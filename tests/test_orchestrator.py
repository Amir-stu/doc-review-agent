import json
from pathlib import Path

import pytest
from fixture_files import SEEDED_TYPOS, build_all
from openpyxl import load_workbook

from docreview import cli
from docreview.orchestrator import IntakeError, Options, run_pipeline, step_intake
from docreview.readers import read_document
from docreview.review import Decision
from docreview.runner import AgentResult

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RULES = PROJECT_ROOT / "format_rules.example.yaml"
CORRECTIONS = {"verröffentlicht": "veröffentlicht", "Projeckt": "Projekt", "Gesammt": "Gesamt"}


def typo_agent(spec, prompt):
    """Stands in for `claude -p`: reports each seeded typo once, nothing else."""
    if spec.name != "doc-review-03a-language-check":
        return AgentResult("", {"findings": []}, 0.0)
    items = json.loads(prompt[prompt.index("{") :])["items"]
    findings = [
        {
            "target_id": item["id"],
            "category": "spelling",
            "severity": "medium",
            "description": "Tippfehler",
            "original": typo,
            "suggestion": fixed,
        }
        for item in items
        for typo, fixed in CORRECTIONS.items()
        if typo in item["text"]
    ]
    return AgentResult("", {"findings": findings}, 0.01)


@pytest.fixture
def fresh_files(tmp_path: Path) -> dict[str, Path]:
    return build_all(tmp_path / "input")


def _accept_all(findings, round_number):
    return Decision("correct", tuple(f.finding_id for f in findings if f.fix is not None))


@pytest.mark.parametrize("file_type", ["pptx", "docx", "xlsx"])
def test_run_pipeline_when_all_fixes_accepted_writes_clean_copy_and_report(fresh_files, tmp_path, file_type):
    source = fresh_files[file_type]
    original = source.read_bytes()
    options = Options(agent=typo_agent, max_parallel=2)
    result = run_pipeline(source, RULES, tmp_path / "runs", _accept_all, options)
    assert source.read_bytes() == original
    assert result.corrected_file is not None and result.corrected_file.is_file()
    statuses = {row.status for row in result.rows}
    assert statuses <= {"korrigiert", "manuell"}
    corrected_text = " ".join(p.text for p in read_document(result.corrected_file).paragraph_index().values())
    corrected_text += " ".join(
        str(c.value) for c in read_document(result.corrected_file).cell_index().values()
    )
    assert SEEDED_TYPOS[file_type] not in corrected_text
    for name in (
        "01_intake.json",
        "02_units.json",
        "04_findings.json",
        "05_decision.json",
        "06a_applied_1.json",
        "06a_recheck_1.json",
        "Pruefliste.xlsx",
        "Pruefliste.md",
    ):
        assert (result.run_dir / name).is_file(), name


def test_run_pipeline_when_report_only_changes_nothing(fresh_files, tmp_path):
    options = Options(agent=typo_agent)
    result = run_pipeline(
        fresh_files["docx"], RULES, tmp_path / "runs", lambda f, r: Decision("report"), options
    )
    assert result.corrected_file is None
    assert not list(result.run_dir.glob("*_korrigiert*"))
    assert {row.status for row in result.rows} == {"offen", "manuell"}
    assert any(row.finding.source == "llm" for row in result.rows)


def test_run_pipeline_when_no_llm_never_calls_agent_and_warns(fresh_files, tmp_path):
    def forbidden(spec, prompt):
        raise AssertionError("agent must not be called")

    options = Options(use_llm=False, agent=forbidden)
    result = run_pipeline(
        fresh_files["pptx"], RULES, tmp_path / "runs", lambda f, r: Decision("report"), options
    )
    assert "Sprachprüfung übersprungen" in result.reports[1].read_text(encoding="utf-8")


def test_run_pipeline_when_fix_introduces_new_error_asks_second_round(fresh_files, tmp_path):
    calls = []

    def gate(findings, round_number):
        calls.append(round_number)
        if round_number == 1:
            return _accept_all(findings, round_number)
        return Decision("report")

    def noisy_agent(spec, prompt):
        """Flags 'Projekt' in the re-check, as if the fix itself were wrong."""
        if spec.name != "doc-review-03a-language-check":
            return AgentResult("", {"findings": []}, 0.0)
        items = json.loads(prompt[prompt.index("{") :])["items"]
        findings = [
            {
                "target_id": i["id"],
                "category": "wording",
                "severity": "low",
                "description": "Wort prüfen",
                "original": word,
                "suggestion": replacement,
            }
            for i in items
            for word, replacement in (("Projeckt", "Projekt"), ("Projekt ", "Vorhaben "))
            if word in i["text"]
        ]
        return AgentResult("", {"findings": findings}, 0.0)

    result = run_pipeline(fresh_files["docx"], RULES, tmp_path / "runs", gate, Options(agent=noisy_agent))
    assert calls == [1, 2]
    new_rows = [row for row in result.rows if "neu im Re-Check 1" in row.note]
    assert [row.finding.original for row in new_rows] == ["Projekt "]
    ids = [row.finding.finding_id for row in result.rows]
    assert len(ids) == len(set(ids))


def test_step_intake_when_wrong_suffix_raises(tmp_path):
    bad = tmp_path / "a.txt"
    bad.write_text("x", encoding="utf-8")
    with pytest.raises(IntakeError, match="Nicht unterstützter"):
        step_intake(bad, RULES, tmp_path / "runs")
    with pytest.raises(IntakeError, match="nicht gefunden"):
        step_intake(tmp_path / "missing.pptx", RULES, tmp_path / "runs")


# --- CLI -------------------------------------------------------------------------------------------


def test_cli_check_when_report_only_and_no_llm_writes_report(fresh_files, tmp_path, capsys):
    code = cli.main(
        [
            "check",
            str(fresh_files["xlsx"]),
            "--rules",
            str(RULES),
            "--runs-dir",
            str(tmp_path / "runs"),
            "--report-only",
            "--no-llm",
        ]
    )
    assert code == 0
    assert "Pruefliste.xlsx" in capsys.readouterr().out
    report = next((tmp_path / "runs").glob("*/Pruefliste.xlsx"))
    assert load_workbook(report)["Prüfliste"].max_row > 1


def test_cli_run_steps_when_chained_produce_same_files_as_pipeline(fresh_files, tmp_path, capsys):
    runs = tmp_path / "runs"
    assert (
        cli.main(
            ["run-step", "intake", str(fresh_files["pptx"]), "--rules", str(RULES), "--runs-dir", str(runs)]
        )
        == 0
    )
    run_dir = capsys.readouterr().out.strip()
    for step in ("split", "check-rules", "collect"):
        assert cli.main(["run-step", step, run_dir, "--no-llm"]) == 0
    findings = json.loads((Path(run_dir) / "04_findings.json").read_text(encoding="utf-8"))
    decision = tmp_path / "decision.json"
    accepted = [f["finding_id"] for f in findings if f["fix"]]
    decision.write_text(json.dumps({"mode": "correct", "accepted": accepted}), encoding="utf-8")
    assert cli.main(["run-step", "review", run_dir, "--decision", str(decision)]) == 0
    assert cli.main(["run-step", "correct", run_dir, "--no-llm"]) == 0
    assert cli.main(["run-step", "report", run_dir]) == 0
    markdown = (Path(run_dir) / "Pruefliste.md").read_text(encoding="utf-8")
    assert "korrigiert" in markdown


def test_cli_when_rules_invalid_exits_2(fresh_files, tmp_path, capsys):
    bad_rules = tmp_path / "rules.yaml"
    bad_rules.write_text("date_format: MM/DD/YYYY\n", encoding="utf-8")
    code = cli.main(
        ["check", str(fresh_files["docx"]), "--rules", str(bad_rules), "--runs-dir", str(tmp_path)]
    )
    assert code == 2
    assert "Formatvorgaben ungültig" in capsys.readouterr().err


def test_cli_interactive_gate_when_user_types_answers_records_decision(fresh_files, tmp_path, monkeypatch):
    answers = iter(["k\n", "a\n"])
    monkeypatch.setattr("sys.stdin", type("S", (), {"readline": staticmethod(lambda: next(answers))})())
    code = cli.main(
        [
            "check",
            str(fresh_files["docx"]),
            "--rules",
            str(RULES),
            "--runs-dir",
            str(tmp_path / "runs"),
            "--no-llm",
        ]
    )
    assert code == 0
    run_dir = next((tmp_path / "runs").iterdir())
    decision = json.loads((run_dir / "05_decision.json").read_text(encoding="utf-8"))
    assert decision["mode"] == "correct" and decision["accepted"]
