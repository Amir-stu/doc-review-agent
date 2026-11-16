"""The run folder: every step reads its input from and writes its output to runs/<run-id>/."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from docreview.models import Document, Finding, document_from_dict, finding_from_dict, to_dict

INTAKE_FILE = "01_intake.json"
UNITS_FILE = "02_units.json"
FINDINGS_DIR = "03_findings"
COLLECTED_FILE = "04_findings.json"
DECISION_FILE = "05_decision.json"
REPORT_STEM = "Pruefliste"


@dataclass(frozen=True)
class RunFolder:
    path: Path

    @staticmethod
    def create(runs_dir: Path, source: Path, now: datetime | None = None) -> RunFolder:
        stamp = (now or datetime.now()).strftime("%Y%m%d-%H%M%S")
        path = runs_dir / f"{stamp}_{source.stem}"
        path.mkdir(parents=True, exist_ok=False)
        return RunFolder(path)

    def write_json(self, name: str, data: Any) -> Path:
        target = self.path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return target

    def read_json(self, name: str) -> Any:
        target = self.path / name
        if not target.is_file():
            raise FileNotFoundError(f"{name} fehlt in {self.path} - wurde der vorherige Schritt ausgeführt?")
        return json.loads(target.read_text(encoding="utf-8"))

    def write_document(self, name: str, document: Document) -> Path:
        return self.write_json(name, to_dict(document))

    def read_document(self, name: str) -> Document:
        return document_from_dict(self.read_json(name))

    def write_findings(self, name: str, findings: list[Finding]) -> Path:
        return self.write_json(name, [to_dict(finding) for finding in findings])

    def read_findings(self, name: str) -> list[Finding]:
        return [finding_from_dict(item) for item in self.read_json(name)]
