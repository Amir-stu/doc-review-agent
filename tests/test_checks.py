import pytest
from fixture_files import SEEDED_DOCX, SEEDED_PPTX, SEEDED_XLSX

from docreview.checks import run_rule_checks
from docreview.checks.common import TextTarget
from docreview.checks.consistency import check_currency, check_dates, check_percent, check_terms
from docreview.checks.file_specific import estimate_text_height_pt
from docreview.models import Container, Document, Paragraph, TextRun, Unit
from docreview.readers import read_document
from docreview.rules import FormatRules


def _target(text: str) -> TextTarget:
    return TextTarget(unit_id="u", target_id="p0", locator="Absatz 1", text=text)


def _matches(findings, unit_id, category, needle):
    return any(f.unit_id == unit_id and f.category == category and needle in f.description for f in findings)


@pytest.mark.parametrize(("file_type", "seeded"), [("pptx", SEEDED_PPTX), ("docx", SEEDED_DOCX), ("xlsx", SEEDED_XLSX)])
def test_run_rule_checks_when_fixture_has_seeded_errors_finds_all(fixture_paths, example_rules, file_type, seeded):
    findings = run_rule_checks(read_document(fixture_paths[file_type]), example_rules)
    missing = [item for item in seeded if not _matches(findings, *item)]
    assert missing == []


@pytest.mark.parametrize("file_type", ["pptx", "docx", "xlsx"])
def test_run_rule_checks_when_fixture_checked_reports_no_unseeded_findings(fixture_paths, example_rules, file_type):
    seeded = {"pptx": SEEDED_PPTX, "docx": SEEDED_DOCX, "xlsx": SEEDED_XLSX}[file_type]
    findings = run_rule_checks(read_document(fixture_paths[file_type]), example_rules)
    unexpected = [f for f in findings if not any(f.unit_id == u and f.category == c and n in f.description
                                                  for u, c, n in seeded)]
    assert unexpected == []


@pytest.mark.parametrize(
    ("text", "date_format", "expected"),
    [
        ("am 2026-03-15 veröffentlicht", "DD.MM.YYYY", "15.03.2026"),
        ("am 1.3.2026 gestartet", "DD.MM.YYYY", "01.03.2026"),
        ("am 03/15/2026", "DD.MM.YYYY", "15.03.2026"),
        ("am 15.03.2026", "YYYY-MM-DD", "2026-03-15"),
    ],
)
def test_check_dates_when_format_differs_suggests_configured_format(text, date_format, expected):
    findings = check_dates(_target(text), FormatRules(date_format=date_format))
    assert [f.suggestion for f in findings] == [expected]
    assert findings[0].fix is not None and findings[0].fix.new == expected


@pytest.mark.parametrize("text", ["am 15.03.2026", "Version 1.2.3", "am 31.02.2026", "Seite 12"])
def test_check_dates_when_correct_or_not_a_date_returns_nothing(text):
    assert check_dates(_target(text), FormatRules(date_format="DD.MM.YYYY")) == []


@pytest.mark.parametrize(
    ("text", "position", "expected"),
    [
        ("Budget: EUR 1.500", "after", "1.500 €"),
        ("Kosten € 200 gesamt", "after", "200 €"),
        ("Kosten 200€ gesamt", "after", "200 €"),
        ("Kosten 1.234,56 EUR", "before", "€ 1.234,56"),
    ],
)
def test_check_currency_when_style_differs_suggests_configured_style(text, position, expected):
    findings = check_currency(_target(text), FormatRules(currency_symbol="€", currency_position=position))
    assert [f.suggestion for f in findings] == [expected]


def test_check_currency_when_style_matches_returns_nothing():
    rules = FormatRules(currency_symbol="€", currency_position="after")
    assert check_currency(_target("Kosten 1.234,56 € netto"), rules) == []


@pytest.mark.parametrize(
    ("text", "style", "expected"),
    [("um 12% gestiegen", "10 %", "12 %"), ("um 12,5 % gestiegen", "10%", "12,5%")],
)
def test_check_percent_when_spacing_differs_suggests_style(text, style, expected):
    findings = check_percent(_target(text), FormatRules(percent_style=style))
    assert [f.suggestion for f in findings] == [expected]


def test_check_percent_when_style_matches_returns_nothing():
    assert check_percent(_target("um 12 % gestiegen"), FormatRules(percent_style="10 %")) == []


def test_check_terms_when_variant_used_suggests_preferred_with_word_boundary():
    rules = FormatRules(terms={"Email": "E-Mail"})
    findings = check_terms(_target("Per Email oder Emailadresse"), rules)
    assert [(f.original, f.suggestion) for f in findings] == [("Email", "E-Mail")]


def test_estimate_text_height_when_text_wraps_grows_with_length():
    short = estimate_text_height_pt(["kurz"], font_size_pt=18, width_pt=144, word_wrap=True)
    long = estimate_text_height_pt(["x" * 200], font_size_pt=18, width_pt=144, word_wrap=True)
    assert long > short


def test_overflow_when_container_auto_fits_is_skipped(example_rules):
    unit = Unit(
        unit_id="slide-1",
        label="Folie 1",
        paragraphs=(Paragraph("c/p0", "Folie 1", "x" * 400, (TextRun("x" * 400),), container_id="c"),),
        containers=(Container("c", "Folie 1, Form", 100, 20, auto_fit=True),),
    )
    findings = run_rule_checks(Document("pptx", "a.pptx", (unit,)), example_rules)
    assert not any(f.category == "file_specific" for f in findings)


def test_fonts_when_disallowed_offers_fix_to_replacement_font(fixture_paths, example_rules):
    findings = run_rule_checks(read_document(fixture_paths["pptx"]), example_rules)
    font = next(f for f in findings if "Schriftart" in f.description)
    assert font.fix is not None
    assert (font.fix.kind, font.fix.old, font.fix.new) == ("set_font", "Calibri", "Arial")


def test_size_when_below_minimum_offers_fix_to_minimum(fixture_paths, example_rules):
    findings = run_rule_checks(read_document(fixture_paths["pptx"]), example_rules)
    size = next(f for f in findings if "Schriftgröße" in f.description)
    assert size.fix is not None
    assert (size.fix.kind, size.fix.old, size.fix.new) == ("set_font_size", "8.0", "10.0")


def test_number_format_when_minority_in_column_offers_majority_format(fixture_paths, example_rules):
    findings = run_rule_checks(read_document(fixture_paths["xlsx"]), example_rules)
    number = next(f for f in findings if "Zahlenformat" in f.description)
    assert number.target_id == "Umsatz!B5"
    assert number.fix is not None and number.fix.new == '#,##0.00 "€"'


def test_run_rule_checks_when_rules_empty_still_runs_file_specific_checks(fixture_paths):
    findings = run_rule_checks(read_document(fixture_paths["xlsx"]), FormatRules())
    assert any("Fehlerwert" in f.description for f in findings)
    assert not any(f.category == "formatting" for f in findings)
