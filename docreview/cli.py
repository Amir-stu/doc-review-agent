"""Command line: `docreview check` runs the whole pipeline, `docreview run-step` runs one box of the diagram."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path

from docreview.config import MAX_PARALLEL_AGENTS, RUNS_DIR
from docreview.correct import ReportRow
from docreview.instructions import InstructionError
from docreview.models import Finding
from docreview.orchestrator import (
    IntakeError,
    Options,
    analyse,
    correction_round,
    rows_from_folder,
    run_pipeline,
    step_check_language,
    step_check_rules,
    step_collect,
    step_intake,
    step_report,
    step_split,
)
from docreview.review import Decision, DecisionError, interactive_review, load_decision
from docreview.rules import RulesError
from docreview.run_folder import COLLECTED_FILE, DECISION_FILE, INTAKE_FILE, RunFolder
from docreview.runner import AgentError

FOLDER_STEPS = ("split", "check-rules", "check-language", "collect", "analyse", "review", "correct", "report")
DEFAULT_RULES = Path(__file__).resolve().parent.parent / "format_rules.example.yaml"


def _show(text: str) -> None:
    sys.stdout.write(text + "\n")


def _ask(prompt: str) -> str:
    sys.stdout.write(prompt)
    sys.stdout.flush()
    return sys.stdin.readline()


def _gate(report_only: bool, decision_path: Path | None):
    def gate(findings: list[Finding], round_number: int) -> Decision:
        if report_only:
            return Decision("report")
        if decision_path is not None:
            return load_decision(decision_path, findings) if round_number == 1 else Decision("report")
        if round_number > 1:
            _show(f"\n--- Re-Check nach Korrekturrunde {round_number - 1} ---")
        return interactive_review(findings, _ask, _show)

    return gate


def _add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--no-llm", action="store_true", help="skip language subagents (rule checks only)")
    parser.add_argument("--parallel", type=int, default=MAX_PARALLEL_AGENTS)
    parser.add_argument("--decision", type=Path, help="decision JSON instead of interactive review")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="docreview", description="Korrekturlesen von PowerPoint, Word, Excel"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("check", help="run the full pipeline")
    check.add_argument("file", type=Path)
    check.add_argument("--rules", type=Path, default=DEFAULT_RULES)
    check.add_argument("--report-only", action="store_true", help="skip the gate, only write the Prüfliste")
    check.add_argument("--runs-dir", type=Path, default=RUNS_DIR)
    _add_common(check)
    step = commands.add_parser("run-step", help="run one step on an existing run folder")
    step.add_argument("step", choices=("intake", *FOLDER_STEPS))
    step.add_argument("target", type=Path, help="input file (intake) or run folder (all other steps)")
    step.add_argument("--rules", type=Path, default=DEFAULT_RULES)
    step.add_argument("--runs-dir", type=Path, default=RUNS_DIR)
    _add_common(step)
    return parser


def _options(args: argparse.Namespace) -> Options:
    return replace(Options(), use_llm=not args.no_llm, max_parallel=args.parallel)


def _print_rows(rows: Sequence[ReportRow]) -> None:
    for row in rows:
        _show(f"{row.finding.finding_id}  {row.status:<14} {row.finding.locator}: {row.finding.description}")


def _run_check(args: argparse.Namespace) -> int:
    result = run_pipeline(
        args.file, args.rules, args.runs_dir, _gate(args.report_only, args.decision), _options(args)
    )
    _show(f"\nRun-Ordner: {result.run_dir}")
    if result.corrected_file:
        _show(f"Korrigierte Kopie: {result.corrected_file}")
    _show(f"Prüfliste: {result.reports[0]}\n           {result.reports[1]}")
    return 0


def _run_folder_step(step: str, run: RunFolder, args: argparse.Namespace) -> int:
    options = _options(args)
    if step == "split":
        document = step_split(run)
        _show(f"{len(document.units)} Einheiten")
    elif step == "check-rules":
        _show(f"{len(step_check_rules(run))} Regelbefunde")
    elif step == "check-language":
        _show(f"{len(step_check_language(run, options))} Sprachbefunde")
    elif step == "collect":
        _show(f"{len(step_collect(run, options))} Befunde gesammelt")
    elif step == "analyse":
        _show(f"{len(analyse(run, options))} Befunde")
    elif step == "review":
        decision = _gate(False, args.decision)(run.read_findings(COLLECTED_FILE), 1)
        run.write_json(DECISION_FILE, decision.to_dict())
        _show(f"Entscheidung: {decision.mode}, {len(decision.accepted)} Korrekturen freigegeben")
    elif step == "correct":
        findings = run.read_findings(COLLECTED_FILE)
        decision = load_decision(run.path / DECISION_FILE, findings)
        source = Path(run.read_json(INTAKE_FILE)["source_path"])
        _, recheck, target = correction_round(run, 1, source, findings, decision, options)
        _show(f"Kopie: {target}")
        _print_rows(recheck)
    else:
        paths = step_report(run, rows_from_folder(run), None)
        _show(f"Prüfliste: {paths[0]}\n           {paths[1]}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "check":
            return _run_check(args)
        if args.step == "intake":
            _show(str(step_intake(args.target, args.rules, args.runs_dir).path))
            return 0
        return _run_folder_step(args.step, RunFolder(args.target), args)
    except (IntakeError, RulesError, DecisionError, InstructionError, AgentError, FileNotFoundError) as error:
        sys.stderr.write(f"Fehler: {error}\n")
        return 2


def entrypoint() -> None:
    raise SystemExit(main())
