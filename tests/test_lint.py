"""Tests for the deterministic language checks.

These matter more than they look. The value of the lint layer is that it is
reproducible — if the findings move because the rules file changed, the
before/after numbers a team is tracking become meaningless.
"""

from pathlib import Path

import pytest

from colorteam import lint
from colorteam import registry

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"


@pytest.fixture(scope="module")
def rules():
    return lint.load_rules()


def test_flags_prohibited_guarantee_language(rules):
    findings = lint.lint("Our team will ensure full availability.", rules)
    terms = {f.term.lower() for f in findings}
    assert "ensure" in terms
    assert any(f.severity == "high" for f in findings if f.term.lower() == "ensure")


def test_flags_unsupported_superlatives(rules):
    findings = lint.lint("We offer a comprehensive, best-in-class solution.", rules)
    terms = {f.term.lower() for f in findings}
    assert "comprehensive" in terms
    assert "best-in-class" in terms


def test_flags_hedges(rules):
    findings = lint.lint("We will strive to complete the transition.", rules)
    assert any(f.category == "hedge" for f in findings)


def test_detects_passive_voice(rules):
    findings = lint.lint("The report was submitted by the contractor.", rules)
    assert any(f.category == "passive" for f in findings)


def test_ignores_active_voice(rules):
    findings = lint.lint("The contractor submitted the report.", rules)
    assert not any(f.category == "passive" for f in findings)


def test_matching_is_case_insensitive_and_word_bounded(rules):
    findings = lint.lint("ENSURE this. Reassurance is different.", rules)
    terms = [f.term.lower() for f in findings if f.category == "prohibited"]
    assert terms == ["ensure"]


def test_findings_are_sorted_by_severity(rules):
    text = "This is a robust approach that will ensure success."
    findings = lint.lint(text, rules)
    severities = [lint.SEVERITY_ORDER[f.severity] for f in findings]
    assert severities == sorted(severities)


def test_lint_is_deterministic(rules):
    text = (EXAMPLES / "sample-draft.md").read_text(encoding="utf-8")
    first = [f.as_dict() for f in lint.lint(text, rules)]
    second = [f.as_dict() for f in lint.lint(text, rules)]
    assert first == second


def test_sample_draft_fails_the_gate(rules):
    text = (EXAMPLES / "sample-draft.md").read_text(encoding="utf-8")
    findings = lint.lint(text, rules)
    summary = lint.summarize(text, findings, rules)
    assert summary["by_severity"]["high"] > 0
    assert summary["ready_for_color_review"] is False


def test_clean_text_passes_the_gate(rules):
    text = (
        "The maintenance team performs preventive actions on a 30-day cycle. "
        "Site leads report availability monthly against a 95% threshold. "
        "Contract N00024-22-C-1234 delivered 14 units at 98% on-time performance."
    )
    findings = lint.lint(text, rules)
    summary = lint.summarize(text, findings, rules)
    assert summary["ready_for_color_review"] is True


def test_every_agent_loads_with_valid_frontmatter():
    agents = registry.load_all()
    assert len(agents) == 6
    for agent in agents.values():
        assert agent.name.isupper()
        assert agent.stage
        assert agent.purpose
        assert agent.output
        assert agent.prompt.strip()


def test_agent_references_resolve():
    for agent in registry.load_all().values():
        agent.reference_text()  # raises if a declared reference file is missing


def test_prompt_assembly_includes_document_and_references():
    agent = registry.get("REDLINE")
    prompt = agent.build_prompt("Our team will ensure success.")
    assert "<document>" in prompt
    assert "style-rules.yaml" in prompt
    assert "ensure success" in prompt
