"""Runs the steps in order and passes output between them through the run folder.

01 intake → 02 split → 03 check (rules + language agents) → 04 collect → 05 gate →
06a correct + re-check (back to 05, at most MAX_CORRECTION_ROUNDS) | 06b report
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from docreview import collect as collect_step
from docreview import language_check
from docreview.agent_findings import AgentFunction
from docreview.checks import run_rule_checks
from docreview.config import (
    AGENT_TIMEOUT_SECONDS,
    MAX_CORRECTION_ROUNDS,
    MAX_PARALLEL_AGENTS,
    SANDBOX_DIR,
    SUPPORTED_SUFFIXES,
)
from docreview.correct import ReportRow, apply_decision, corrected_path, label_recheck, status_rows
from docreview.instructions import load_instruction
from docreview.models import Document, Finding, finding_from_dict, to_dict
from docreview.readers import read_document
from docreview.report import XLSX_WARNING, ReportContext, write_reports
from docreview.review import Decision
from docreview.rules import FormatRules, parse_rules, read_raw_rules
from docreview.run_folder import (
    COLLECTED_FILE,
    DECISION_FILE,
    FINDINGS_DIR,
    INTAKE_FILE,
    REPORT_STEM,
    UNITS_FILE,
    RunFolder,
)
from docreview.runner import AgentResult, AgentSpec, run_agent

Gate = Callable[[list[Finding], int], Decision]
META_FILE = "04_meta.json"
ROWS_FILE = "06_report_rows.json"
NO_LLM_WARNING = (
    "Sprachprüfung übersprungen (--no-llm): Rechtschreibung und Formulierungen wurden nicht geprüft."
)


class IntakeError(ValueError):
    """The input file cannot be processed."""


def default_agent(spec: AgentSpec, prompt: str) -> AgentResult:
    return run_agent(spec, prompt, sandbox_dir=SANDBOX_DIR, timeout_s=AGENT_TIMEOUT_SECONDS)


@dataclass(frozen=True)
class Options:
    use_llm: bool = True
    max_parallel: int = MAX_PARALLEL_AGENTS
    agent: AgentFunction = default_agent


@dataclass(frozen=True)
class PipelineResult:
    run_dir: Path
    reports: tuple[Path, Path]
    corrected_file: Path | None
    rows: tuple[ReportRow, ...]


# --- 01 ---------------------------------------------------------------------------------------------


def _write_intake(run: RunFolder, source: Path, raw_rules: dict[str, Any]) -> None:
    run.write_json(
        INTAKE_FILE,
        {
            "source_path": str(source.resolve()),
            "file_type": source.suffix.lower().lstrip("."),
            "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            "rules": raw_rules,
        },
    )


def step_intake(source: Path, rules_path: Path, runs_dir: Path) -> RunFolder:
    if not source.is_file():
        raise IntakeError(f"Datei nicht gefunden: {source}")
    if source.suffix.lower() not in SUPPORTED_SUFFIXES:
        raise IntakeError(
            f"Nicht unterstützter Dateityp {source.suffix} – erlaubt: {', '.join(SUPPORTED_SUFFIXES)}"
        )
    raw_rules = read_raw_rules(rules_path)
    run = RunFolder.create(runs_dir, source)
    _write_intake(run, source, raw_rules)
    return run


def _intake(run: RunFolder) -> dict[str, Any]:
    return dict(run.read_json(INTAKE_FILE))


def _rules(run: RunFolder) -> FormatRules:
    return parse_rules(_intake(run)["rules"])


# --- 02–04 ------------------------------------------------------------------------------------------


def step_split(run: RunFolder) -> Document:
    document = read_document(Path(_intake(run)["source_path"]))
    run.write_document(UNITS_FILE, document)
    return document


def step_check_rules(run: RunFolder) -> list[Finding]:
    findings = run_rule_checks(run.read_document(UNITS_FILE), _rules(run))
    run.write_findings(f"{FINDINGS_DIR}/rules.json", findings)
    return findings


def step_check_language(run: RunFolder, options: Options) -> list[Finding]:
    instruction = load_instruction(language_check.INSTRUCTION_FILE)
    document = run.read_document(UNITS_FILE)
    checks = language_check.run_language_checks(document, instruction, options.agent, options.max_parallel)
    for check in checks:
        run.write_findings(f"{FINDINGS_DIR}/llm_{check.unit_id}.json", list(check.result.findings))
    run.write_json(
        f"{FINDINGS_DIR}/agent_status.json",
        [
            {
                "unit_id": c.unit_id,
                "label": c.label,
                "error": c.result.error,
                "rejected": c.result.rejected,
                "cost_usd": c.result.cost_usd,
            }
            for c in checks
        ],
    )
    return [finding for check in checks for finding in check.result.findings]


def _agent_status(run: RunFolder) -> list[dict[str, Any]]:
    path = run.path / FINDINGS_DIR / "agent_status.json"
    return list(run.read_json(f"{FINDINGS_DIR}/agent_status.json")) if path.is_file() else []


def step_collect(run: RunFolder, options: Options) -> list[Finding]:
    document = run.read_document(UNITS_FILE)
    groups = [run.read_findings(f"{FINDINGS_DIR}/rules.json")]
    llm_files = sorted((run.path / FINDINGS_DIR).glob("llm_*.json"))
    groups += [run.read_findings(f"{FINDINGS_DIR}/{path.name}") for path in llm_files]
    statuses = _agent_status(run)
    cost = sum(status["cost_usd"] for status in statuses)
    rejected = sum(status["rejected"] for status in statuses)
    term_error = None
    if options.use_llm:
        instruction = load_instruction(collect_step.INSTRUCTION_FILE)
        term = collect_step.run_term_consistency(document, instruction, options.agent)
        groups.append(list(term.findings))
        cost, rejected, term_error = cost + term.cost_usd, rejected + term.rejected, term.error
    findings = collect_step.collect(document, groups)
    run.write_findings(COLLECTED_FILE, findings)
    run.write_json(
        META_FILE,
        {
            "unchecked_units": [s["label"] for s in statuses if s["error"]],
            "term_consistency_error": term_error,
            "rejected_agent_findings": rejected,
            "cost_usd": round(cost, 4),
            "language_checked": options.use_llm,
        },
    )
    return findings


def analyse(run: RunFolder, options: Options) -> list[Finding]:
    step_split(run)
    step_check_rules(run)
    if options.use_llm:
        step_check_language(run, options)
    return step_collect(run, options)


# --- 05/06 ------------------------------------------------------------------------------------------


def decision_file(round_number: int) -> str:
    return DECISION_FILE if round_number == 1 else f"05_decision_{round_number}.json"


def _rows_to_json(rows: list[ReportRow]) -> list[dict[str, Any]]:
    return [{"finding": to_dict(r.finding), "status": r.status, "note": r.note} for r in rows]


def _rows_from_json(data: list[dict[str, Any]]) -> list[ReportRow]:
    return [ReportRow(finding_from_dict(item["finding"]), item["status"], item["note"]) for item in data]


def correction_round(
    run: RunFolder,
    round_number: int,
    current: Path,
    findings: list[Finding],
    decision: Decision,
    options: Options,
    earlier_rows: tuple[ReportRow, ...] = (),
) -> tuple[list[ReportRow], list[ReportRow], Path]:
    """Apply one decision to the copy and re-check it. Returns (rows for this round, re-check rows, copy).

    earlier_rows: rows from previous rounds, so findings already reported are not reported again as new.
    """
    intake = _intake(run)
    source = Path(intake["source_path"])
    target = corrected_path(run.path, source)
    outcome = apply_decision(current, target, intake["file_type"], findings, decision)
    run.write_json(f"06a_applied_{round_number}.json", outcome)
    rows = status_rows(findings, decision, outcome)
    recheck_run = RunFolder(run.path / f"recheck_{round_number}")
    recheck_run.path.mkdir(exist_ok=True)
    _write_intake(recheck_run, target, intake["rules"])
    recheck = analyse(recheck_run, options)
    all_rows = [*earlier_rows, *rows]
    first_id = max((int(row.finding.finding_id[1:]) for row in all_rows), default=0) + 1
    labelled = label_recheck(all_rows, recheck, first_id)
    run.write_json(f"06a_recheck_{round_number}.json", _rows_to_json(labelled))
    return rows, labelled, target


def _with_round_labels(rows: list[ReportRow], labels: dict[str, str]) -> list[ReportRow]:
    return [
        ReportRow(
            row.finding, row.status, "; ".join(filter(None, [labels.get(row.finding.finding_id), row.note]))
        )
        for row in rows
    ]


def run_rounds(
    run: RunFolder, findings: list[Finding], gate: Gate, options: Options
) -> tuple[list[ReportRow], Path | None]:
    current = Path(_intake(run)["source_path"])
    rows: list[ReportRow] = []
    labels: dict[str, str] = {}
    corrected: Path | None = None
    for round_number in range(1, MAX_CORRECTION_ROUNDS + 1):
        decision = gate(findings, round_number)
        run.write_json(decision_file(round_number), decision.to_dict())
        if decision.mode == "report" or not decision.accepted:
            return [*rows, *_with_round_labels(status_rows(findings, decision, {}), labels)], corrected
        round_rows, recheck, corrected = correction_round(
            run, round_number, current, findings, decision, options, tuple(rows)
        )
        rows = [*rows, *_with_round_labels(round_rows, labels)]
        current = corrected
        if not recheck:
            return rows, corrected
        if round_number == MAX_CORRECTION_ROUNDS:
            return [*rows, *recheck], corrected
        labels = {row.finding.finding_id: f"{row.status} im Re-Check {round_number}" for row in recheck}
        findings = [row.finding for row in recheck]
    return rows, corrected


# --- 06b --------------------------------------------------------------------------------------------


def rows_from_folder(run: RunFolder) -> list[ReportRow]:
    """Rebuild report rows from step files, for `run-step report` after single steps."""
    if (run.path / ROWS_FILE).is_file():
        return _rows_from_json(run.read_json(ROWS_FILE))
    findings = run.read_findings(COLLECTED_FILE)
    has_decision = (run.path / DECISION_FILE).is_file()
    decision = Decision(**run.read_json(DECISION_FILE)) if has_decision else Decision("report")
    applied = run.path / "06a_applied_1.json"
    outcome = run.read_json(applied.name) if applied.is_file() else {}
    rows = status_rows(findings, Decision(decision.mode, tuple(decision.accepted)), outcome)
    recheck = run.path / "06a_recheck_1.json"
    return [*rows, *(_rows_from_json(run.read_json(recheck.name)) if recheck.is_file() else [])]


def step_report(run: RunFolder, rows: list[ReportRow], corrected: Path | None) -> tuple[Path, Path]:
    run.write_json(ROWS_FILE, _rows_to_json(rows))
    intake = _intake(run)
    meta = run.read_json(META_FILE) if (run.path / META_FILE).is_file() else {}
    warnings = []
    if corrected is not None and intake["file_type"] == "xlsx":
        warnings.append(XLSX_WARNING)
    if not meta.get("language_checked", True):
        warnings.append(NO_LLM_WARNING)
    context = ReportContext(
        source_name=Path(intake["source_path"]).name,
        unchecked_units=tuple(meta.get("unchecked_units", ())),
        corrected_file=str(corrected) if corrected else None,
        warnings=tuple(warnings),
    )
    return write_reports(run.path, REPORT_STEM, rows, context)


def run_pipeline(
    source: Path, rules_path: Path, runs_dir: Path, gate: Gate, options: Options
) -> PipelineResult:
    run = step_intake(source, rules_path, runs_dir)
    findings = analyse(run, options)
    rows, corrected = run_rounds(run, findings, gate, options)
    reports = step_report(run, rows, corrected)
    return PipelineResult(run.path, reports, corrected, tuple(rows))
