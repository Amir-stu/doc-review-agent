"""File-type specific checks: PowerPoint overflow, Word headings, Excel error values and number formats."""

from __future__ import annotations

import math
import re
from collections import defaultdict
from collections.abc import Iterator

from openpyxl.utils.cell import coordinate_from_string

from docreview.checks.common import TextTarget, majority, rule_finding
from docreview.config import (
    AVERAGE_CHAR_WIDTH_EM,
    DEFAULT_FONT_SIZE_PT,
    LINE_HEIGHT_FACTOR,
    MANUAL_HEADING_MAX_CHARS,
    OVERFLOW_TOLERANCE,
    TEXTBOX_INSET_PT,
)
from docreview.models import Cell, Document, Finding, Fix, Paragraph, Unit
from docreview.readers.docx_reader import heading_level
from docreview.readers.xlsx_reader import split_cell_id

EXCEL_ERRORS = ("#NULL!", "#DIV/0!", "#VALUE!", "#REF!", "#NAME?", "#NUM!", "#N/A")
NUMBER_AS_TEXT = re.compile(r"^-?(\d{1,3}(\.\d{3})+|\d+)(,\d+)?$")
SENTENCE_END = (".", ":", "!", "?")
HEADING_ATTRIBUTES = (("size_pt", "Schriftgröße"), ("font", "Schriftart"), ("color", "Farbe"))
MIN_COLUMN_SIZE = 3


def _target(unit_id: str, paragraph: Paragraph) -> TextTarget:
    return TextTarget(unit_id, paragraph.paragraph_id, paragraph.locator, paragraph.text)


# --- PowerPoint -------------------------------------------------------------------------------------


def estimate_text_height_pt(
    texts: list[str], *, font_size_pt: float, width_pt: float, word_wrap: bool
) -> float:
    """Rough layout: average glyph width of half an em. Good enough to flag, not to prove, an overflow."""
    usable_width = max(width_pt - 2 * TEXTBOX_INSET_PT, 1.0)
    chars_per_line = max(1, int(usable_width / (font_size_pt * AVERAGE_CHAR_WIDTH_EM)))
    lines = sum(max(1, math.ceil(len(text) / chars_per_line)) for text in texts) if word_wrap else len(texts)
    return lines * font_size_pt * LINE_HEIGHT_FACTOR + 2 * TEXTBOX_INSET_PT


def _overflow_findings(unit: Unit) -> Iterator[Finding]:
    for container in unit.containers:
        if container.auto_fit or not container.width_pt or not container.height_pt:
            continue
        paragraphs = [p for p in unit.paragraphs if p.container_id == container.container_id]
        if not paragraphs:
            continue
        sizes = [run.size_pt for p in paragraphs for run in p.runs if run.size_pt is not None]
        font_size = max(sizes, default=DEFAULT_FONT_SIZE_PT)
        texts = [p.text for p in paragraphs]
        needed = estimate_text_height_pt(
            texts, font_size_pt=font_size, width_pt=container.width_pt, word_wrap=container.word_wrap
        )
        widest = max(len(text) for text in texts) * font_size * AVERAGE_CHAR_WIDTH_EM + 2 * TEXTBOX_INSET_PT
        too_high = needed > container.height_pt * OVERFLOW_TOLERANCE
        too_wide = not container.word_wrap and widest > container.width_pt * OVERFLOW_TOLERANCE
        if not (too_high or too_wide):
            continue
        first = paragraphs[0]
        yield rule_finding(
            TextTarget(unit.unit_id, first.paragraph_id, container.locator, first.text),
            category="file_specific",
            severity="high",
            description=(
                f"Text wird wahrscheinlich abgeschnitten (benötigt ca. {needed:.0f} pt Höhe, "
                f"Feld hat {container.height_pt:.0f} pt)"
            ),
            original=first.text,
            suggestion="Text kürzen, Feld vergrößern oder Schriftgröße reduzieren",
            confidence="probable",
        )


# --- Word -------------------------------------------------------------------------------------------


def _heading_text_findings(unit_id: str, paragraph: Paragraph) -> Iterator[Finding]:
    text = paragraph.text.rstrip()
    level = heading_level(paragraph.style)
    if level is not None and text.endswith(".") and not text.endswith(".."):
        yield rule_finding(
            _target(unit_id, paragraph),
            category="file_specific",
            severity="low",
            description="Überschrift endet mit Punkt",
            original=text,
            suggestion=text.rstrip("."),
            fix=Fix(kind="replace_text", target_id=paragraph.paragraph_id, old=text, new=text.rstrip(".")),
        )
    all_bold = bool(paragraph.runs) and all(run.bold for run in paragraph.runs)
    looks_like_heading = (
        level is None
        and all_bold
        and len(text) <= MANUAL_HEADING_MAX_CHARS
        and not text.endswith(SENTENCE_END)
    )
    if looks_like_heading:
        yield rule_finding(
            _target(unit_id, paragraph),
            category="file_specific",
            severity="medium",
            description="Überschrift ohne Formatvorlage (nur fett formatiert)",
            original=text,
            suggestion="Formatvorlage „Überschrift“ der passenden Ebene zuweisen",
            confidence="probable",
        )


def _first_run_value(paragraph: Paragraph, attribute: str) -> object:
    return getattr(paragraph.runs[0], attribute) if paragraph.runs else None


def _heading_consistency_findings(document: Document) -> Iterator[Finding]:
    by_level: dict[int, list[tuple[str, Paragraph]]] = defaultdict(list)
    for unit in document.units:
        for paragraph in unit.paragraphs:
            level = heading_level(paragraph.style)
            if level is not None:
                by_level[level].append((unit.unit_id, paragraph))
    for level, headings in sorted(by_level.items()):
        for attribute, label in HEADING_ATTRIBUTES:
            values = [_first_run_value(p, attribute) for _, p in headings]
            if len(set(values)) < 2:
                continue
            expected = majority(values)
            reference = expected if expected is not None else values[0]
            for unit_id, paragraph in headings:
                actual = _first_run_value(paragraph, attribute)
                if actual == reference:
                    continue
                yield rule_finding(
                    _target(unit_id, paragraph),
                    category="file_specific",
                    severity="medium",
                    description=f"Überschriften der Ebene {level} uneinheitlich: {label} {actual} statt {reference}",
                    original=f"{label} {actual}",
                    suggestion=f"{label} {reference}",
                )


# --- Excel ------------------------------------------------------------------------------------------


def _cell_target(unit_id: str, cell: Cell) -> TextTarget:
    return TextTarget(unit_id, cell.cell_id, cell.locator, str(cell.value))


def _is_number(cell: Cell) -> bool:
    return cell.data_type == "n" and isinstance(cell.value, int | float) and not isinstance(cell.value, bool)


def _column(cell: Cell) -> str:
    sheet, coordinate = split_cell_id(cell.cell_id)
    return f"{sheet}!{coordinate_from_string(coordinate)[0]}"


def _excel_findings(unit: Unit) -> Iterator[Finding]:
    columns: dict[str, list[Cell]] = defaultdict(list)
    for cell in unit.cells:
        columns[_column(cell)].append(cell)
        if cell.data_type == "e" or cell.value in EXCEL_ERRORS:
            yield rule_finding(
                _cell_target(unit.unit_id, cell),
                category="file_specific",
                severity="high",
                description=f"Sichtbarer Fehlerwert {cell.value}",
                original=str(cell.value),
                suggestion="Formel oder Eingabewerte prüfen",
            )
    for cells in columns.values():
        numbers = [cell for cell in cells if _is_number(cell)]
        yield from _number_format_findings(unit.unit_id, numbers)
        if not numbers:
            continue
        for cell in cells:
            if (
                isinstance(cell.value, str)
                and cell.data_type == "s"
                and NUMBER_AS_TEXT.match(cell.value.strip())
            ):
                yield rule_finding(
                    _cell_target(unit.unit_id, cell),
                    category="file_specific",
                    severity="medium",
                    description="Zahl als Text gespeichert",
                    original=cell.value,
                    suggestion="Als Zahl eingeben",
                )


def _number_format_findings(unit_id: str, numbers: list[Cell]) -> Iterator[Finding]:
    if len(numbers) < MIN_COLUMN_SIZE:
        return
    expected = majority(cell.number_format for cell in numbers)
    if expected is None:
        return
    for cell in numbers:
        if cell.number_format == expected:
            continue
        yield rule_finding(
            _cell_target(unit_id, cell),
            category="file_specific",
            severity="medium",
            description="Zahlenformat weicht von der übrigen Spalte ab",
            original=cell.number_format,
            suggestion=expected,
            confidence="probable",
            fix=Fix(kind="set_number_format", target_id=cell.cell_id, old=cell.number_format, new=expected),
        )


def check_file_specific(document: Document) -> list[Finding]:
    if document.file_type == "pptx":
        return [finding for unit in document.units for finding in _overflow_findings(unit)]
    if document.file_type == "docx":
        text_findings = [
            finding
            for unit in document.units
            for paragraph in unit.paragraphs
            for finding in _heading_text_findings(unit.unit_id, paragraph)
        ]
        return [*text_findings, *_heading_consistency_findings(document)]
    return [finding for unit in document.units for finding in _excel_findings(unit)]
