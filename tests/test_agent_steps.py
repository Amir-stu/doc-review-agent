from pathlib import Path

import pytest

from docreview.agent_findings import run_checked_agent, to_findings
from docreview.checks import run_rule_checks
from docreview.checks.common import TextTarget
from docreview.collect import collect, run_term_consistency
from docreview.instructions import InstructionError, load_instruction, parse_instruction
from docreview.language_check import run_language_checks
from docreview.readers import read_document
from docreview.runner import AgentError, AgentResult, AgentSpec, UsageLimitError

INSTRUCTION = parse_instruction("---\nname: t\ndescription: d\nexecutor: agent\n---\nPrüfe.")
TARGETS = {"p0": TextTarget("u", "p0", "Absatz 1", "Das Projeckt ist fertig.")}


def _item(**overrides):
    base = {
        "target_id": "p0",
        "category": "spelling",
        "severity": "medium",
        "description": "Tippfehler",
        "original": "Projeckt",
        "suggestion": "Projekt",
    }
    return {**base, **overrides}


def _result(items):
    return AgentResult(text="", structured={"findings": items}, cost_usd=0.01)


def test_to_findings_when_original_in_text_creates_replace_fix():
    findings, rejected = to_findings([_item()], TARGETS)
    assert rejected == 0
    assert findings[0].fix is not None
    assert (findings[0].fix.old, findings[0].fix.new) == ("Projeckt", "Projekt")
    assert findings[0].confidence == "certain"


@pytest.mark.parametrize(
    "item",
    [_item(original="Projekkt"), _item(target_id="p9"), _item(suggestion="Projeckt")],
)
def test_to_findings_when_unbacked_by_text_rejects(item):
    assert to_findings([item], TARGETS) == ([], 1)


def test_to_findings_when_wording_marks_probable():
    findings, _ = to_findings([_item(category="wording")], TARGETS)
    assert findings[0].confidence == "probable"


def test_run_checked_agent_when_first_output_invalid_retries_once():
    outputs = iter([AgentResult("", {"wrong": 1}, 0.01), _result([_item()])])
    result = run_checked_agent(lambda spec, prompt: next(outputs), _spec(), "p", TARGETS)
    assert len(result.findings) == 1
    assert result.cost_usd == pytest.approx(0.02)


def test_run_checked_agent_when_all_attempts_fail_returns_error():
    def failing(spec, prompt):
        raise AgentError("boom")

    result = run_checked_agent(failing, _spec(), "p", TARGETS)
    assert result.findings == ()
    assert result.error == "boom"


def test_run_checked_agent_when_usage_limit_propagates():
    def limited(spec, prompt):
        raise UsageLimitError("limit")

    with pytest.raises(UsageLimitError):
        run_checked_agent(limited, _spec(), "p", TARGETS)


def _spec():
    return AgentSpec(name="t", system_prompt="s", model="sonnet")


def test_run_language_checks_when_docx_calls_agent_per_section_with_unit_text(fixture_paths):
    document = read_document(fixture_paths["docx"])
    prompts = []

    def fake(spec, prompt):
        prompts.append(prompt)
        if "Projeckt" in prompt:
            return _result([_item(target_id="p1")])
        return _result([])

    checks = run_language_checks(document, INSTRUCTION, fake, max_parallel=2)
    assert [check.unit_id for check in checks] == ["section-0", "section-1"]
    assert len(prompts) == 2
    found = [f for check in checks for f in check.result.findings]
    assert [(f.target_id, f.original) for f in found] == [("p1", "Projeckt")]


def test_run_language_checks_when_xlsx_sends_only_text_cells(fixture_paths):
    document = read_document(fixture_paths["xlsx"])
    prompts = []
    run_language_checks(document, INSTRUCTION, lambda s, p: prompts.append(p) or _result([]), max_parallel=1)
    assert "Gesammt" in prompts[0]
    assert "1200.5" not in prompts[0]


def test_run_term_consistency_when_document_small_sends_all_targets(fixture_paths):
    document = read_document(fixture_paths["pptx"])
    prompts = []
    result = run_term_consistency(document, INSTRUCTION, lambda s, p: prompts.append(p) or _result([]))
    assert result.error is None
    assert "Quartalsbericht Q3" in prompts[0] and "Quelle: interne Auswertung" in prompts[0]


def test_collect_when_rule_and_llm_duplicate_keeps_rule_and_numbers_in_order(fixture_paths, example_rules):
    document = read_document(fixture_paths["pptx"])
    rules = run_rule_checks(document, example_rules)
    term = next(f for f in rules if "Begriff" in f.description)
    duplicate = term.__class__(**{**term.__dict__, "source": "llm"})
    collected = collect(document, [rules, [duplicate]])
    assert len(collected) == len(rules)
    assert [f.finding_id for f in collected][:2] == ["F001", "F002"]
    assert next(f for f in collected if "Begriff" in f.description).source == "rules"
    units = [f.unit_id for f in collected]
    assert units == sorted(units)


def test_load_instruction_when_all_step_files_present_parse(tmp_path: Path):
    for name in ("03a_language_check.md", "04b_term_consistency.md"):
        assert load_instruction(name).executor == "agent"
    with pytest.raises(InstructionError):
        load_instruction("missing.md", tmp_path)


@pytest.mark.parametrize("text", ["no frontmatter", "---\nname: x\n---\nbody"])
def test_parse_instruction_when_malformed_raises(text):
    with pytest.raises(InstructionError):
        parse_instruction(text)


def test_collect_when_llm_span_overlaps_rule_finding_on_same_target_drops_llm(fixture_paths, example_rules):
    document = read_document(fixture_paths["xlsx"])
    rules = run_rule_checks(document, example_rules)
    term = next(f for f in rules if "Begriff" in f.description)
    wider = term.__class__(
        **{**term.__dict__, "source": "llm", "original": "Email-Kampagne", "suggestion": "E-Mail-Kampagne"}
    )
    elsewhere = term.__class__(**{**wider.__dict__, "target_id": "Umsatz!A8"})
    collected = collect(document, [rules, [wider, elsewhere]])
    llm = [f for f in collected if f.source == "llm"]
    assert [f.target_id for f in llm] == ["Umsatz!A8"]
