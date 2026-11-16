"""Step 06a writers: apply fixes to a file that is already a copy. Return {finding_id: failure reason or None}."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from docx import Document as open_docx
from docx.shared import Pt as DocxPt
from openpyxl import load_workbook
from pptx import Presentation
from pptx.util import Pt as PptxPt

from docreview.models import Finding
from docreview.readers.docx_reader import iter_paragraphs
from docreview.readers.pptx_reader import iter_frames, paragraph_id
from docreview.readers.xlsx_reader import split_cell_id
from docreview.writers.text_runs import NOT_FOUND, UNSUPPORTED, apply_run_fix

Outcome = dict[str, str | None]
FORMULA_CELL = "Formelzelle – wird nicht automatisch geändert"
UNKNOWN_TARGET = "Fundstelle nicht gefunden"


def _apply_to_paragraphs(paragraphs: dict[str, Any], findings: list[Finding], to_length: Any) -> Outcome:
    outcome: Outcome = {}
    for finding in findings:
        paragraph = paragraphs.get(finding.target_id)
        if finding.fix is None or paragraph is None:
            outcome[finding.finding_id] = UNKNOWN_TARGET
            continue
        outcome[finding.finding_id] = apply_run_fix(paragraph, finding.fix, to_length)
    return outcome


def write_pptx(path: Path, findings: list[Finding]) -> Outcome:
    presentation = Presentation(str(path))
    paragraphs = {
        paragraph_id(ref.container.container_id, index): paragraph
        for ref in iter_frames(presentation)
        for index, paragraph in enumerate(ref.text_frame.paragraphs)
    }
    outcome = _apply_to_paragraphs(paragraphs, findings, PptxPt)
    presentation.save(str(path))
    return outcome


def write_docx(path: Path, findings: list[Finding]) -> Outcome:
    document = open_docx(str(path))
    paragraphs = {ref.paragraph_id: ref.paragraph for ref in iter_paragraphs(document)}
    outcome = _apply_to_paragraphs(paragraphs, findings, DocxPt)
    document.save(str(path))
    return outcome


def _apply_cell_fix(workbook: Any, finding: Finding) -> str | None:
    fix = finding.fix
    sheet_title, coordinate = split_cell_id(finding.target_id)
    if fix is None or sheet_title not in workbook.sheetnames:
        return UNKNOWN_TARGET
    cell = workbook[sheet_title][coordinate]
    if fix.kind == "set_number_format" and fix.new is not None:
        cell.number_format = fix.new
        return None
    if fix.kind != "replace_text" or fix.old is None or fix.new is None:
        return UNSUPPORTED
    if cell.data_type == "f":
        return FORMULA_CELL
    if not isinstance(cell.value, str) or fix.old not in cell.value:
        return NOT_FOUND
    cell.value = cell.value.replace(fix.old, fix.new, 1)
    return None


def write_xlsx(path: Path, findings: list[Finding]) -> Outcome:
    workbook = load_workbook(str(path))
    outcome = {finding.finding_id: _apply_cell_fix(workbook, finding) for finding in findings}
    workbook.save(str(path))
    return outcome


WRITERS = {"pptx": write_pptx, "docx": write_docx, "xlsx": write_xlsx}
