"""Command line entry point.

    colorteam list
    colorteam lint   examples/sample-draft.md
    colorteam lint   draft.docx --record --label "pink team"
    colorteam trend  --document draft.docx
    colorteam run    SHRED --input examples/sample-rfp.md --dry-run
    colorteam run    DRAFT --input outline.md --context rfp.docx --material past-perf.docx
    colorteam run    PINK  --input draft.docx --matrix matrix.md --context rfp.docx
    colorteam run    SCORE --input examples/sample-draft.md --context examples/sample-rfp.md
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import lint as lint_mod
from . import loaders, registry, runner, trend


def _read(path: str) -> str:
    """Load a document, turning loader problems into clean CLI errors."""
    try:
        return loaders.load_document(path)
    except (loaders.UnsupportedDocument, loaders.MissingDependency, FileNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2)


def _gather_context(args: argparse.Namespace) -> dict[str, str]:
    """Collect the named side inputs an agent's frontmatter declares.

    Each flag maps to one tagged block in the prompt, so an agent that declares
    `inputs: [draft, compliance_matrix, solicitation]` receives exactly those
    names. Several source documents collapse into one <source_material> block,
    separated by their filenames so the agent can cite which one it drew from.
    """
    extra: dict[str, str] = {}
    if getattr(args, "context", None):
        extra["solicitation"] = _read(args.context)
    if getattr(args, "matrix", None):
        extra["compliance_matrix"] = _read(args.matrix)
    materials = getattr(args, "material", None) or []
    if materials:
        extra["source_material"] = "\n\n".join(
            f"--- {path} ---\n{_read(path)}" for path in materials
        )
    return extra


def cmd_list(_: argparse.Namespace) -> int:
    agents = registry.load_all()
    width = max(len(name) for name in agents) if agents else 0
    print(f"{len(agents)} agents\n")
    for agent in agents.values():
        print(f"  {agent.name:<{width}}  [{agent.stage}]  {agent.purpose}")
    return 0


def cmd_lint(args: argparse.Namespace) -> int:
    text = _read(args.input)
    findings = lint_mod.lint(text)
    summary = lint_mod.summarize(text, findings)

    if args.record:
        entry = trend.record(args.input, summary, label=args.label)
        recorded = f"[recorded {entry['recorded']}]"
    else:
        recorded = None

    if args.json:
        payload = {"summary": summary, "findings": [f.as_dict() for f in findings]}
        print(json.dumps(payload, indent=2))
        return 0 if summary["ready_for_color_review"] else 1

    print(f"{args.input}: {summary['total_findings']} findings "
          f"in {summary['word_count']} words\n")
    for finding in findings:
        print("  " + finding.format())
    print()
    counts = summary["by_severity"]
    print(f"  high {counts['high']} | medium {counts['medium']} | low {counts['low']}")
    verdict = "PASS" if summary["ready_for_color_review"] else "HOLD"
    print(f"  gate: {verdict} (thresholds in reference/style-rules.yaml)")
    if recorded:
        print(f"  {recorded}", file=sys.stderr)
    return 0 if summary["ready_for_color_review"] else 1


def cmd_trend(args: argparse.Namespace) -> int:
    entries = trend.load_history(document=args.document)
    if args.limit:
        entries = entries[-args.limit:]

    if args.json:
        print(json.dumps(
            {"entries": entries, "delta": trend.delta(entries)}, indent=2
        ))
        return 0

    print(trend.render(entries))
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    try:
        agent = registry.get(args.agent)
    except KeyError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    document = _read(args.input)
    extra = _gather_context(args)

    if args.dry_run:
        payload = runner.assemble(agent, document, extra)
        print("=" * 72)
        print(f"SYSTEM PROMPT — {agent.name}")
        print("=" * 72)
        print(payload["system"])
        print()
        print("=" * 72)
        print("USER MESSAGE")
        print("=" * 72)
        print(payload["user"])
        return 0

    try:
        output = runner.run(agent, document, extra, model=args.model)
    except runner.MissingAPIKey as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(output)
    if args.save:
        path = runner.save_run(agent, output, args.input)
        print(f"\n[saved to {path}]", file=sys.stderr)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="colorteam",
        description="An AI color team for federal proposals.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="show every agent and its lifecycle stage").set_defaults(
        func=cmd_list
    )

    p_lint = sub.add_parser("lint", help="deterministic language check, no API call")
    p_lint.add_argument("input", help="a .md, .txt, or .docx document")
    p_lint.add_argument("--json", action="store_true", help="machine-readable output")
    p_lint.add_argument("--record", action="store_true",
                        help="append this result to the history file")
    p_lint.add_argument("--label", help="name this snapshot, e.g. \"pink team\"")
    p_lint.set_defaults(func=cmd_lint)

    p_trend = sub.add_parser("trend", help="show recorded results over time")
    p_trend.add_argument("--document", help="filter to one document path")
    p_trend.add_argument("--limit", type=int, help="show only the last N snapshots")
    p_trend.add_argument("--json", action="store_true", help="machine-readable output")
    p_trend.set_defaults(func=cmd_trend)

    p_run = sub.add_parser("run", help="run one agent against a document")
    p_run.add_argument("agent", help="agent name, e.g. SHRED")
    p_run.add_argument("--input", required=True, help="the document to process")
    p_run.add_argument("--context", metavar="PATH",
                       help="the solicitation, for agents that evaluate against it")
    p_run.add_argument("--matrix", metavar="PATH",
                       help="a compliance matrix, for agents that check coverage")
    p_run.add_argument("--material", metavar="PATH", action="append",
                       help="source material for DRAFT; repeat for several files")
    p_run.add_argument("--dry-run", action="store_true",
                       help="print the assembled prompt instead of calling the API")
    p_run.add_argument("--save", action="store_true", help="write the output to runs/")
    p_run.add_argument("--model", default=runner.DEFAULT_MODEL)
    p_run.set_defaults(func=cmd_run)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
