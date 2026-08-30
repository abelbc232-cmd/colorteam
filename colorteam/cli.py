"""Command line entry point.

    colorteam list
    colorteam lint   examples/sample-draft.md
    colorteam run    SHRED --input examples/sample-rfp.md --dry-run
    colorteam run    SCORE --input examples/sample-draft.md --context examples/sample-rfp.md
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import lint as lint_mod
from . import registry, runner


def _read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


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

    if args.json:
        print(json.dumps(
            {"summary": summary, "findings": [f.as_dict() for f in findings]}, indent=2
        ))
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
    return 0 if summary["ready_for_color_review"] else 1


def cmd_run(args: argparse.Namespace) -> int:
    agent = registry.get(args.agent)
    document = _read(args.input)
    extra = {}
    if args.context:
        extra["solicitation"] = _read(args.context)

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
    p_lint.add_argument("input")
    p_lint.add_argument("--json", action="store_true", help="machine-readable output")
    p_lint.set_defaults(func=cmd_lint)

    p_run = sub.add_parser("run", help="run one agent against a document")
    p_run.add_argument("agent", help="agent name, e.g. SHRED")
    p_run.add_argument("--input", required=True, help="the document to process")
    p_run.add_argument("--context", help="optional solicitation for scoring agents")
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
