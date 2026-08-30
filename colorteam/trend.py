"""Recording lint results over time.

This is the part that turns a tool into evidence.

A single lint run tells a writer what to fix. A series of them tells a manager
whether the process is improving — which is the only claim worth putting in
front of leadership, and the only one worth putting on a resume. "We cut
high-severity findings per thousand words from 19.3 to 1.4 over six drafts" is
a sentence you can only write if something was counting.

History is an append-only JSONL file. Append-only because the point is the
series, and a file you can rewrite is a series nobody should trust.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_HISTORY = Path(__file__).resolve().parent.parent / "history" / "lint-history.jsonl"

SPARK = "▁▂▃▄▅▆▇█"


def record(
    document: str,
    summary: dict,
    label: str | None = None,
    path: Path | str = DEFAULT_HISTORY,
) -> dict:
    """Append one snapshot and return it."""
    entry = {
        "recorded": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "document": str(document),
        "label": label or "",
        "word_count": summary["word_count"],
        "total_findings": summary["total_findings"],
        "high": summary["by_severity"]["high"],
        "medium": summary["by_severity"]["medium"],
        "low": summary["by_severity"]["low"],
        "high_per_1k_words": summary["high_per_1k_words"],
        "medium_per_1k_words": summary["medium_per_1k_words"],
        "findings_per_1k_words": round(
            summary["total_findings"] * 1000 / max(summary["word_count"], 1), 2
        ),
        "ready_for_color_review": summary["ready_for_color_review"],
    }
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, sort_keys=True) + "\n")
    return entry


def load_history(
    document: str | None = None,
    path: Path | str = DEFAULT_HISTORY,
) -> list[dict]:
    """Read every snapshot, optionally filtered to one document."""
    path = Path(path)
    if not path.exists():
        return []
    entries = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        entry = json.loads(line)
        if document is None or entry["document"] == document:
            entries.append(entry)
    return entries


def sparkline(values: list[float]) -> str:
    """A one-line shape of the series. Flat line when every value is equal."""
    if not values:
        return ""
    low, high = min(values), max(values)
    if high == low:
        return SPARK[0] * len(values)
    span = high - low
    return "".join(
        SPARK[min(int((v - low) / span * (len(SPARK) - 1)), len(SPARK) - 1)]
        for v in values
    )


def delta(entries: list[dict], field: str = "findings_per_1k_words") -> dict | None:
    """Change between the first and last snapshot, as absolute and percent."""
    if len(entries) < 2:
        return None
    first, last = entries[0][field], entries[-1][field]
    change = last - first
    percent = (change / first * 100) if first else 0.0
    return {
        "field": field,
        "first": first,
        "last": last,
        "change": round(change, 2),
        "percent": round(percent, 1),
        "improved": change < 0,
    }


def render(entries: list[dict]) -> str:
    """A compact report: one row per snapshot, then the trend."""
    if not entries:
        return (
            "No history recorded yet.\n\n"
            "Record a snapshot with:\n"
            "  colorteam lint <file> --record --label \"pink team\""
        )

    lines = []
    documents = sorted({e["document"] for e in entries})
    header = f"{len(entries)} snapshot(s) across {len(documents)} document(s)\n"
    lines.append(header)

    lines.append(
        f"  {'date':<12} {'label':<16} {'words':>7} {'high':>5} "
        f"{'med':>5} {'low':>5} {'per 1k':>8}  gate"
    )
    lines.append("  " + "-" * 72)
    for entry in entries:
        date = entry["recorded"][:10]
        gate = "PASS" if entry["ready_for_color_review"] else "HOLD"
        label = (entry["label"] or "—")[:16]
        lines.append(
            f"  {date:<12} {label:<16} {entry['word_count']:>7} "
            f"{entry['high']:>5} {entry['medium']:>5} {entry['low']:>5} "
            f"{entry['findings_per_1k_words']:>8.2f}  {gate}"
        )

    series = [e["findings_per_1k_words"] for e in entries]
    lines.append("")
    lines.append(f"  findings per 1k words  {sparkline(series)}")

    high_series = [e["high_per_1k_words"] for e in entries]
    lines.append(f"  high severity per 1k   {sparkline(high_series)}")

    change = delta(entries)
    if change:
        direction = "down" if change["improved"] else "up"
        lines.append("")
        lines.append(
            f"  Findings per 1k words went {direction} from {change['first']} "
            f"to {change['last']} ({change['percent']:+.1f}%)."
        )
    return "\n".join(lines)
