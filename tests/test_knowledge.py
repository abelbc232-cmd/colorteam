"""Tests for the evidence base.

The behaviour that matters here is not "does it read files" but "does a claim
stay attributable". Provenance in the packed block is what lets a drafting agent
cite a source and a reviewer check it, so it is tested directly.
"""

import pytest

from colorteam import knowledge


@pytest.fixture
def base(tmp_path):
    root = knowledge.ensure_layout(tmp_path / "knowledge")
    (root / "capabilities" / "cap-statement.md").write_text(
        "We perform ground terminal sustainment across three geographically "
        "separated sites, including corrective and preventive maintenance.",
        encoding="utf-8",
    )
    (root / "past-performance" / "sustainment-contract.md").write_text(
        "Contract DEMO-19-C-0001. Ground terminal sustainment, 2019 to 2024, "
        "availability held above the contractual threshold every month.",
        encoding="utf-8",
    )
    (root / "pricing" / "rates.md").write_text(
        "Composite labor rates by year for technician and engineer categories.",
        encoding="utf-8",
    )
    return root


def test_init_creates_every_kind(tmp_path):
    root = knowledge.ensure_layout(tmp_path / "kb")
    for kind in knowledge.KINDS:
        assert (root / kind).is_dir()
        assert (root / kind / "README.md").exists()


def test_readmes_are_not_treated_as_evidence(base):
    files = {s.name for s in knowledge.load(root=base)}
    assert "README.md" not in files


def test_load_reads_every_kind(base):
    kinds = {s.kind for s in knowledge.load(root=base)}
    assert kinds == {"capabilities", "past-performance", "pricing"}


def test_load_can_be_narrowed_to_one_kind(base):
    sources = knowledge.load(kinds=["pricing"], root=base)
    assert len(sources) == 1
    assert sources[0].kind == "pricing"


def test_rank_puts_the_relevant_source_first(base):
    sources = knowledge.load(root=base)
    ordered = knowledge.rank(sources, "availability threshold on a prior contract")
    assert ordered[0][0].name == "sustainment-contract.md"
    assert ordered[0][1] > 0


def test_pack_carries_provenance(base):
    packed = knowledge.pack(query="ground terminal sustainment", root=base)
    assert 'kind="capabilities"' in packed
    assert 'file="cap-statement.md"' in packed
    assert "Cite the file name" in packed


def test_pack_states_the_grounding_rule(base):
    packed = knowledge.pack(query="anything", root=base)
    assert "ONLY sources you may draw facts from" in packed


def test_pack_is_empty_when_the_base_is(tmp_path):
    knowledge.ensure_layout(tmp_path / "kb")
    assert knowledge.pack(query="anything", root=tmp_path / "kb") == ""


def test_pack_respects_the_character_budget(base):
    packed = knowledge.pack(query="sustainment", max_chars=200, root=base)
    assert len(packed) < 1500  # header plus one small excerpt, not everything


def test_excerpt_keeps_document_order(base):
    source = knowledge.load(kinds=["past-performance"], root=base)[0]
    long_source = knowledge.Source(
        path=source.path,
        kind=source.kind,
        text="Alpha paragraph about availability.\n\nBravo filler.\n\n"
             "Charlie paragraph about availability.",
    )
    # 80 is under the 89-character total, so the budget actually binds.
    text = knowledge.excerpt(long_source, "availability", max_chars=80)
    assert text.index("Alpha") < text.index("Charlie")
    assert "Bravo" not in text  # lowest overlap, dropped for budget


def test_add_copies_into_the_right_kind(base, tmp_path):
    incoming = tmp_path / "resume.md"
    incoming.write_text("Program manager, 12 years.", encoding="utf-8")
    destination = knowledge.add(incoming, "resumes", root=base)
    assert destination.parent.name == "resumes"
    assert destination.read_text(encoding="utf-8").startswith("Program manager")


def test_add_rejects_an_unknown_kind(base, tmp_path):
    incoming = tmp_path / "x.md"; incoming.write_text("x", encoding="utf-8")
    with pytest.raises(ValueError):
        knowledge.add(incoming, "not-a-kind", root=base)


def test_add_rejects_an_unreadable_format(base, tmp_path):
    incoming = tmp_path / "x.xlsx"; incoming.write_bytes(b"binary")
    with pytest.raises(ValueError):
        knowledge.add(incoming, "pricing", root=base)


def test_manifest_reports_word_counts(base):
    entries = knowledge.manifest(root=base)
    assert len(entries) == 3
    assert all(e["words"] > 0 for e in entries)
