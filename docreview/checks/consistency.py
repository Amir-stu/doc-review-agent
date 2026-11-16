"""Consistency checks on text: date formats, currency notation, percent spacing, preferred terms."""

from __future__ import annotations

import re
from datetime import date

from docreview.checks.common import TextTarget, replace_fix, rule_finding, text_targets
from docreview.models import Document, Finding
from docreview.rules import FormatRules

GERMAN_DATE = re.compile(r"(?<![\d.])(\d{1,2})\.(\d{1,2})\.(\d{4})(?![\d.])")
ISO_DATE = re.compile(r"(?<![\d-])(\d{4})-(\d{2})-(\d{2})(?![\d-])")
US_DATE = re.compile(r"(?<![\d/])(\d{1,2})/(\d{1,2})/(\d{4})(?![\d/])")

AMOUNT = r"\d{1,3}(?:\.\d{3})+(?:,\d{1,2})?|\d+(?:,\d{1,2})?"
CURRENCY = re.compile(
    rf"(?P<pre>€|EUR)\s?(?P<pre_amount>{AMOUNT})(?!\d)|(?<![\d.,])(?P<post_amount>{AMOUNT})\s?(?P<post>€|EUR)(?![A-Za-z])"
)
PERCENT_TIGHT = re.compile(r"(?<![\d,])(\d+(?:,\d+)?)%")
PERCENT_SPACED = re.compile(r"(?<![\d,])(\d+(?:,\d+)?) %")


def _format_date(value: date, date_format: str) -> str:
    if date_format == "YYYY-MM-DD":
        return value.isoformat()
    return value.strftime("%d.%m.%Y")


def _safe_date(year: str, month: str, day: str) -> date | None:
    try:
        return date(int(year), int(month), int(day))
    except ValueError:
        return None


def check_dates(target: TextTarget, rules: FormatRules) -> list[Finding]:
    if rules.date_format is None:
        return []
    candidates = [
        (match.group(0), _safe_date(match.group(3), match.group(2), match.group(1)), "certain")
        for match in GERMAN_DATE.finditer(target.text)
    ]
    candidates += [
        (match.group(0), _safe_date(match.group(1), match.group(2), match.group(3)), "certain")
        for match in ISO_DATE.finditer(target.text)
    ]
    candidates += [
        (match.group(0), _safe_date(match.group(3), match.group(1), match.group(2)), "probable")
        for match in US_DATE.finditer(target.text)
    ]
    findings = []
    for original, parsed, confidence in candidates:
        if parsed is None:
            continue
        expected = _format_date(parsed, rules.date_format)
        if original == expected:
            continue
        findings.append(
            rule_finding(
                target,
                category="consistency",
                severity="medium",
                description=f"Datumsformat weicht von der Vorgabe {rules.date_format} ab",
                original=original,
                suggestion=expected,
                confidence=confidence,  # type: ignore[arg-type]
                fix=replace_fix(target, original, expected),
            )
        )
    return findings


def check_currency(target: TextTarget, rules: FormatRules) -> list[Finding]:
    if rules.currency_symbol is None or rules.currency_position is None:
        return []
    findings = []
    for match in CURRENCY.finditer(target.text):
        amount = match.group("pre_amount") or match.group("post_amount")
        if rules.currency_position == "after":
            expected = f"{amount} {rules.currency_symbol}"
        else:
            expected = f"{rules.currency_symbol} {amount}"
        original = match.group(0)
        if original == expected:
            continue
        findings.append(
            rule_finding(
                target,
                category="consistency",
                severity="low",
                description="Währungsschreibweise weicht von der Vorgabe ab",
                original=original,
                suggestion=expected,
                fix=replace_fix(target, original, expected),
            )
        )
    return findings


def check_percent(target: TextTarget, rules: FormatRules) -> list[Finding]:
    if rules.percent_style is None:
        return []
    spaced = rules.percent_style == "10 %"
    pattern = PERCENT_TIGHT if spaced else PERCENT_SPACED
    findings = []
    for match in pattern.finditer(target.text):
        expected = f"{match.group(1)} %" if spaced else f"{match.group(1)}%"
        findings.append(
            rule_finding(
                target,
                category="consistency",
                severity="low",
                description=f"Prozentschreibweise weicht von der Vorgabe „{rules.percent_style}“ ab",
                original=match.group(0),
                suggestion=expected,
                fix=replace_fix(target, match.group(0), expected),
            )
        )
    return findings


def check_terms(target: TextTarget, rules: FormatRules) -> list[Finding]:
    findings = []
    for variant, preferred in rules.terms.items():
        if variant == preferred:
            continue
        for match in re.finditer(rf"(?<![\w-]){re.escape(variant)}(?!\w)", target.text):
            findings.append(
                rule_finding(
                    target,
                    category="consistency",
                    severity="low",
                    description=f"Begriff „{variant}“ – Vorgabe ist „{preferred}“",
                    original=match.group(0),
                    suggestion=preferred,
                    fix=replace_fix(target, match.group(0), preferred),
                )
            )
    return findings


def check_consistency(document: Document, rules: FormatRules) -> list[Finding]:
    return [
        finding
        for target in text_targets(document)
        for check in (check_dates, check_currency, check_percent, check_terms)
        for finding in check(target, rules)
    ]
