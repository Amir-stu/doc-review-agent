"""Step 06b: the Prüfliste as a filterable Excel table and a Markdown file."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font
from openpyxl.utils import get_column_letter

from docreview.correct import ReportRow

HEADERS = ("Nr.", "Fundstelle", "Kategorie", "Schwere", "Sicherheit", "Befund", "Original", "Vorschlag", "Status")
COLUMN_WIDTHS = (7, 45, 14, 9, 11, 50, 30, 30, 28)
CATEGORY_LABELS = {
    "spelling": "Rechtschreibung",
    "wording": "Formulierung",
    "formatting": "Formatierung",
    "consistency": "Konsistenz",
    "file_specific": "Dateispezifisch",
}
SEVERITY_LABELS = {"high": "hoch", "medium": "mittel", "low": "niedrig"}
CONFIDENCE_LABELS = {"certain": "sicher", "probable": "wahrscheinlich"}
XLSX_WARNING = (
    "Excel-Kopie: openpyxl entfernt beim Speichern Diagramme, Bilder und zwischengespeicherte Formelergebnisse. "
    "Kopie vor dem Versand einmal in Excel öffnen und speichern."
)


@dataclass(frozen=True)
class ReportContext:
    source_name: str
    unchecked_units: tuple[str, ...] = ()
    corrected_file: str | None = None
    warnings: tuple[str, ...] = ()


def _cells(row: ReportRow) -> tuple[str, ...]:
    finding = row.finding
    status = f"{row.status} ({row.note})" if row.note else row.status
    return (
        finding.finding_id,
        finding.locator,
        CATEGORY_LABELS[finding.category],
        SEVERITY_LABELS[finding.severity],
        CONFIDENCE_LABELS[finding.confidence],
        finding.description,
        finding.original,
        finding.suggestion,
        status,
    )


def write_xlsx_report(path: Path, rows: list[ReportRow]) -> Path:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Prüfliste"
    sheet.append(HEADERS)
    for cell in sheet[1]:
        cell.font = Font(bold=True)
    for row in rows:
        sheet.append(_cells(row))
    for index, width in enumerate(COLUMN_WIDTHS, start=1):
        sheet.column_dimensions[get_column_letter(index)].width = width
        for cell in sheet[get_column_letter(index)]:
            cell.alignment = Alignment(wrap_text=True, vertical="top")
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = sheet.dimensions
    workbook.save(str(path))
    return path


def _escape(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def _summary_lines(rows: list[ReportRow], context: ReportContext) -> list[str]:
    by_category = Counter(CATEGORY_LABELS[row.finding.category] for row in rows)
    by_severity = Counter(SEVERITY_LABELS[row.finding.severity] for row in rows)
    by_status = Counter(row.status for row in rows)
    lines = [
        f"# Prüfliste: {context.source_name}",
        "",
        f"**{len(rows)} Befunde.** "
        + " · ".join(f"{label}: {count}" for label, count in sorted(by_category.items())),
        "",
        "Schwere: " + " · ".join(f"{label}: {by_severity[label]}" for label in SEVERITY_LABELS.values()),
        "",
        "Status: " + " · ".join(f"{label}: {count}" for label, count in sorted(by_status.items())),
    ]
    if context.corrected_file:
        lines += ["", f"Korrigierte Kopie: `{context.corrected_file}`"]
    if context.unchecked_units:
        lines += ["", "**Nicht sprachlich geprüft** (Agent fehlgeschlagen): " + ", ".join(context.unchecked_units)]
    lines += [f"\n> {warning}" for warning in context.warnings]
    return lines


def write_markdown_report(path: Path, rows: list[ReportRow], context: ReportContext) -> Path:
    table = ["| " + " | ".join(HEADERS) + " |", "|" + "---|" * len(HEADERS)]
    table += ["| " + " | ".join(_escape(cell) for cell in _cells(row)) + " |" for row in rows]
    lines = [*_summary_lines(rows, context), "", *table, ""]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def write_reports(directory: Path, stem: str, rows: list[ReportRow], context: ReportContext) -> tuple[Path, Path]:
    return (
        write_xlsx_report(directory / f"{stem}.xlsx", rows),
        write_markdown_report(directory / f"{stem}.md", rows, context),
    )
