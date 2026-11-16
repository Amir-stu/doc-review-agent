"""Step 05: the human gate. Nothing is corrected without a recorded decision."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import jsonschema

from docreview.models import Finding

Ask = Callable[[str], str]
Show = Callable[[str], None]
Mode = Literal["correct", "report"]

DECISION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["mode", "accepted"],
    "properties": {
        "mode": {"enum": ["correct", "report"]},
        "accepted": {"type": "array", "items": {"type": "string"}, "uniqueItems": True},
    },
}
MODE_PROMPT = "[k] Korrektur freigeben  ·  [b] Nur Bericht  > "
FINDING_PROMPT = "  Übernehmen? [j]a / [n]ein / [a]lle übrigen / [q] keine weiteren  > "


class DecisionError(ValueError):
    """A decision file has the wrong shape or references unknown findings."""


@dataclass(frozen=True)
class Decision:
    mode: Mode
    accepted: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {"mode": self.mode, "accepted": list(self.accepted)}


def describe(finding: Finding) -> str:
    fix_note = "auto" if finding.fix else "manuell"
    return (
        f"{finding.finding_id} [{finding.severity}/{finding.confidence}/{fix_note}] {finding.locator}\n"
        f"    {finding.description}: „{finding.original}“ → „{finding.suggestion}“"
    )


def _ask_choice(ask: Ask, prompt: str, valid: str) -> str:
    while True:
        answer = ask(prompt).strip().lower()[:1]
        if answer in valid:
            return answer


def _ask_per_finding(fixable: list[Finding], ask: Ask, show: Show) -> tuple[str, ...]:
    accepted: list[str] = []
    for index, finding in enumerate(fixable):
        show(describe(finding))
        answer = _ask_choice(ask, FINDING_PROMPT, "jnaq")
        if answer == "j":
            accepted = [*accepted, finding.finding_id]
        elif answer == "a":
            return (*accepted, *(f.finding_id for f in fixable[index:]))
        elif answer == "q":
            break
    return tuple(accepted)


def interactive_review(findings: list[Finding], ask: Ask, show: Show) -> Decision:
    if not findings:
        show("Keine Befunde.")
        return Decision(mode="report")
    show(f"{len(findings)} Befunde:")
    for finding in findings:
        show(describe(finding))
    fixable = [finding for finding in findings if finding.fix is not None]
    if not fixable:
        show("Keiner der Befunde ist automatisch korrigierbar – es wird nur der Bericht erstellt.")
        return Decision(mode="report")
    if _ask_choice(ask, MODE_PROMPT, "kb") == "b":
        return Decision(mode="report")
    show(f"\n{len(fixable)} Befunde können automatisch korrigiert werden:")
    return Decision(mode="correct", accepted=_ask_per_finding(fixable, ask, show))


def load_decision(path: Path, findings: list[Finding]) -> Decision:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        jsonschema.validate(raw, DECISION_SCHEMA)
    except (OSError, json.JSONDecodeError, jsonschema.ValidationError) as error:
        raise DecisionError(f"Entscheidungsdatei ungültig: {error}") from error
    fixable = {finding.finding_id for finding in findings if finding.fix is not None}
    unknown = [finding_id for finding_id in raw["accepted"] if finding_id not in fixable]
    if unknown:
        raise DecisionError(f"Unbekannte oder nicht korrigierbare Befunde: {', '.join(unknown)}")
    return Decision(mode=raw["mode"], accepted=tuple(raw["accepted"]))
