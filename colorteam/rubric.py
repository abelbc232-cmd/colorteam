"""Fusing the judgment score with the deterministic gate.

SCORE returns a filled-in rubric as JSON. This module turns that into one
verdict and, more usefully, into a worklist: which sections to revise and what
the revision notes are. That worklist is what closes the loop back into RED.

The fusion rule is the important part, and it only goes one way. A strong
judgment score never excuses a deterministic failure — a proposal that misses a
requirement is non-responsive no matter how well it reads. So `fuse` treats the
gate as a veto rather than as another weighted input.
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml

RUBRIC_PATH = Path(__file__).resolve().parent.parent / "reference" / "score-rubric.yaml"


def load_rubric(path: Path | str = RUBRIC_PATH) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def weighted(scores: dict, rubric: dict | None = None) -> float:
    """Weighted score on the 1-5 scale. Weights come from the rubric, not the input."""
    rubric = rubric or load_rubric()
    dimensions = rubric["dimensions"]
    total = 0.0
    weight_sum = 0.0
    for name, spec in dimensions.items():
        entry = scores.get(name)
        if entry is None:
            continue
        value = entry["score"] if isinstance(entry, dict) else entry
        total += spec["weight"] * float(value)
        weight_sum += spec["weight"]
    return round(total / weight_sum, 3) if weight_sum else 0.0


def normalize(weighted_score: float) -> float:
    """Put a 1-5 weighted score on 0-1."""
    return round(max(0.0, (weighted_score - 1) / 4), 3)


def evaluate(report: dict, rubric: dict | None = None) -> dict:
    """Score one judge report against the thresholds."""
    rubric = rubric or load_rubric()
    limits = rubric["thresholds"]

    dimensions = report.get("dimensions", {})
    sections = report.get("sections", [])

    score = weighted(dimensions, rubric)
    normalized = normalize(score)

    def value(entry):
        return float(entry["score"] if isinstance(entry, dict) else entry)

    failing_dimensions = [
        name for name, entry in dimensions.items()
        if value(entry) < limits["no_dimension_below"]
    ]
    failing_sections = [
        s["section"] for s in sections
        if float(s["score"]) < limits["no_section_below"]
    ]
    revise = [
        s for s in sections
        if float(s["score"]) <= limits["revise_at_or_below"]
    ]
    revise.sort(key=lambda s: float(s["score"]))

    missing_evidence = [
        name for name, entry in dimensions.items()
        if isinstance(entry, dict) and not str(entry.get("evidence", "")).strip()
    ]

    passed = (
        normalized >= limits["pass_normalized"]
        and not failing_dimensions
        and not failing_sections
    )
    borderline = abs(normalized - limits["pass_normalized"]) <= limits["borderline_band"]

    return {
        "weighted": score,
        "normalized": normalized,
        "threshold": limits["pass_normalized"],
        "passed": passed,
        "borderline": borderline,
        "failing_dimensions": failing_dimensions,
        "failing_sections": failing_sections,
        "scores_without_evidence": missing_evidence,
        "worklist": [
            {
                "section": s["section"],
                "score": float(s["score"]),
                "note": s.get("note", ""),
            }
            for s in revise
        ],
        "revision_notes": report.get("revision_notes", []),
    }


def fuse(judgment: dict, gate: dict | None = None) -> dict:
    """Combine the judgment verdict with the deterministic gate.

    The gate is a veto. A proposal that misses a requirement or busts a page
    limit is non-responsive regardless of how well it reads, so no judgment
    score can overturn it.
    """
    result = dict(judgment)
    result["gate_passed"] = None if gate is None else bool(gate.get("passed"))

    if gate is not None and not gate.get("passed"):
        result["verdict"] = "HOLD"
        reasons = []
        if gate.get("uncovered"):
            reasons.append(f"{len(gate['uncovered'])} requirement(s) unaddressed")
        if gate.get("over_page_limit_by"):
            reasons.append(f"over the page limit by {gate['over_page_limit_by']}")
        if any(s.get("over") for s in gate.get("section_page_limits", [])):
            reasons.append("a section is over its page limit")
        result["blocking"] = reasons or ["the deterministic gate failed"]
        return result

    result["verdict"] = "PASS" if judgment["passed"] else "REVISE"
    result["blocking"] = []
    if not judgment["passed"]:
        if judgment["failing_dimensions"]:
            result["blocking"].append(
                "dimension at 1: " + ", ".join(judgment["failing_dimensions"])
            )
        if judgment["failing_sections"]:
            result["blocking"].append(
                "section at 1: " + ", ".join(judgment["failing_sections"])
            )
        if judgment["normalized"] < judgment["threshold"]:
            result["blocking"].append(
                f"score {judgment['normalized']} below {judgment['threshold']}"
            )
    return result


def render(fused: dict) -> str:
    lines = [
        f"weighted {fused['weighted']}/5   normalized {fused['normalized']}   "
        f"threshold {fused['threshold']}",
        "",
    ]
    if fused.get("gate_passed") is not None:
        lines.append(f"deterministic gate: {'PASS' if fused['gate_passed'] else 'HOLD'}")
    lines.append(f"verdict: {fused['verdict']}")

    if fused.get("blocking"):
        lines.append("")
        lines.append("blocking:")
        for reason in fused["blocking"]:
            lines.append(f"  - {reason}")

    if fused.get("scores_without_evidence"):
        lines.append("")
        lines.append(
            "scored without evidence (treat as unreliable): "
            + ", ".join(fused["scores_without_evidence"])
        )

    if fused.get("borderline"):
        lines.append("")
        lines.append(
            "borderline — the rubric asks for a second judging pass and an average"
        )

    if fused.get("worklist"):
        lines.append("")
        lines.append("revise, weakest first:")
        for item in fused["worklist"]:
            lines.append(f"  {item['score']:.0f}  {item['section']}")
            if item["note"]:
                lines.append(f"      {item['note']}")

    if fused.get("revision_notes"):
        lines.append("")
        lines.append("notes to feed the revision stage:")
        for note in fused["revision_notes"]:
            lines.append(f"  - {note}")

    return "\n".join(lines)


def load_report(path: Path | str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))
