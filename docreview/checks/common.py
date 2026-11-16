"""Shared helpers for the rule checks (step 03b)."""

from __future__ import annotations

from collections import Counter
from collections.abc import Hashable, Iterable, Iterator
from dataclasses import dataclass
from typing import TypeVar

from docreview.models import Category, Confidence, Document, Finding, Fix, Severity

T = TypeVar("T", bound=Hashable)


@dataclass(frozen=True)
class TextTarget:
    """A piece of checkable text: a paragraph, or an Excel cell holding a string."""

    unit_id: str
    target_id: str
    locator: str
    text: str


def text_targets(document: Document) -> Iterator[TextTarget]:
    for unit in document.units:
        for paragraph in unit.paragraphs:
            yield TextTarget(unit.unit_id, paragraph.paragraph_id, paragraph.locator, paragraph.text)
        for cell in unit.cells:
            if isinstance(cell.value, str) and cell.data_type == "s":
                yield TextTarget(unit.unit_id, cell.cell_id, cell.locator, cell.value)


def rule_finding(
    target: TextTarget,
    *,
    category: Category,
    severity: Severity,
    description: str,
    original: str,
    suggestion: str,
    confidence: Confidence = "certain",
    fix: Fix | None = None,
) -> Finding:
    return Finding(
        unit_id=target.unit_id,
        target_id=target.target_id,
        locator=target.locator,
        category=category,
        severity=severity,
        description=description,
        original=original,
        suggestion=suggestion,
        confidence=confidence,
        source="rules",
        fix=fix,
    )


def replace_fix(target: TextTarget, old: str, new: str) -> Fix:
    return Fix(kind="replace_text", target_id=target.target_id, old=old, new=new)


def majority(values: Iterable[T]) -> T | None:
    """The most common value if it is a strict majority or the clear winner; None on an exact tie."""
    ranked = Counter(values).most_common(2)
    if not ranked:
        return None
    if len(ranked) == 2 and ranked[0][1] == ranked[1][1]:
        return None
    return ranked[0][0]
