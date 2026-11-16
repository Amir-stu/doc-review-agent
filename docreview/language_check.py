"""Step 03a: one language subagent per unit (slide / section / sheet), run in parallel."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from docreview.agent_findings import (
    FINDINGS_SCHEMA,
    AgentCheckResult,
    AgentFunction,
    run_checked_agent,
    targets_prompt,
)
from docreview.checks.common import TextTarget, text_targets
from docreview.config import AGENT_BUDGET_USD, LANGUAGE_MODEL
from docreview.instructions import Instruction
from docreview.models import Document, Unit
from docreview.runner import AgentSpec

INSTRUCTION_FILE = "03a_language_check.md"


@dataclass(frozen=True)
class UnitCheck:
    unit_id: str
    label: str
    result: AgentCheckResult


def language_spec(instruction: Instruction) -> AgentSpec:
    return AgentSpec(
        name=instruction.name,
        system_prompt=instruction.body,
        model=instruction.model or LANGUAGE_MODEL,
        json_schema=FINDINGS_SCHEMA,
        max_budget_usd=AGENT_BUDGET_USD,
    )


def _unit_targets(document: Document, unit: Unit) -> dict[str, TextTarget]:
    single = Document(document.file_type, document.source_path, (unit,))
    return {target.target_id: target for target in text_targets(single)}


def check_unit(document: Document, unit: Unit, spec: AgentSpec, agent: AgentFunction) -> UnitCheck:
    targets = _unit_targets(document, unit)
    heading = f"Dokumenttyp: {document.file_type}. Prüfeinheit: {unit.label}."
    result = run_checked_agent(agent, spec, targets_prompt(heading, targets.values()), targets)
    return UnitCheck(unit.unit_id, unit.label, result)


def run_language_checks(
    document: Document, instruction: Instruction, agent: AgentFunction, max_parallel: int
) -> list[UnitCheck]:
    spec = language_spec(instruction)
    units = [unit for unit in document.units if _unit_targets(document, unit)]
    if not units:
        return []
    with ThreadPoolExecutor(max_workers=max(1, max_parallel)) as pool:
        futures = [pool.submit(check_unit, document, unit, spec, agent) for unit in units]
        return [future.result() for future in futures]
