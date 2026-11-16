"""Formatting checks: fonts, sizes, colours against the rules; alignment and spacing against the document."""

from __future__ import annotations

from collections.abc import Iterator

from docreview.checks.common import TextTarget, majority, rule_finding
from docreview.models import Document, Finding, Fix, Paragraph
from docreview.rules import FormatRules

PARAGRAPH_ATTRIBUTES = (
    ("alignment", "Ausrichtung"),
    ("space_before_pt", "Abstand vor dem Absatz"),
    ("space_after_pt", "Abstand nach dem Absatz"),
)
MIN_GROUP_SIZE = 3


def _target(unit_id: str, paragraph: Paragraph) -> TextTarget:
    return TextTarget(unit_id, paragraph.paragraph_id, paragraph.locator, paragraph.text)


def _font_findings(unit_id: str, paragraph: Paragraph, rules: FormatRules) -> Iterator[Finding]:
    if not rules.allowed_fonts:
        return
    bad_fonts = sorted({run.font for run in paragraph.runs if run.font and run.font not in rules.allowed_fonts})
    for font in bad_fonts:
        replacement = rules.replacement_font or rules.allowed_fonts[0]
        yield rule_finding(
            _target(unit_id, paragraph),
            category="formatting",
            severity="medium",
            description=f"Schriftart „{font}“ ist nicht erlaubt (erlaubt: {', '.join(rules.allowed_fonts)})",
            original=font,
            suggestion=replacement,
            fix=Fix(kind="set_font", target_id=paragraph.paragraph_id, old=font, new=replacement),
        )


def _clamp(size: float, rules: FormatRules) -> float | None:
    if rules.min_font_size_pt is not None and size < rules.min_font_size_pt:
        return float(rules.min_font_size_pt)
    if rules.max_font_size_pt is not None and size > rules.max_font_size_pt:
        return float(rules.max_font_size_pt)
    return None


def _size_findings(unit_id: str, paragraph: Paragraph, rules: FormatRules) -> Iterator[Finding]:
    sizes = sorted({run.size_pt for run in paragraph.runs if run.size_pt is not None})
    for size in sizes:
        clamped = _clamp(size, rules)
        if clamped is None:
            continue
        yield rule_finding(
            _target(unit_id, paragraph),
            category="formatting",
            severity="medium",
            description=(
                f"Schriftgröße {size:g} pt außerhalb der Vorgabe "
                f"({rules.min_font_size_pt:g}–{rules.max_font_size_pt:g} pt)"
            ),
            original=f"{size:g} pt",
            suggestion=f"{clamped:g} pt",
            fix=Fix(kind="set_font_size", target_id=paragraph.paragraph_id, old=str(size), new=str(clamped)),
        )


def _color_findings(unit_id: str, paragraph: Paragraph, rules: FormatRules) -> Iterator[Finding]:
    if not rules.allowed_colors:
        return
    colors = sorted({run.color for run in paragraph.runs if run.color and run.color not in rules.allowed_colors})
    for color in colors:
        yield rule_finding(
            _target(unit_id, paragraph),
            category="formatting",
            severity="low",
            description=f"Farbe #{color} ist nicht in der Farbvorgabe",
            original=f"#{color}",
            suggestion=f"eine der Farben {', '.join('#' + c for c in rules.allowed_colors)}",
        )


def _paragraph_layout_findings(document: Document) -> Iterator[Finding]:
    """Within one style, flag paragraphs whose alignment or spacing differs from the majority."""
    entries = [(unit.unit_id, p) for unit in document.units for p in unit.paragraphs if p.style is not None]
    for style in sorted({p.style for _, p in entries if p.style}):
        group = [(unit_id, p) for unit_id, p in entries if p.style == style]
        if len(group) < MIN_GROUP_SIZE:
            continue
        for attribute, label in PARAGRAPH_ATTRIBUTES:
            values = [getattr(p, attribute) for _, p in group]
            expected = majority(values)
            if expected is None and values.count(None) == 0:
                continue
            for unit_id, paragraph in group:
                actual = getattr(paragraph, attribute)
                if actual == expected:
                    continue
                yield rule_finding(
                    _target(unit_id, paragraph),
                    category="formatting",
                    severity="low",
                    description=f"{label} weicht von anderen „{style}“-Absätzen ab",
                    original=str(actual if actual is not None else "Standard"),
                    suggestion=str(expected if expected is not None else "Standard"),
                    confidence="probable",
                )


def check_formatting(document: Document, rules: FormatRules) -> list[Finding]:
    per_paragraph = [
        finding
        for unit in document.units
        for paragraph in unit.paragraphs
        for check in (_font_findings, _size_findings, _color_findings)
        for finding in check(unit.unit_id, paragraph, rules)
    ]
    return [*per_paragraph, *_paragraph_layout_findings(document)]
