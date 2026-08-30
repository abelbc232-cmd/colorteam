"""Tests for the no-install Claude Project pack.

The pack is generated, so the property that matters is that it cannot drift
from its sources. Two copies of the same reviewer prompt disagreeing would mean
the person using the Project is running a version of the tool that is not the
version under test.
"""

import pytest

from colorteam import project, registry


def flat(text: str) -> str:
    """Collapse whitespace so prose assertions survive line wrapping."""
    return " ".join(text.split())


@pytest.fixture
def built(tmp_path):
    project.build(tmp_path)
    return tmp_path


def test_builds_every_file(built):
    for name in project.FILES:
        assert (built / name).exists()


def test_every_agent_reaches_the_pack(built):
    text = (built / "knowledge" / "agents.md").read_text(encoding="utf-8")
    for name in registry.load_all():
        assert f"## {name}" in text


def test_agent_prompts_are_carried_verbatim(built):
    """The pack must contain the real prompt, not a summary of it."""
    text = (built / "knowledge" / "agents.md").read_text(encoding="utf-8")
    draft = registry.get("DRAFT")
    assert draft.prompt.strip() in text


def test_instructions_list_the_lifecycle_in_order(built):
    text = (built / "instructions.md").read_text(encoding="utf-8")
    assert " → ".join(registry.load_all()) in text


def test_instructions_carry_the_anti_fabrication_rule(built):
    text = flat((built / "instructions.md").read_text(encoding="utf-8"))
    assert "Never invent a fact" in text
    assert "[PROOF NEEDED:" in text
    assert "Placeholder Manifest" in text


def test_instructions_forbid_chaining_stages(built):
    text = flat((built / "instructions.md").read_text(encoding="utf-8"))
    assert "One stage per turn" in text
    assert "chaining them silently" in text


def test_checks_pack_carries_every_banned_term(built):
    import yaml
    rules = yaml.safe_load((project.REFERENCE / "style-rules.yaml").read_text(encoding="utf-8"))
    text = (built / "knowledge" / "checks.md").read_text(encoding="utf-8")
    for group in ("prohibited", "overclaim", "hedge"):
        for entry in rules[group]:
            assert f"`{entry['term']}`" in text, entry["term"]


def test_checks_pack_states_the_veto(built):
    text = flat((built / "knowledge" / "checks.md").read_text(encoding="utf-8"))
    assert "veto, not a vote" in text


def test_rubric_pack_carries_every_dimension_and_weight(built):
    import yaml
    rubric = yaml.safe_load((project.REFERENCE / "score-rubric.yaml").read_text(encoding="utf-8"))
    text = (built / "knowledge" / "rubric.md").read_text(encoding="utf-8")
    for name, spec in rubric["dimensions"].items():
        assert name in text
        assert str(spec["weight"]) in text


def test_readme_is_honest_about_losing_determinism(built):
    text = flat((built / "README.md").read_text(encoding="utf-8"))
    assert "stop being deterministic" in text


def test_generated_files_say_they_are_generated(built):
    for name in project.FILES:
        assert project.GENERATED in (built / name).read_text(encoding="utf-8")


def test_is_current_detects_a_hand_edit(built):
    assert project.is_current(built)[0] is True
    path = built / "knowledge" / "agents.md"
    path.write_text(path.read_text(encoding="utf-8") + "\nhand edit\n", encoding="utf-8")
    current, stale = project.is_current(built)
    assert current is False
    assert "knowledge/agents.md" in stale


def test_is_current_detects_a_missing_file(built):
    (built / "knowledge" / "rubric.md").unlink()
    current, stale = project.is_current(built)
    assert current is False
    assert any("rubric.md" in name for name in stale)


def test_the_committed_pack_is_current():
    """The pack in the repository must match its sources."""
    current, stale = project.is_current()
    assert current, f"stale: {stale} — run `python -m colorteam project build`"
