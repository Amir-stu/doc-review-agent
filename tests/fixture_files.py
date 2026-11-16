"""Builds test documents with seeded errors. SEEDED_* lists what the rule checks must find.

Run as a script to write the fixtures to examples/ for a live end-to-end run:
    .venv/Scripts/python tests/fixture_files.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from docx import Document as new_docx
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt as DocxPt
from docx.shared import RGBColor as DocxRGB
from openpyxl import Workbook
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import MSO_AUTO_SIZE
from pptx.util import Inches, Pt

CURRENCY_FORMAT = '#,##0.00 "€"'

# (unit_id, category, substring of description) the rule checks must report.
SEEDED_PPTX = [
    ("slide-1", "formatting", "Schriftart"),
    ("slide-1", "consistency", "Prozent"),
    ("slide-2", "consistency", "Datum"),
    ("slide-2", "formatting", "Farbe"),
    ("slide-2", "file_specific", "abgeschnitten"),
    ("slide-3", "consistency", "Begriff"),
    ("slide-3", "consistency", "Währung"),
    ("slide-3", "formatting", "Schriftgröße"),
]
SEEDED_DOCX = [
    ("section-0", "formatting", "Schriftart"),
    ("section-0", "consistency", "Datum"),
    ("section-0", "consistency", "Währung"),
    ("section-0", "formatting", "Ausrichtung"),
    ("section-1", "file_specific", "Punkt"),
    ("section-1", "file_specific", "Überschrift ohne Formatvorlage"),
    ("section-1", "file_specific", "Überschriften"),
]
SEEDED_XLSX = [
    ("sheet-Umsatz", "file_specific", "Fehlerwert"),
    ("sheet-Umsatz", "file_specific", "Zahlenformat"),
    ("sheet-Umsatz", "file_specific", "als Text"),
    ("sheet-Umsatz", "consistency", "Begriff"),
]
# Language errors only the LLM step can find.
SEEDED_TYPOS = {"pptx": "verröffentlicht", "docx": "Projeckt", "xlsx": "Gesammt"}


def _textbox(slide, text: str, *, font: str = "Arial", size: float = 18, color: str | None = None,
             width: float = 8.0, height: float = 1.0, top: float = 1.5, fixed_size: bool = False):
    box = slide.shapes.add_textbox(Inches(0.5), Inches(top), Inches(width), Inches(height))
    if fixed_size:
        box.text_frame.word_wrap = True
        box.text_frame.auto_size = MSO_AUTO_SIZE.NONE
    run = box.text_frame.paragraphs[0].add_run()
    run.text = text
    run.font.name = font
    run.font.size = Pt(size)
    if color:
        run.font.color.rgb = RGBColor.from_string(color)
    return box


def build_pptx(path: Path) -> Path:
    presentation = Presentation()
    blank = presentation.slide_layouts[6]
    slide = presentation.slides.add_slide(blank)
    _textbox(slide, "Quartalsbericht Q3", size=32, top=0.3)
    _textbox(slide, "Der Umsatz stieg um 12% im Vergleich zum Vorjahr.", font="Calibri")
    slide = presentation.slides.add_slide(blank)
    _textbox(slide, "Die Ergebnisse wurden am 2026-03-15 verröffentlicht.")
    _textbox(slide, "Wichtig", color="FF00FF", top=3.0)
    _textbox(
        slide,
        "Dieser Text ist viel zu lang für das kleine Textfeld und läuft deshalb über den unteren Rand hinaus "
        "und wird in der Präsentation abgeschnitten dargestellt.",
        width=2.0, height=0.5, top=4.5, fixed_size=True,
    )
    slide = presentation.slides.add_slide(blank)
    _textbox(slide, "Kontakt per Email an das Projektteam.")
    _textbox(slide, "Budget: EUR 1.500", top=3.0)
    _textbox(slide, "Quelle: interne Auswertung", size=8, top=4.5)
    presentation.save(str(path))
    return path


def _docx_paragraph(document, text: str, *, style: str | None = None, font: str | None = None,
                    size: float | None = None, bold: bool | None = None, color: str | None = None):
    paragraph = document.add_paragraph(style=style)
    run = paragraph.add_run(text)
    if font:
        run.font.name = font
    if size:
        run.font.size = DocxPt(size)
    if bold is not None:
        run.bold = bold
    if color:
        run.font.color.rgb = DocxRGB.from_string(color)
    return paragraph


def build_docx(path: Path) -> Path:
    document = new_docx()
    _docx_paragraph(document, "Einleitung", style="Heading 1")
    _docx_paragraph(document, "Das Projeckt startete im Frühjahr mit einem kleinen Team.")
    _docx_paragraph(document, "Der Kickoff fand am 1.3.2026 statt.")
    _docx_paragraph(document, "Das Budget betrug € 200 für Material.", font="Times New Roman")
    centered = _docx_paragraph(document, "Alle Beteiligten waren pünktlich anwesend.")
    centered.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _docx_paragraph(document, "Die Planung war vollständig abgeschlossen.")
    _docx_paragraph(document, "Ergebnisse.", style="Heading 1")
    _docx_paragraph(document, "Umsatz", style="Heading 2", size=14)
    _docx_paragraph(document, "Der Umsatz stieg deutlich.")
    _docx_paragraph(document, "Kosten", style="Heading 2", size=16)
    _docx_paragraph(document, "Die Kosten blieben stabil.")
    _docx_paragraph(document, "Ausblick", bold=True)
    _docx_paragraph(document, "Im nächsten Jahr wird das Team wachsen.")
    document.save(str(path))
    return path


def build_xlsx(path: Path) -> Path:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Umsatz"
    sheet.append(["Region", "Umsatz", "Anteil"])
    rows = [("Nord", 1200.5), ("Süd", 980.0), ("West", 1430.25), ("Ost", 760.0)]
    for region, amount in rows:
        sheet.append([region, amount, None])
    for row in range(2, 5):
        sheet[f"B{row}"].number_format = CURRENCY_FORMAT
    sheet["B5"].number_format = "0.00"
    sheet["C2"] = "#DIV/0!"
    sheet["B6"] = "1.234"
    sheet["A6"] = "Zentrale"
    sheet["A8"] = "Gesammt"
    sheet["A9"] = "Email-Kampagne"
    workbook.save(str(path))
    return path


def build_all(directory: Path) -> dict[str, Path]:
    directory.mkdir(parents=True, exist_ok=True)
    return {
        "pptx": build_pptx(directory / "Quartalsbericht.pptx"),
        "docx": build_docx(directory / "Projektbericht.docx"),
        "xlsx": build_xlsx(directory / "Umsatz.xlsx"),
    }


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent / "examples"
    for file_type, written in build_all(target).items():
        sys.stdout.write(f"{file_type}: {written}\n")
