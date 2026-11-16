"""Step 06a: apply approved fixes to a copy, then label re-check findings against what was attempted."""

from __future__ import annotations

import shutil
from dataclasses import dataclass, replace
from pathlib import Path

from docreview.models import Finding
from docreview.review import Decision
from docreview.writers.office_writers import WRITERS

CORRECTED_SUFFIX = "_korrigiert"

STATUS_CORRECTED = "korrigiert"
STATUS_REJECTED = "abgelehnt"
STATUS_MANUAL = "manuell"
STATUS_OPEN = "offen"
STATUS_NOT_FIXED = "nicht behoben"
STATUS_NEW = "neu"


@dataclass(frozen=True)
class ReportRow:
    finding: Finding
    status: str
    note: str = ""


def corrected_path(run_dir: Path, source: Path) -> Path:
    return run_dir / f"{source.stem}{CORRECTED_SUFFIX}{source.suffix}"


def apply_decision(
    source: Path, target: Path, file_type: str, findings: list[Finding], decision: Decision
) -> dict[str, str | None]:
    """Copy source to target (unless they are the same file) and apply the accepted fixes to target only."""
    if source.resolve() != target.resolve():
        shutil.copy2(source, target)
    accepted = [f for f in findings if f.finding_id in decision.accepted and f.fix is not None]
    if not accepted:
        return {}
    return WRITERS[file_type](target, accepted)


def status_rows(
    findings: list[Finding], decision: Decision, outcome: dict[str, str | None]
) -> list[ReportRow]:
    rows = []
    for finding in findings:
        if finding.fix is None:
            rows.append(ReportRow(finding, STATUS_MANUAL, "keine automatische Korrektur möglich"))
        elif decision.mode == "report":
            rows.append(ReportRow(finding, STATUS_OPEN))
        elif finding.finding_id not in decision.accepted:
            rows.append(ReportRow(finding, STATUS_REJECTED))
        elif outcome.get(finding.finding_id) is None:
            rows.append(ReportRow(finding, STATUS_CORRECTED))
        else:
            rows.append(
                ReportRow(finding, STATUS_MANUAL, f"Korrektur fehlgeschlagen: {outcome[finding.finding_id]}")
            )
    return rows


def finding_key(finding: Finding) -> tuple[str, str, str]:
    return finding.target_id, finding.original.casefold(), finding.suggestion.casefold()


def label_recheck(previous: list[ReportRow], recheck: list[Finding], first_id: int) -> list[ReportRow]:
    """Keep re-check findings that matter: a fix that did not take effect, or something not seen before.

    Findings already reported (rejected, manual, open) are not repeated.
    """
    corrected = {finding_key(row.finding) for row in previous if row.status == STATUS_CORRECTED}
    seen = {finding_key(row.finding) for row in previous}
    kept = []
    for finding in recheck:
        key = finding_key(finding)
        if key in corrected:
            kept.append((finding, STATUS_NOT_FIXED))
        elif key not in seen:
            kept.append((finding, STATUS_NEW))
    return [
        ReportRow(replace(finding, finding_id=f"F{first_id + index:03d}"), status)
        for index, (finding, status) in enumerate(kept)
    ]
