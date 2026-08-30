"""Tests for weighted scoring and the gate fusion.

The rule under test that matters most: the deterministic gate is a veto, not
another weighted input. A proposal that misses a requirement is non-responsive
no matter how well it reads, and no judgment score may overturn that.
"""

import pytest

from colorteam import rubric


def report(**overrides):
    base = {
        "dimensions": {
            "responsiveness":        {"score": 4, "justification": "x", "evidence": "§2.1"},
            "technical_credibility": {"score": 4, "justification": "x", "evidence": "§2.1"},
            "honesty_and_grounding": {"score": 5, "justification": "x", "evidence": "§2.2"},
            "win_theme_clarity":     {"score": 4, "justification": "x", "evidence": "§2.3"},
            "clarity_and_structure": {"score": 4, "justification": "x", "evidence": "§2.4"},
        },
        "sections": [
            {"section": "2.1", "score": 4, "note": ""},
            {"section": "2.2", "score": 4, "note": ""},
        ],
        "revision_notes": ["do the thing"],
    }
    base.update(overrides)
    return base


def test_rubric_weights_sum_to_one():
    spec = rubric.load_rubric()
    total = sum(d["weight"] for d in spec["dimensions"].values())
    assert round(total, 6) == 1.0


def test_weighted_uses_rubric_weights_not_input_weights():
    """A judge that supplies its own weights cannot reweight itself."""
    scores = {name: {"score": 5, "weight": 0.99} for name in rubric.load_rubric()["dimensions"]}
    assert rubric.weighted(scores) == 5.0


def test_weighted_accepts_bare_numbers():
    scores = {name: 3 for name in rubric.load_rubric()["dimensions"]}
    assert rubric.weighted(scores) == 3.0


def test_normalize_maps_one_to_five_onto_zero_to_one():
    assert rubric.normalize(1.0) == 0.0
    assert rubric.normalize(5.0) == 1.0
    assert rubric.normalize(4.0) == 0.75


def test_a_strong_report_passes():
    result = rubric.evaluate(report())
    assert result["passed"] is True
    assert result["normalized"] >= result["threshold"]


def test_a_dimension_at_one_fails_outright():
    data = report()
    data["dimensions"]["win_theme_clarity"]["score"] = 1
    result = rubric.evaluate(data)
    assert result["passed"] is False
    assert result["failing_dimensions"] == ["win_theme_clarity"]


def test_a_section_at_one_fails_outright():
    data = report(sections=[{"section": "2.1", "score": 1, "note": "empty"}])
    result = rubric.evaluate(data)
    assert result["passed"] is False
    assert result["failing_sections"] == ["2.1"]


def test_weak_sections_become_the_worklist_weakest_first():
    data = report(sections=[
        {"section": "2.1", "score": 4, "note": "fine"},
        {"section": "2.2", "score": 2, "note": "thin"},
        {"section": "2.3", "score": 1, "note": "missing"},
    ])
    result = rubric.evaluate(data)
    assert [w["section"] for w in result["worklist"]] == ["2.3", "2.2"]


def test_scores_without_evidence_are_reported_as_unreliable():
    data = report()
    data["dimensions"]["responsiveness"]["evidence"] = "  "
    assert rubric.evaluate(data)["scores_without_evidence"] == ["responsiveness"]


def test_borderline_results_are_flagged_for_a_second_pass():
    data = report()
    data["dimensions"]["win_theme_clarity"]["score"] = 2
    result = rubric.evaluate(data)
    assert result["borderline"] is True


# --- fusion ---------------------------------------------------------------


def test_a_failed_gate_vetoes_a_passing_judgment():
    judgment = rubric.evaluate(report())
    assert judgment["passed"] is True

    gate = {"passed": False, "uncovered": [{"id": "L-009"}], "over_page_limit_by": 0.0}
    fused = rubric.fuse(judgment, gate)

    assert fused["verdict"] == "HOLD"
    assert "1 requirement(s) unaddressed" in fused["blocking"]


def test_a_page_bust_also_vetoes():
    judgment = rubric.evaluate(report())
    gate = {"passed": False, "uncovered": [], "over_page_limit_by": 3.2}
    fused = rubric.fuse(judgment, gate)
    assert fused["verdict"] == "HOLD"
    assert any("page limit" in reason for reason in fused["blocking"])


def test_a_passing_gate_lets_the_judgment_stand():
    fused = rubric.fuse(rubric.evaluate(report()), {"passed": True})
    assert fused["verdict"] == "PASS"
    assert fused["blocking"] == []


def test_a_passing_gate_does_not_rescue_a_weak_judgment():
    data = report()
    data["dimensions"]["technical_credibility"]["score"] = 2
    data["dimensions"]["win_theme_clarity"]["score"] = 2
    fused = rubric.fuse(rubric.evaluate(data), {"passed": True})
    assert fused["verdict"] == "REVISE"
    assert any("below" in reason for reason in fused["blocking"])


def test_fusion_without_a_gate_reports_no_gate():
    fused = rubric.fuse(rubric.evaluate(report()), None)
    assert fused["gate_passed"] is None
    assert fused["verdict"] == "PASS"


def test_render_shows_the_worklist_and_the_veto():
    judgment = rubric.evaluate(report(sections=[{"section": "2.3", "score": 2, "note": "thin"}]))
    text = rubric.render(rubric.fuse(judgment, {"passed": False, "uncovered": [{"id": "x"}]}))
    assert "deterministic gate: HOLD" in text
    assert "verdict: HOLD" in text
    assert "2.3" in text
