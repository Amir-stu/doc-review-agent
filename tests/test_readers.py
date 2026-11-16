from pathlib import Path

import pytest

from docreview.models import document_from_dict, to_dict
from docreview.readers import read_document
from docreview.readers.docx_reader import heading_level
from docreview.readers.xlsx_reader import split_cell_id


def test_read_pptx_when_three_slides_returns_one_unit_per_slide(fixture_paths):
    document = read_document(fixture_paths["pptx"])
    assert [unit.unit_id for unit in document.units] == ["slide-1", "slide-2", "slide-3"]


def test_read_pptx_when_run_has_explicit_font_records_font_size_and_color(fixture_paths):
    document = read_document(fixture_paths["pptx"])
    paragraphs = document.paragraph_index()
    calibri = next(p for p in paragraphs.values() if "Umsatz stieg" in p.text)
    assert calibri.runs[0].font == "Calibri"
    assert calibri.runs[0].size_pt == 18.0
    colored = next(p for p in paragraphs.values() if p.text == "Wichtig")
    assert colored.runs[0].color == "FF00FF"
    assert colored.locator.startswith("Folie 2, Form")


def test_read_pptx_when_textbox_records_container_size_in_points(fixture_paths):
    document = read_document(fixture_paths["pptx"])
    small = [c for c in document.units[1].containers if c.width_pt == 144.0]
    assert len(small) == 1
    assert small[0].height_pt == 36.0


def test_read_docx_when_two_heading1_splits_into_front_and_two_sections(fixture_paths):
    document = read_document(fixture_paths["docx"])
    assert [unit.label for unit in document.units] == ["Abschnitt 0: Einleitung", "Abschnitt 1: Ergebnisse."]


def test_read_docx_when_heading_first_paragraph_is_section_start(fixture_paths):
    document = read_document(fixture_paths["docx"])
    first = document.units[0].paragraphs[0]
    assert first.style == "Heading 1"
    assert first.locator == 'Abschnitt "Einleitung", Absatz 1'


def test_read_docx_when_alignment_set_records_alignment_name(fixture_paths):
    document = read_document(fixture_paths["docx"])
    centered = next(p for p in document.paragraph_index().values() if "pünktlich" in p.text)
    assert centered.alignment == "CENTER"


def test_read_xlsx_when_error_cell_records_error_data_type(fixture_paths):
    document = read_document(fixture_paths["xlsx"])
    cells = document.cell_index()
    assert cells["Umsatz!C2"].data_type == "e"
    assert cells["Umsatz!B2"].number_format == '#,##0.00 "€"'
    assert cells["Umsatz!B6"].value == "1.234"
    assert cells["Umsatz!B6"].locator == 'Blatt "Umsatz", Zelle B6'


def test_read_xlsx_when_formula_cell_uses_cached_value(tmp_path: Path):
    from openpyxl import Workbook

    workbook = Workbook()
    workbook.active["A1"] = 2
    workbook.active["A2"] = "=A1*2"
    workbook.save(tmp_path / "f.xlsx")
    cell = read_document(tmp_path / "f.xlsx").cell_index()["Sheet!A2"]
    assert cell.is_formula is True
    assert cell.value is None  # never calculated by Excel, so no cached value


def test_read_document_when_unsupported_suffix_raises(tmp_path: Path):
    with pytest.raises(ValueError, match="Nicht unterstützter"):
        read_document(tmp_path / "notes.txt")


def test_document_when_serialized_round_trips(fixture_paths):
    for path in fixture_paths.values():
        document = read_document(path)
        assert document_from_dict(to_dict(document)) == document


@pytest.mark.parametrize(
    ("style", "expected"),
    [("Heading 2", 2), ("Überschrift 1", 1), ("Normal", None), (None, None), ("Heading X", None)],
)
def test_heading_level_when_style_name_given_returns_level(style, expected):
    assert heading_level(style) == expected


def test_split_cell_id_when_sheet_has_exclamation_keeps_title():
    assert split_cell_id("Q1!Daten!B3") == ("Q1!Daten", "B3")
