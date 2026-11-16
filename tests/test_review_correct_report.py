import json
from dataclasses import replace
from pathlib import Path

import pytest
from openpyxl import load_workbook

from docreview.checks import run_rule_checks
from docreview.collect import collect
from docreview.correct import (
    STATUS_CORRECTED,
    STATUS_MANUAL,
    STATUS_NEW,
    STATUS_NOT_FIXED,
    STATUS_OPEN,
    STATUS_REJECTED,
    ReportRow,
    apply_decision,
    corrected_path,
    label_recheck,
    status_rows,
)
from docreview.models import Finding, Fix
from docreview.readers import read_document
from docreview.report import ReportContext, write_reports
from docreview.review import Decision, DecisionError, interactive_review, load_decision


def _findings(path, rules):
    document = read_document(path)
    return collect(document, [run_rule_checks(document, rules)])


def _scripted(answers):
    remaining = iter(answers)
    return lambda prompt: next(remaining)


def _finding(finding_id="F001", fix=True, **overrides):
    base = Finding(
        unit_id="u", target_id="p0", locator="Absatz 1", category="spelling", severity="medium",
        description="Tippfehler", original="Projeckt", suggestion="Projekt", confidence="certain", source="llm",
        fix=Fix("replace_text", "p0", "Projeckt", "Projekt") if fix else None, finding_id=finding_id,
    )
    return replace(base, **overrides)


# --- step 05 ---------------------------------------------------------------------------------------


def test_interactive_review_when_report_chosen_accepts_nothing():
    decision = interactive_review([_finding()], _scripted(["b"]), lambda text: None)
    assert decision == Decision(mode="report")


def test_interactive_review_when_yes_no_then_all_accepts_selected():
    findings = [_finding(f"F00{i}") for i in range(1, 5)]
    decision = interactive_review(findings, _scripted(["x", "k", "j", "n", "a"]), lambda text: None)
    assert decision == Decision(mode="correct", accepted=("F001", "F003", "F004"))


def test_interactive_review_when_quit_stops_accepting():
    findings = [_finding("F001"), _finding("F002")]
    decision = interactive_review(findings, _scripted(["k", "q"]), lambda text: None)
    assert decision == Decision(mode="correct", accepted=())


def test_interactive_review_when_nothing_fixable_returns_report_without_asking():
    decision = interactive_review([_finding(fix=False)], _scripted([]), lambda text: None)
    assert decision.mode == "report"


def test_interactive_review_when_no_findings_returns_report():
    assert interactive_review([], _scripted([]), lambda text: None).mode == "report"


def test_load_decision_when_valid_returns_decision(tmp_path: Path):
    path = tmp_path / "d.json"
    path.write_text(json.dumps({"mode": "correct", "accepted": ["F001"]}), encoding="utf-8")
    assert load_decision(path, [_finding()]) == Decision("correct", ("F001",))


@pytest.mark.parametrize(
    "payload",
    [{"mode": "correct", "accepted": ["F999"]}, {"mode": "maybe", "accepted": []}, {"accepted": []}],
)
def test_load_decision_when_invalid_raises(tmp_path: Path, payload):
    path = tmp_path / "d.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(DecisionError):
        load_decision(path, [_finding(), _finding("F002", fix=False)])


# --- step 06a writers ------------------------------------------------------------------------------


@pytest.mark.parametrize("file_type", ["pptx", "docx", "xlsx"])
def test_apply_decision_when_all_fixable_accepted_fixes_disappear_on_recheck(
    fixture_paths, example_rules, tmp_path, file_type
):
    source = fixture_paths[file_type]
    original_bytes = source.read_bytes()
    findings = _findings(source, example_rules)
    accepted = tuple(f.finding_id for f in findings if f.fix is not None)
    target = corrected_path(tmp_path, source)
    outcome = apply_decision(source, target, file_type, findings, Decision("correct", accepted))
    assert source.read_bytes() == original_bytes
    assert all(reason is None for reason in outcome.values()), outcome
    remaining = _findings(target, example_rules)
    assert not any(f.fix is not None for f in remaining)
    assert len(remaining) == len([f for f in findings if f.fix is None])


def test_apply_decision_when_text_fixed_keeps_run_formatting(fixture_paths, example_rules, tmp_path):
    source = fixture_paths["pptx"]
    findings = _findings(source, example_rules)
    date_fix = next(f for f in findings if "Datum" in f.description)
    target = corrected_path(tmp_path, source)
    apply_decision(source, target, "pptx", findings, Decision("correct", (date_fix.finding_id,)))
    paragraph = read_document(target).paragraph_index()[date_fix.target_id]
    assert "15.03.2026" in paragraph.text
    assert (paragraph.runs[0].font, paragraph.runs[0].size_pt) == ("Arial", 18.0)


def test_apply_decision_when_text_spans_runs_reports_failure(tmp_path: Path):
    from docx import Document as new_docx

    document = new_docx()
    paragraph = document.add_paragraph()
    paragraph.add_run("Proj")
    paragraph.add_run("eckt").bold = True
    document.save(tmp_path / "a.docx")
    finding = _finding(target_id="p0", fix=True)
    outcome = apply_decision(
        tmp_path / "a.docx", tmp_path / "b.docx", "docx", [finding], Decision("correct", ("F001",))
    )
    assert outcome == {"F001": "über mehrere Formatierungen verteilt"}


def test_apply_decision_when_xlsx_formula_cell_is_not_changed(tmp_path: Path):
    from openpyxl import Workbook

    workbook = Workbook()
    workbook.active["A1"] = "=CONCAT(\"Email\",\"x\")"
    workbook.save(tmp_path / "a.xlsx")
    finding = _finding(target_id="Sheet!A1", fix=True)
    finding = replace(finding, fix=Fix("replace_text", "Sheet!A1", "Email", "E-Mail"))
    outcome = apply_decision(
        tmp_path / "a.xlsx", tmp_path / "b.xlsx", "xlsx", [finding], Decision("correct", ("F001",))
    )
    assert outcome == {"F001": "Formelzelle – wird nicht automatisch geändert"}


def test_apply_decision_when_nothing_accepted_only_copies(fixture_paths, tmp_path):
    source = fixture_paths["docx"]
    outcome = apply_decision(source, tmp_path / "c.docx", "docx", [], Decision("correct"))
    assert outcome == {}
    assert (tmp_path / "c.docx").read_bytes() == source.read_bytes()


# --- statuses and re-check labels -----------------------------------------------------------------


def test_status_rows_when_mixed_decision_assigns_each_status():
    findings = [_finding("F001"), _finding("F002"), _finding("F003"), _finding("F004", fix=False)]
    decision = Decision("correct", ("F001", "F003"))
    rows = status_rows(findings, decision, {"F001": None, "F003": "über mehrere Formatierungen verteilt"})
    assert [row.status for row in rows] == [STATUS_CORRECTED, STATUS_REJECTED, STATUS_MANUAL, STATUS_MANUAL]
    assert "fehlgeschlagen" in rows[2].note


def test_status_rows_when_report_mode_marks_fixable_open():
    rows = status_rows([_finding()], Decision("report"), {})
    assert rows[0].status == STATUS_OPEN


def test_label_recheck_when_fix_persists_or_new_error_labels_and_renumbers():
    previous = [
        ReportRow(_finding("F001"), STATUS_CORRECTED),
        ReportRow(_finding("F002", target_id="p1"), STATUS_REJECTED),
    ]
    recheck = [
        _finding("F001"),
        _finding("F002", target_id="p1"),
        _finding("F003", target_id="p2", original="Teh", suggestion="The"),
    ]
    rows = label_recheck(previous, recheck, first_id=10)
    assert [(row.finding.finding_id, row.status) for row in rows] == [("F010", STATUS_NOT_FIXED), ("F011", STATUS_NEW)]


# --- step 06b --------------------------------------------------------------------------------------


def test_write_reports_when_rows_given_writes_xlsx_and_markdown(tmp_path: Path):
    rows = [ReportRow(_finding(), STATUS_OPEN), ReportRow(_finding("F002", fix=False), STATUS_MANUAL, "x|y")]
    context = ReportContext("a.docx", unchecked_units=("Folie 3",), warnings=("Achtung",))
    xlsx, markdown = write_reports(tmp_path, "Pruefliste", rows, context)
    sheet = load_workbook(xlsx)["Prüfliste"]
    assert [cell.value for cell in sheet[1]][0] == "Nr."
    assert sheet["I3"].value == "manuell (x|y)"
    text = markdown.read_text(encoding="utf-8")
    assert "**2 Befunde.**" in text
    assert "Folie 3" in text and "> Achtung" in text
    assert "manuell (x\\|y)" in text
