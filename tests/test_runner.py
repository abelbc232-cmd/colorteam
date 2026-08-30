"""Tests for prompt assembly and environment loading.

No network calls. The point of these is that the parts you can test without an
API key stay correct — prompt assembly is where agent systems actually break.
"""

import os

import pytest

from colorteam import registry, runner


def test_assemble_returns_system_and_user():
    agent = registry.get("SHRED")
    payload = runner.assemble(agent, "Section L.1 The offeror shall submit.")
    assert payload["system"].startswith("You are a proposal manager")
    assert "<document>" in payload["user"]
    assert "shall submit" in payload["user"]


def test_assemble_includes_declared_references():
    agent = registry.get("SHRED")
    payload = runner.assemble(agent, "text")
    assert 'reference name="compliance-schema.md"' in payload["user"]


def test_assemble_includes_extra_context_blocks():
    agent = registry.get("SCORE")
    payload = runner.assemble(agent, "draft text", {"solicitation": "Section M.1"})
    assert "<solicitation>" in payload["user"]
    assert "Section M.1" in payload["user"]


def test_assemble_states_required_output_shape():
    agent = registry.get("GATE")
    payload = runner.assemble(agent, "text")
    assert "Produce your output as:" in payload["user"]


def test_run_raises_a_clear_error_without_a_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    agent = registry.get("REDLINE")
    with pytest.raises(runner.MissingAPIKey) as exc:
        runner.run(agent, "Our team will ensure success.")
    assert "--dry-run" in str(exc.value)


def test_load_env_does_not_override_existing_variables(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "already-set")
    runner.load_env()
    assert os.environ["ANTHROPIC_API_KEY"] == "already-set"


def test_save_run_writes_provenance_header(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "RUNS_DIR", tmp_path)
    agent = registry.get("DEBRIEF")
    path = runner.save_run(agent, "output body", "examples/sample-rfp.md")
    content = path.read_text(encoding="utf-8")
    assert "agent: DEBRIEF" in content
    assert "source: examples/sample-rfp.md" in content
    assert content.rstrip().endswith("output body")
