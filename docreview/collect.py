"""Step 04: merge rule and agent findings, add the cross-document term check, dedupe, rank, number."""

from __future__ import annotations

from dataclasses import replace

from docreview.agent_findings import (
    FINDINGS_SCHEMA,
    AgentCheckResult,
    AgentFunction,
    run_checked_agent,
    targets_prompt,
)
from docreview.checks.common import text_targets
from docreview.config import AGENT_BUDGET_USD, CONSISTENCY_MAX_CHARS, CONSISTENCY_MODEL, SEVERITY_ORDER
from docreview.instructions import Instruction
from docreview.models import Document, Finding
from docreview.runner import AgentSpec

INSTRUCTION_FILE = "04b_term_consistency.md"
TRUNCATION_NOTE = "(Text gekürzt – nur der Anfang des Dokuments wurde geprüft.)"


def run_term_consistency(
    document: Document, instruction: Instruction, agent: AgentFunction
) -> AgentCheckResult:
    targets = {}
    used = 0
    truncated = False
    for target in text_targets(document):
        if used + len(target.text) > CONSISTENCY_MAX_CHARS:
            truncated = True
            break
        targets[target.target_id] = target
        used += len(target.text)
    if len(targets) < 2:
        return AgentCheckResult((), 0, 0.0)
    spec = AgentSpec(
        name=instruction.name,
        system_prompt=instruction.body,
        model=instruction.model or CONSISTENCY_MODEL,
        json_schema=FINDINGS_SCHEMA,
        max_budget_usd=AGENT_BUDGET_USD,
    )
    heading = f"Dokumenttyp: {document.file_type}. Gesamtes Dokument. {TRUNCATION_NOTE if truncated else ''}"
    return run_checked_agent(agent, spec, targets_prompt(heading.strip(), targets.values()), targets)


def _document_order(document: Document) -> dict[str, int]:
    order: dict[str, int] = {}
    for unit in document.units:
        for paragraph in unit.paragraphs:
            order.setdefault(paragraph.paragraph_id, len(order))
        for cell in unit.cells:
            order.setdefault(cell.cell_id, len(order))
    return order


def _dedupe_key(finding: Finding) -> tuple[str, str, str]:
    return finding.target_id, finding.original.casefold(), finding.suggestion.casefold()


def _overlaps_text_fix(finding: Finding, kept: list[Finding]) -> bool:
    """True if an agent finding edits the same text as an already kept text fix on the same target.

    Applying both would make the second fix fail ("Textstelle nicht mehr vorhanden").
    """
    if finding.source != "llm":
        return False
    original = finding.original.casefold()
    return any(
        other.target_id == finding.target_id
        and other.fix is not None
        and other.fix.kind == "replace_text"
        and (other.original.casefold() in original or original in other.original.casefold())
        for other in kept
    )


def collect(document: Document, finding_groups: list[list[Finding]]) -> list[Finding]:
    """Rule findings should come first in finding_groups: on duplicates the first one wins."""
    unique: dict[tuple[str, str, str], Finding] = {}
    for group in finding_groups:
        for finding in group:
            if _overlaps_text_fix(finding, list(unique.values())):
                continue
            unique.setdefault(_dedupe_key(finding), finding)
    order = _document_order(document)
    ranked = sorted(
        unique.values(),
        key=lambda f: (order.get(f.target_id, len(order)), SEVERITY_ORDER[f.severity], f.category),
    )
    return [replace(finding, finding_id=f"F{index:03d}") for index, finding in enumerate(ranked, start=1)]
