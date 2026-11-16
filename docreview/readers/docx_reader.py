"""Step 02 for Word: one unit per "Heading 1" section, body paragraphs and table cells in document order."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from docx import Document as open_docx
from docx.enum.dml import MSO_COLOR_TYPE
from docx.table import Table
from docx.text.paragraph import Paragraph as DocxParagraph

from docreview.models import Document, Paragraph, TextRun, Unit

SECTION_STYLES = ("Heading 1", "Überschrift 1", "Title", "Titel")
HEADING_PREFIXES = ("Heading ", "Überschrift ")
FRONT_MATTER_LABEL = "Dokumentanfang"


@dataclass(frozen=True)
class ParagraphRef:
    paragraph_id: str
    table_position: str | None
    paragraph: Any


def _table_paragraphs(table: Table, table_index: int) -> Iterator[ParagraphRef]:
    seen_cells: set[int] = set()
    for row_index, row in enumerate(table.rows):
        for column_index, cell in enumerate(row.cells):
            if id(cell._tc) in seen_cells:
                continue
            seen_cells.add(id(cell._tc))
            for paragraph_index, paragraph in enumerate(cell.paragraphs):
                yield ParagraphRef(
                    paragraph_id=f"t{table_index}/r{row_index}c{column_index}/p{paragraph_index}",
                    table_position=f"Tabelle {table_index + 1}, Zeile {row_index + 1} Spalte {column_index + 1}",
                    paragraph=paragraph,
                )


def iter_paragraphs(document: Any) -> Iterator[ParagraphRef]:
    """Shared by reader and writer so paragraph IDs resolve to the same objects."""
    paragraph_index = 0
    table_index = 0
    for child in document.element.body.iterchildren():
        tag = child.tag.rsplit("}", 1)[-1]
        if tag == "p":
            yield ParagraphRef(f"p{paragraph_index}", None, DocxParagraph(child, document))
            paragraph_index += 1
        elif tag == "tbl":
            yield from _table_paragraphs(Table(child, document), table_index)
            table_index += 1


def heading_level(style: str | None) -> int | None:
    if style is None:
        return None
    for prefix in HEADING_PREFIXES:
        if style.startswith(prefix) and style[len(prefix) :].isdigit():
            return int(style[len(prefix) :])
    return None


def _run_color(run: Any) -> str | None:
    color = run.font.color
    if color is None or color.type != MSO_COLOR_TYPE.RGB or color.rgb is None:
        return None
    return str(color.rgb).upper()


def _read_run(run: Any) -> TextRun:
    size = run.font.size
    return TextRun(
        text=run.text,
        font=run.font.name,
        size_pt=size.pt if size is not None else None,
        color=_run_color(run),
        bold=run.bold,
    )


def _points(length: Any) -> float | None:
    return round(length.pt, 1) if length is not None else None


def _to_paragraph(ref: ParagraphRef, section: str, number_in_section: int) -> Paragraph:
    paragraph = ref.paragraph
    position = ref.table_position or f"Absatz {number_in_section}"
    alignment = paragraph.paragraph_format.alignment
    return Paragraph(
        paragraph_id=ref.paragraph_id,
        locator=f'Abschnitt "{section}", {position}',
        text=paragraph.text,
        runs=tuple(_read_run(run) for run in paragraph.runs),
        style=paragraph.style.name if paragraph.style is not None else None,
        alignment=alignment.name if alignment is not None else None,
        space_before_pt=_points(paragraph.paragraph_format.space_before),
        space_after_pt=_points(paragraph.paragraph_format.space_after),
    )


def _make_unit(index: int, title: str, paragraphs: list[Paragraph]) -> Unit:
    return Unit(unit_id=f"section-{index}", label=f"Abschnitt {index}: {title}", paragraphs=tuple(paragraphs))


def read_docx(path: Path) -> Document:
    document = open_docx(str(path))
    units: list[Unit] = []
    title, counter = FRONT_MATTER_LABEL, 0
    paragraphs: list[Paragraph] = []
    for ref in iter_paragraphs(document):
        text = ref.paragraph.text
        style = ref.paragraph.style.name if ref.paragraph.style is not None else None
        starts_section = ref.table_position is None and style in SECTION_STYLES and text.strip()
        if starts_section and paragraphs:
            units.append(_make_unit(len(units), title, paragraphs))
            paragraphs, counter = [], 0
        if starts_section:
            title = text.strip()
        if not text.strip():
            continue
        counter += 1
        paragraphs.append(_to_paragraph(ref, title, counter))
    if paragraphs:
        units.append(_make_unit(len(units), title, paragraphs))
    return Document(file_type="docx", source_path=str(path), units=tuple(units))
