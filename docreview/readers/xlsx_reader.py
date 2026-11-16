"""Step 02 for Excel: one unit per sheet, every non-empty cell with its cached value and number format."""

from __future__ import annotations

from datetime import date, datetime, time
from pathlib import Path
from typing import Any

from openpyxl import load_workbook

from docreview.models import Cell, Document, Unit


def cell_id(sheet_title: str, coordinate: str) -> str:
    return f"{sheet_title}!{coordinate}"


def split_cell_id(identifier: str) -> tuple[str, str]:
    sheet_title, _, coordinate = identifier.rpartition("!")
    return sheet_title, coordinate


def _json_value(value: Any) -> str | float | int | bool | None:
    if isinstance(value, datetime | date | time):
        return value.isoformat()
    if value is None or isinstance(value, str | float | int | bool):
        return value
    return str(value)


def _read_sheet(formula_sheet: Any, value_sheet: Any) -> Unit:
    cells = []
    for row in formula_sheet.iter_rows():
        for formula_cell in row:
            value_cell = value_sheet[formula_cell.coordinate]
            is_formula = formula_cell.data_type == "f"
            value = value_cell.value if is_formula else formula_cell.value
            if value is None and not is_formula:
                continue
            cells.append(
                Cell(
                    cell_id=cell_id(formula_sheet.title, formula_cell.coordinate),
                    locator=f'Blatt "{formula_sheet.title}", Zelle {formula_cell.coordinate}',
                    value=_json_value(value),
                    data_type=value_cell.data_type if is_formula else formula_cell.data_type,
                    number_format=formula_cell.number_format,
                    is_formula=is_formula,
                )
            )
    return Unit(
        unit_id=f"sheet-{formula_sheet.title}", label=f'Blatt "{formula_sheet.title}"', cells=tuple(cells)
    )


def read_xlsx(path: Path) -> Document:
    formulas = load_workbook(str(path))
    values = load_workbook(str(path), data_only=True)
    units = tuple(_read_sheet(formulas[name], values[name]) for name in formulas.sheetnames)
    return Document(file_type="xlsx", source_path=str(path), units=units)
