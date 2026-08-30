"""Deterministic language checks for proposal text.

This module runs before any model call. Every finding here is reproducible:
the same input always produces the same output, with a line and column, so
findings can be diffed between drafts and counted over time.

The model-based agents handle judgment (is this responsive? does it score?).
This handles the rules that never need judgment.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterable

import yaml

RULES_PATH = Path(__file__).resolve().parent.parent / "reference" / "style-rules.yaml"

PARTICIPLE = re.compile(r"\b\w+(?:ed|en|wn|ne|un|it)\b", re.IGNORECASE)

# Common irregular past participles the -ed heuristic misses.
IRREGULAR = {
    "built", "brought", "bought", "caught", "dealt", "found", "held", "kept",
    "led", "left", "lost", "made", "meant", "met", "paid", "put", "read",
    "said", "sent", "set", "sought", "sold", "spent", "taught", "told",
}

SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}


@dataclass(frozen=True)
class Finding:
    line: int
    column: int
    category: str
    severity: str
    term: str
    why: str
    excerpt: str

    def as_dict(self) -> dict:
        return asdict(self)

    def format(self) -> str:
        return (
            f"{self.line}:{self.column}  {self.severity.upper():<6} "
            f"{self.category:<10} {self.term!r} — {self.why}"
        )


def load_rules(path: Path | str = RULES_PATH) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _term_pattern(term: str) -> re.Pattern:
    """Word-boundary match that tolerates multi-word terms and hyphens."""
    escaped = r"\s+".join(re.escape(part) for part in term.split())
    return re.compile(rf"(?<!\w){escaped}(?!\w)", re.IGNORECASE)


def _scan_terms(text: str, entries: Iterable[dict], category: str) -> list[Finding]:
    findings: list[Finding] = []
    lines = text.splitlines()
    for entry in entries or []:
        pattern = _term_pattern(entry["term"])
        for lineno, line in enumerate(lines, start=1):
            for match in pattern.finditer(line):
                findings.append(
                    Finding(
                        line=lineno,
                        column=match.start() + 1,
                        category=category,
                        severity=entry.get("severity", "medium"),
                        term=match.group(0),
                        why=entry.get("why", ""),
                        excerpt=line.strip()[:160],
                    )
                )
    return findings


def _scan_passive(text: str, config: dict) -> list[Finding]:
    if not config:
        return []
    be_forms = "|".join(config.get("be_forms", []))
    if not be_forms:
        return []
    pattern = re.compile(
        rf"(?<!\w)(?:{be_forms})\s+(?:\w+ly\s+)?(\w+)(?!\w)", re.IGNORECASE
    )
    findings: list[Finding] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        for match in pattern.finditer(line):
            candidate = match.group(1)
            lowered = candidate.lower()
            if not (PARTICIPLE.fullmatch(candidate) or lowered in IRREGULAR):
                continue
            findings.append(
                Finding(
                    line=lineno,
                    column=match.start() + 1,
                    category="passive",
                    severity=config.get("severity", "low"),
                    term=match.group(0).strip(),
                    why=config.get("why", "Passive construction."),
                    excerpt=line.strip()[:160],
                )
            )
    return findings


def lint(text: str, rules: dict | None = None) -> list[Finding]:
    """Return every finding in `text`, sorted by severity then position."""
    rules = rules or load_rules()
    findings: list[Finding] = []
    findings += _scan_terms(text, rules.get("prohibited"), "prohibited")
    findings += _scan_terms(text, rules.get("overclaim"), "overclaim")
    findings += _scan_terms(text, rules.get("hedge"), "hedge")
    findings += _scan_passive(text, rules.get("passive", {}))
    findings.sort(key=lambda f: (SEVERITY_ORDER.get(f.severity, 9), f.line, f.column))
    return findings


def summarize(text: str, findings: list[Finding], rules: dict | None = None) -> dict:
    """Counts and a pass/fail against the thresholds in style-rules.yaml."""
    rules = rules or load_rules()
    thresholds = rules.get("thresholds", {})
    words = max(len(text.split()), 1)
    per_k = lambda n: round(n * 1000 / words, 2)  # noqa: E731

    counts = {"high": 0, "medium": 0, "low": 0}
    by_category: dict[str, int] = {}
    for finding in findings:
        counts[finding.severity] = counts.get(finding.severity, 0) + 1
        by_category[finding.category] = by_category.get(finding.category, 0) + 1

    high_rate = per_k(counts["high"])
    medium_rate = per_k(counts["medium"])
    gate_pass = (
        high_rate <= thresholds.get("high_per_kwords", 0)
        and medium_rate <= thresholds.get("medium_per_kwords", 3)
    )

    return {
        "word_count": words,
        "total_findings": len(findings),
        "by_severity": counts,
        "by_category": by_category,
        "high_per_1k_words": high_rate,
        "medium_per_1k_words": medium_rate,
        "ready_for_color_review": gate_pass,
    }
