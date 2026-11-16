"""Data passed between steps. Every object round-trips through JSON in the run folder."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

FileType = Literal["pptx", "docx", "xlsx"]
Category = Literal["spelling", "wording", "formatting", "consistency", "file_specific"]
Severity = Literal["high", "medium", "low"]
Confidence = Literal["certain", "probable"]
Source = Literal["rules", "llm"]


@dataclass(frozen=True)
class TextRun:
    text: str
    font: str | None = None
    size_pt: float | None = None
    color: str | None = None
    bold: bool | None = None


@dataclass(frozen=True)
class Paragraph:
    paragraph_id: str
    locator: str
    text: str
    runs: tuple[TextRun, ...] = ()
    style: str | None = None
    alignment: str | None = None
    space_before_pt: float | None = None
    space_after_pt: float | None = None
    container_id: str | None = None


@dataclass(frozen=True)
class Container:
    """A PowerPoint text box or table cell: the area text must fit into."""

    container_id: str
    locator: str
    width_pt: float | None
    height_pt: float | None
    auto_fit: bool = False
    word_wrap: bool = True


@dataclass(frozen=True)
class Cell:
    cell_id: str
    locator: str
    value: str | float | int | bool | None
    data_type: str
    number_format: str
    is_formula: bool = False


@dataclass(frozen=True)
class Unit:
    unit_id: str
    label: str
    paragraphs: tuple[Paragraph, ...] = ()
    containers: tuple[Container, ...] = ()
    cells: tuple[Cell, ...] = ()


@dataclass(frozen=True)
class Fix:
    """A machine-applicable correction. `kind` decides which other fields are used."""

    kind: Literal["replace_text", "set_font", "set_font_size", "set_number_format"]
    target_id: str
    old: str | None = None
    new: str | None = None


@dataclass(frozen=True)
class Finding:
    unit_id: str
    target_id: str
    locator: str
    category: Category
    severity: Severity
    description: str
    original: str
    suggestion: str
    confidence: Confidence
    source: Source
    fix: Fix | None = None
    finding_id: str = ""


@dataclass(frozen=True)
class Document:
    file_type: FileType
    source_path: str
    units: tuple[Unit, ...] = field(default_factory=tuple)

    def paragraph_index(self) -> dict[str, Paragraph]:
        return {p.paragraph_id: p for unit in self.units for p in unit.paragraphs}

    def cell_index(self) -> dict[str, Cell]:
        return {c.cell_id: c for unit in self.units for c in unit.cells}


def to_dict(obj: Any) -> Any:
    return asdict(obj)


def finding_from_dict(data: dict[str, Any]) -> Finding:
    fix_data = data.get("fix")
    return Finding(**{**data, "fix": Fix(**fix_data) if fix_data else None})


def document_from_dict(data: dict[str, Any]) -> Document:
    return Document(
        file_type=data["file_type"],
        source_path=data["source_path"],
        units=tuple(_unit_from_dict(unit) for unit in data["units"]),
    )


def _unit_from_dict(data: dict[str, Any]) -> Unit:
    return Unit(
        unit_id=data["unit_id"],
        label=data["label"],
        paragraphs=tuple(
            Paragraph(**{**p, "runs": tuple(TextRun(**r) for r in p["runs"])}) for p in data["paragraphs"]
        ),
        containers=tuple(Container(**c) for c in data["containers"]),
        cells=tuple(Cell(**c) for c in data["cells"]),
    )
