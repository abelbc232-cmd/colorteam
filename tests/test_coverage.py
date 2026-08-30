"""Tests for the deterministic gate."""

import pytest

from colorteam import coverage
from colorteam.matrix import Requirement

DRAFT = """
## 2.1 Technical Approach

Our approach addresses the sustainment requirement across all three sites.

## 2.2 Management Approach

Staffing is set from measured workload, addressing L-004.

## 2.4 Transition Plan

Transition completes within 45 days.
"""


def rows():
    return [
        Requirement(id="L-001", requirement="Shall not exceed 25 pages.",
                    page_limit="25"),
        Requirement(id="L-003", requirement="Shall describe sustainment.",
                    section="2.1", eval_criterion="M-001"),
        Requirement(id="L-004", requirement="Shall describe staffing.",
                    section="2.2", eval_criterion="M-002"),
        Requirement(id="L-006", requirement="Shall describe transition.",
                    section="2.4", eval_criterion="M-004"),
        Requirement(id="L-009", requirement="Shall describe security.",
                    section="2.9", eval_criterion="M-005"),
    ]


def test_counts_sections_by_heading():
    sections = coverage.split_sections(DRAFT)
    assert [s.heading for s in sections] == [
        "2.1 Technical Approach", "2.2 Management Approach", "2.4 Transition Plan"
    ]


def test_a_document_with_no_headings_is_one_section():
    sections = coverage.split_sections("Just prose.")
    assert len(sections) == 1 and sections[0].heading == "(whole document)"


def test_a_requirement_cited_by_id_counts_as_addressed():
    report = coverage.check(rows(), DRAFT)
    covered = {r["id"] for r in report["uncovered"]}
    assert "L-004" not in covered  # cited literally in the text


def test_a_requirement_whose_section_exists_counts_as_addressed():
    report = coverage.check(rows(), DRAFT)
    assert "L-003" not in {r["id"] for r in report["uncovered"]}


def test_a_requirement_with_no_section_and_no_citation_is_flagged():
    report = coverage.check(rows(), DRAFT)
    assert [r["id"] for r in report["uncovered"]] == ["L-009"]
    assert report["passed"] is False


def test_scored_but_uncovered_is_surfaced_separately():
    report = coverage.check(rows(), DRAFT)
    assert [r["id"] for r in report["scored_but_uncovered"]] == ["L-009"]


def test_a_page_limit_row_is_a_constraint_not_a_content_requirement():
    """'Shall not exceed 25 pages' is satisfied by the page math, not by prose.

    Counting it as unaddressed would report every compliant proposal as
    non-responsive.
    """
    report = coverage.check(rows(), DRAFT)
    assert "L-001" not in {r["id"] for r in report["uncovered"]}
    assert report["constraints"][0]["id"] == "L-001"
    assert report["constraints"][0]["over"] is False
    assert report["requirements_live"] == 4  # the constraint is not counted here


def test_a_document_over_its_stated_limit_fails():
    long_draft = DRAFT + "\n\n" + ("word " * 20000)
    report = coverage.check(rows(), long_draft)
    assert report["constraints"][0]["over"] is True
    assert report["passed"] is False


def test_an_explicit_page_limit_argument_is_enforced():
    report = coverage.check(rows()[1:], "## 2.1 X\n" + ("word " * 6000), page_limit=5)
    assert report["over_page_limit_by"] > 0
    assert report["passed"] is False


def test_page_estimate_uses_the_configured_density():
    report = coverage.check([], "word " * 1000, words_per_page=250)
    assert report["estimated_pages"] == 4.0


def test_flagged_rows_are_excluded_from_coverage():
    data = rows()
    data[4].flag = "mis-extracted"        # the one that was missing
    report = coverage.check(data, DRAFT)
    assert report["uncovered"] == []
    assert report["requirements_excluded"] == 1
    assert report["passed"] is True


def test_a_section_page_limit_is_checked():
    data = [
        Requirement(id="L-020", requirement="Section 2.1 shall not exceed 1 page.",
                    section="2.1", page_limit="1"),
    ]
    draft = "## 2.1 Technical Approach\n\n" + ("word " * 2000)
    report = coverage.check(data, draft)
    assert report["section_page_limits"][0]["over"] is True
    assert report["passed"] is False


def test_full_coverage_passes():
    data = [r for r in rows() if r.id != "L-009"]
    report = coverage.check(data, DRAFT, page_limit=25)
    assert report["coverage_rate"] == 1.0
    assert report["passed"] is True


def test_render_names_the_unaddressed():
    text = coverage.render(coverage.check(rows(), DRAFT))
    assert "UNADDRESSED" in text
    assert "L-009" in text
    assert "[SCORED]" in text
    assert "gate: HOLD" in text


def test_check_is_deterministic():
    first = coverage.check(rows(), DRAFT)
    second = coverage.check(rows(), DRAFT)
    assert first == second
