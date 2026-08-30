"""Tests for the history and trend reporting.

Every test writes to a tmp_path history file. The real history file is never
touched by the suite — an append-only record that tests append to is not a
record.
"""

import json

import pytest

from colorteam import trend


def make_summary(word_count=1000, high=0, medium=0, low=0, ready=True):
    total = high + medium + low
    return {
        "word_count": word_count,
        "total_findings": total,
        "by_severity": {"high": high, "medium": medium, "low": low},
        "by_category": {},
        "high_per_1k_words": round(high * 1000 / word_count, 2),
        "medium_per_1k_words": round(medium * 1000 / word_count, 2),
        "ready_for_color_review": ready,
    }


@pytest.fixture
def history(tmp_path):
    return tmp_path / "history.jsonl"


def test_record_writes_one_json_line(history):
    trend.record("draft.md", make_summary(high=3, medium=2), path=history)
    lines = history.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["document"] == "draft.md"
    assert entry["high"] == 3
    assert entry["findings_per_1k_words"] == 5.0


def test_history_is_append_only(history):
    trend.record("draft.md", make_summary(high=5), label="pink", path=history)
    trend.record("draft.md", make_summary(high=1), label="red", path=history)
    entries = trend.load_history(path=history)
    assert [e["label"] for e in entries] == ["pink", "red"]


def test_load_history_filters_by_document(history):
    trend.record("a.md", make_summary(high=1), path=history)
    trend.record("b.md", make_summary(high=2), path=history)
    assert len(trend.load_history(path=history)) == 2
    assert len(trend.load_history(document="a.md", path=history)) == 1


def test_load_history_is_empty_when_no_file(tmp_path):
    assert trend.load_history(path=tmp_path / "nothing.jsonl") == []


def test_delta_reports_improvement(history):
    trend.record("d.md", make_summary(high=20, medium=10), path=history)
    trend.record("d.md", make_summary(high=1, medium=2), path=history)
    change = trend.delta(trend.load_history(path=history))
    assert change["improved"] is True
    assert change["first"] == 30.0
    assert change["last"] == 3.0
    assert change["percent"] == -90.0


def test_delta_reports_regression(history):
    trend.record("d.md", make_summary(high=1), path=history)
    trend.record("d.md", make_summary(high=4), path=history)
    change = trend.delta(trend.load_history(path=history))
    assert change["improved"] is False
    assert change["percent"] == 300.0


def test_delta_needs_two_points(history):
    trend.record("d.md", make_summary(high=1), path=history)
    assert trend.delta(trend.load_history(path=history)) is None


def test_sparkline_shapes_the_series():
    assert trend.sparkline([]) == ""
    assert trend.sparkline([5, 5, 5]) == "▁▁▁"
    line = trend.sparkline([1, 5, 10])
    assert len(line) == 3
    assert line[0] == "▁" and line[-1] == "█"


def test_render_explains_itself_when_empty():
    output = trend.render([])
    assert "--record" in output


def test_render_includes_rows_and_direction(history):
    trend.record("d.md", make_summary(high=20, medium=10), label="pink", path=history)
    trend.record("d.md", make_summary(high=1, medium=2), label="red", path=history)
    output = trend.render(trend.load_history(path=history))
    assert "pink" in output and "red" in output
    assert "went down" in output
    assert "-90.0%" in output


# --- CLI context gathering ------------------------------------------------


def test_material_flag_repeats(tmp_path):
    from colorteam import cli

    a = tmp_path / "a.md"; a.write_text("alpha source", encoding="utf-8")
    b = tmp_path / "b.md"; b.write_text("bravo source", encoding="utf-8")

    args = cli.build_parser().parse_args(
        ["run", "DRAFT", "--input", "x.md", "--material", str(a), "--material", str(b)]
    )
    extra = cli._gather_context(args)
    assert "alpha source" in extra["source_material"]
    assert "bravo source" in extra["source_material"]
    # Filenames are kept so the agent can say which source a fact came from.
    assert str(a) in extra["source_material"]


def test_matrix_flag_maps_to_its_own_block(tmp_path):
    from colorteam import cli

    matrix = tmp_path / "m.md"; matrix.write_text("L-014 | shall", encoding="utf-8")
    args = cli.build_parser().parse_args(
        ["run", "PINK", "--input", "d.md", "--matrix", str(matrix)]
    )
    extra = cli._gather_context(args)
    assert extra["compliance_matrix"] == "L-014 | shall"
    assert "solicitation" not in extra
    assert "source_material" not in extra


def test_no_flags_gathers_nothing():
    from colorteam import cli

    args = cli.build_parser().parse_args(["run", "SHRED", "--input", "x.md"])
    assert cli._gather_context(args) == {}
