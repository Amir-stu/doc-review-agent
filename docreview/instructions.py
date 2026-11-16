"""Loads the step instruction files in steps/. Frontmatter = metadata, body = what the step (or subagent) does."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from docreview.config import STEPS_DIR

FRONTMATTER_DELIMITER = "---"


class InstructionError(ValueError):
    """An instruction file is missing or malformed."""


@dataclass(frozen=True)
class Instruction:
    name: str
    description: str
    executor: str
    model: str | None
    body: str


def parse_instruction(text: str) -> Instruction:
    parts = text.split(FRONTMATTER_DELIMITER, 2)
    if len(parts) != 3 or parts[0].strip():
        raise InstructionError("Instruction file must start with a --- frontmatter block")
    meta = yaml.safe_load(parts[1]) or {}
    missing = [key for key in ("name", "description", "executor") if key not in meta]
    if missing:
        raise InstructionError(f"Frontmatter misses {', '.join(missing)}")
    return Instruction(
        name=meta["name"],
        description=meta["description"],
        executor=meta["executor"],
        model=meta.get("model"),
        body=parts[2].strip(),
    )


def load_instruction(file_name: str, steps_dir: Path = STEPS_DIR) -> Instruction:
    path = steps_dir / file_name
    if not path.is_file():
        raise InstructionError(f"Instruction file not found: {path}")
    return parse_instruction(path.read_text(encoding="utf-8"))
