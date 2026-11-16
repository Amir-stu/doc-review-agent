"""Step 03b: deterministic checks. Everything readable from the file's XML is checked here, not by an LLM."""

from docreview.checks.consistency import check_consistency
from docreview.checks.file_specific import check_file_specific
from docreview.checks.formatting import check_formatting
from docreview.models import Document, Finding
from docreview.rules import FormatRules


def run_rule_checks(document: Document, rules: FormatRules) -> list[Finding]:
    return [
        *check_formatting(document, rules),
        *check_consistency(document, rules),
        *check_file_specific(document),
    ]
