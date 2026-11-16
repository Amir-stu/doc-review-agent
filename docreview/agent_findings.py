"""Turns subagent output into Findings, and rejects anything the agent cannot back with the document's text."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

import jsonschema

from docreview.checks.common import TextTarget
from docreview.config import AGENT_ATTEMPTS
from docreview.models import Finding, Fix
from docreview.runner import AgentError, AgentResult, AgentSpec, UsageLimitError

AgentFunction = Callable[[AgentSpec, str], AgentResult]

LLM_CATEGORIES = ("spelling", "wording", "consistency")
CERTAIN_CATEGORIES = ("spelling",)

FINDINGS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["findings"],
    "properties": {
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["target_id", "category", "severity", "description", "original", "suggestion"],
                "properties": {
                    "target_id": {"type": "string"},
                    "category": {"enum": list(LLM_CATEGORIES)},
                    "severity": {"enum": ["high", "medium", "low"]},
                    "description": {"type": "string"},
                    "original": {"type": "string", "minLength": 1},
                    "suggestion": {"type": "string"},
                },
            },
        }
    },
}


@dataclass(frozen=True)
class AgentCheckResult:
    findings: tuple[Finding, ...]
    rejected: int
    cost_usd: float
    error: str | None = None


def targets_prompt(heading: str, targets: Iterable[TextTarget]) -> str:
    items = [{"id": t.target_id, "locator": t.locator, "text": t.text} for t in targets]
    return f"{heading}\n\n" + json.dumps({"items": items}, ensure_ascii=False, indent=1)


def to_findings(raw_items: list[dict[str, Any]], targets: dict[str, TextTarget]) -> tuple[list[Finding], int]:
    """Keep only items whose `original` is literally in the referenced text. Returns (findings, rejected)."""
    findings: list[Finding] = []
    rejected = 0
    for item in raw_items:
        target = targets.get(item["target_id"])
        original, suggestion = item["original"], item["suggestion"]
        if target is None or original not in target.text or original == suggestion:
            rejected += 1
            continue
        findings.append(
            Finding(
                unit_id=target.unit_id,
                target_id=target.target_id,
                locator=target.locator,
                category=item["category"],
                severity=item["severity"],
                description=item["description"],
                original=original,
                suggestion=suggestion,
                confidence="certain" if item["category"] in CERTAIN_CATEGORIES else "probable",
                source="llm",
                fix=Fix(kind="replace_text", target_id=target.target_id, old=original, new=suggestion),
            )
        )
    return findings, rejected


def run_checked_agent(
    agent: AgentFunction, spec: AgentSpec, prompt: str, targets: dict[str, TextTarget]
) -> AgentCheckResult:
    """Call the agent up to AGENT_ATTEMPTS times until its output validates. Usage limits are not retried."""
    cost = 0.0
    last_error = "no attempt made"
    for _ in range(AGENT_ATTEMPTS):
        try:
            result = agent(spec, prompt)
        except UsageLimitError:
            raise
        except AgentError as error:
            last_error = str(error)
            continue
        cost += result.cost_usd
        try:
            jsonschema.validate(result.structured, FINDINGS_SCHEMA)
        except jsonschema.ValidationError as error:
            last_error = f"output failed schema validation: {error.message}"
            continue
        assert result.structured is not None
        findings, rejected = to_findings(result.structured["findings"], targets)
        return AgentCheckResult(tuple(findings), rejected, cost)
    return AgentCheckResult((), 0, cost, error=last_error)
