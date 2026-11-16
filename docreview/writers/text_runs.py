"""Run-level edits shared by the PowerPoint and Word writers (both libraries expose runs with .text and .font)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from docreview.models import Fix

SPANS_RUNS = "über mehrere Formatierungen verteilt"
NOT_FOUND = "Textstelle nicht mehr vorhanden"
NO_MATCHING_RUN = "keine passende Textstelle mit dieser Formatierung"
UNSUPPORTED = "Korrekturart für diesen Dateityp nicht unterstützt"


def replace_in_runs(runs: list[Any], old: str, new: str) -> str | None:
    """Replace the first occurrence inside a single run. Returns None on success, else the failure reason."""
    for run in runs:
        if old in run.text:
            run.text = run.text.replace(old, new, 1)
            return None
    if old in "".join(run.text for run in runs):
        return SPANS_RUNS
    return NOT_FOUND


def set_run_font(runs: list[Any], old: str | None, new: str) -> str | None:
    matching = [run for run in runs if run.font.name == old]
    for run in matching:
        run.font.name = new
    return None if matching else NO_MATCHING_RUN


def set_run_size(runs: list[Any], old: str | None, new: str, to_length: Callable[[float], Any]) -> str | None:
    matching = [run for run in runs if run.font.size is not None and str(run.font.size.pt) == old]
    for run in matching:
        run.font.size = to_length(float(new))
    return None if matching else NO_MATCHING_RUN


def apply_run_fix(paragraph: Any, fix: Fix, to_length: Callable[[float], Any]) -> str | None:
    runs = list(paragraph.runs)
    if fix.kind == "replace_text" and fix.old is not None and fix.new is not None:
        return replace_in_runs(runs, fix.old, fix.new)
    if fix.kind == "set_font" and fix.new is not None:
        return set_run_font(runs, fix.old, fix.new)
    if fix.kind == "set_font_size" and fix.new is not None:
        return set_run_size(runs, fix.old, fix.new, to_length)
    return UNSUPPORTED
