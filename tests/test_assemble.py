"""Tests for .docx assembly."""

import pytest

from colorteam import assemble, coverage, loaders
from colorteam.matrix import Requirement

DRAFT = """## 2.1 Technical Approach

Our approach addresses L-003. Availability held at [PROOF NEEDED: monthly rate]
on [PAST PERFORMANCE: comparable contract].

- A bullet with **bold** in it
- Another bullet

## 2.2 Management Approach

Staffing addresses L-004. [SME INPUT: workload basis]
"""


def rows():
    return [
        Requirement(id="L-003", requirement="Shall describe sustainment.",
                    section="2.1", eval_criterion="M-001"),
        Requirement(id="L-004", requirement="Shall describe staffing.",
                    section="2.2", eval_criterion="M-002"),
        Requirement(id="L-009", requirement="Shall describe security.",
                    section="2.9", eval_criterion="M-005"),
        Requirement(id="L-050", requirement="Rejected row.", section="9.9",
                    flag="mis-extracted"),
    ]


def test_finds_every_open_item():
    markers = assemble.find_markers(DRAFT)
    kinds = [m["marker"].split(":")[0].strip("[") for m in markers]
    assert kinds == ["PROOF NEEDED", "PAST PERFORMANCE", "SME INPUT"]


def test_markers_carry_their_section():
    markers = assemble.find_markers(DRAFT)
    assert markers[0]["section"] == "2.1 Technical Approach"
    assert markers[-1]["section"] == "2.2 Management Approach"


def test_builds_a_readable_document(tmp_path):
    pytest.importorskip("docx")
    path = assemble.build(DRAFT, path=tmp_path / "p.docx")
    text = loaders.load_document(path)
    assert "2.1 Technical Approach" in text
    assert "Not for submission" in text


def test_open_items_appendix_lists_every_marker(tmp_path):
    pytest.importorskip("docx")
    path = assemble.build(DRAFT, path=tmp_path / "p.docx")
    text = loaders.load_document(path)
    assert "Appendix C" in text
    assert "PROOF NEEDED" in text
    assert "SME INPUT" in text


def test_a_clean_draft_says_so(tmp_path):
    pytest.importorskip("docx")
    path = assemble.build("## 2.1 X\n\nClean prose.\n", path=tmp_path / "p.docx")
    assert "No open items remain" in loaders.load_document(path)


def test_compliance_matrix_appendix_excludes_rejected_rows(tmp_path):
    pytest.importorskip("docx")
    path = assemble.build(DRAFT, rows=rows(), path=tmp_path / "p.docx")
    text = loaders.load_document(path)
    assert "Appendix A" in text
    assert "L-003" in text
    assert "Rejected row." not in text


def test_traceability_appendix_names_the_gaps(tmp_path):
    pytest.importorskip("docx")
    data = rows()
    gate = coverage.check(data, DRAFT)
    path = assemble.build(DRAFT, rows=data, coverage=gate, path=tmp_path / "p.docx")
    text = loaders.load_document(path)
    assert "Appendix B" in text
    assert "Requirements not yet addressed" in text
    assert "L-009" in text


def test_traceability_says_so_when_nothing_is_missing(tmp_path):
    pytest.importorskip("docx")
    data = [r for r in rows() if r.id in {"L-003", "L-004"}]
    gate = coverage.check(data, DRAFT)
    path = assemble.build(DRAFT, rows=data, coverage=gate, path=tmp_path / "p.docx")
    assert "Every live requirement is addressed" in loaders.load_document(path)


def test_code_fences_do_not_leak_their_backticks(tmp_path):
    pytest.importorskip("docx")
    draft = "## 2.1 X\n\n```mermaid\ngraph TD\nA-->B\n```\n"
    text = loaders.load_document(assemble.build(draft, path=tmp_path / "p.docx"))
    assert "```" not in text
    assert "graph TD" in text
