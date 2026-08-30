"""Command line entry point.

    colorteam list
    colorteam lint   examples/sample-draft.md
    colorteam lint   draft.docx --record --label "pink team"
    colorteam trend  --document draft.docx
    colorteam run    SHRED --input examples/sample-rfp.md --dry-run
    colorteam run    DRAFT --input outline.md --context rfp.docx --material past-perf.docx
    colorteam run    PINK  --input draft.docx --matrix matrix.md --context rfp.docx
    colorteam run    RED   --input pink-with-comments.docx --knowledge --matrix matrix.md
    colorteam knowledge add --path capability-statement.docx --kind capabilities
    colorteam graphics red-draft.md --out graphics/
    colorteam matrix   export matrix.json -o matrix.xlsx     # correct it in Excel
    colorteam matrix   import matrix.xlsx --against matrix.json
    colorteam coverage --matrix matrix.json --draft draft.docx --pages 25
    colorteam rubric   score judge.json --gate coverage.json
    colorteam assemble --draft red-draft.md --matrix matrix.json -o proposal.docx
    colorteam run    SCORE --input examples/sample-draft.md --context examples/sample-rfp.md
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import lint as lint_mod
from . import assemble, coverage, graphics, knowledge, loaders, matrix as matrix_mod
from . import registry, rubric, runner, trend


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

    # Reviewer comments: an explicit file, or the Word comments in the input.
    if getattr(args, "comments", None):
        extra["reviewer_comments"] = _read(args.comments)
    elif getattr(args, "input", None):
        found = loaders.extract_comments(args.input)
        if found:
            extra["reviewer_comments"] = loaders.format_comments(found)
            print(f"[read {len(found)} reviewer comment(s) from {args.input}]",
                  file=sys.stderr)

    # The evidence base, ranked against whatever this run is working on.
    if getattr(args, "knowledge", False):
        query = " ".join(
            v for k, v in extra.items() if k != "reviewer_comments"
        ) or ""
        packed = knowledge.pack(query=query + " " + _read(args.input)[:4000])
        if packed:
            extra["knowledge"] = packed
        else:
            print("[knowledge base is empty — nothing attached]", file=sys.stderr)
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


def cmd_knowledge(args: argparse.Namespace) -> int:
    if args.action == "init":
        root = knowledge.ensure_layout()
        print(f"knowledge base ready at {root}\n")
        for kind, description in knowledge.KINDS.items():
            print(f"  {kind:<18} {description}")
        print("\nNothing in this folder is committed.")
        return 0

    if args.action == "add":
        if not args.path or not args.kind:
            print("error: add needs --path and --kind", file=sys.stderr)
            return 2
        try:
            destination = knowledge.add(args.path, args.kind)
        except (ValueError, FileNotFoundError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        print(f"added {destination}")
        return 0

    entries = knowledge.manifest()
    if args.json:
        print(json.dumps(entries, indent=2))
        return 0
    if not entries:
        print("knowledge base is empty. Run: colorteam knowledge init")
        return 0
    total = sum(e["words"] for e in entries)
    print(f"{len(entries)} source(s), {total:,} words\n")
    width = max(len(e["kind"]) for e in entries)
    for entry in entries:
        print(f"  {entry['kind']:<{width}}  {entry['words']:>7,}w  {entry['file']}")
    return 0


def cmd_graphics(args: argparse.Namespace) -> int:
    markdown = _read(args.input)
    figures = graphics.extract(markdown)
    if not figures:
        print("no mermaid figures found in this draft", file=sys.stderr)
        return 1

    out_dir = Path(args.out)
    graphics.write_sources(figures, out_dir)
    page = out_dir / "graphics.html"
    page.write_text(graphics.build_page(figures, title=f"Graphics — {Path(args.input).name}"),
                    encoding="utf-8")

    svgs = graphics.render_svgs(figures, out_dir) if args.svg else []

    print(f"{len(figures)} figure(s) → {out_dir}/")
    for figure in figures:
        flag = "  ← caption is a label, not an argument" if figure.caption_is_a_label else ""
        print(f"  {figure.slug}.mmd  {figure.title}{flag}")
    print(f"\nopen {page} to review them rendered")
    if args.svg and not svgs:
        print("(mermaid-cli not installed; skipped SVG export)", file=sys.stderr)
    return 0


def cmd_matrix(args: argparse.Namespace) -> int:
    if args.action == "export":
        rows = matrix_mod.load(args.input)
        if not rows:
            print(f"error: no requirement rows found in {args.input}", file=sys.stderr)
            return 2
        out = Path(args.out or "matrix.xlsx")
        matrix_mod.export_workbook(rows, out)
        print(f"{len(rows)} requirement(s) → {out}")
        print("Correct it in Excel, then read it back with: "
              f"colorteam matrix import {out}")
        return 0

    if args.action == "import":
        rows, report = matrix_mod.import_workbook(args.input)
        out = Path(args.out or "matrix.json")
        matrix_mod.save_json(rows, out)

        print(f"{report['total']} row(s) read, {report['live']} live → {out}")
        if report["added_by_hand"]:
            print(f"  added by hand: {', '.join(report['added_by_hand'])}")
        if report["rejected"]:
            print(f"  rejected by reviewer ({len(report['rejected'])}):")
            for item in report["rejected"]:
                note = f" — {item['note']}" if item["note"] else ""
                print(f"    {item['id']}  [{item['flag']}]{note}")
        if report["with_notes"]:
            print(f"  carrying reviewer notes: {', '.join(report['with_notes'])}")

        if args.against:
            before = matrix_mod.load(args.against)
            changes = matrix_mod.diff(before, rows)
            if changes["edited"]:
                print(f"  edited ({len(changes['edited'])}):")
                for item in changes["edited"]:
                    print(f"    {item['id']}: {', '.join(item['fields'])}")
            if changes["removed"]:
                print(f"  removed: {', '.join(changes['removed'])}")
        return 0

    # convert: a markdown table from SHRED into json
    rows = matrix_mod.load(args.input)
    out = Path(args.out or "matrix.json")
    matrix_mod.save_json(rows, out)
    print(f"{len(rows)} requirement(s) → {out}")
    return 0


def cmd_coverage(args: argparse.Namespace) -> int:
    rows = matrix_mod.load(args.matrix)
    draft = _read(args.draft)
    report = coverage.check(
        rows, draft, page_limit=args.pages, words_per_page=args.words_per_page
    )
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(coverage.render(report))
    if args.out:
        Path(args.out).write_text(json.dumps(report, indent=2), encoding="utf-8")
    return 0 if report["passed"] else 1


def cmd_rubric(args: argparse.Namespace) -> int:
    if args.action == "show":
        print(Path(rubric.RUBRIC_PATH).read_text(encoding="utf-8"))
        return 0

    if args.action == "schema":
        print(json.dumps(
            {
                "dimensions": {
                    name: {"score": 4, "justification": "...", "evidence": "quote or pointer"}
                    for name in rubric.load_rubric()["dimensions"]
                },
                "sections": [{"section": "2.3 Technical Approach", "score": 3,
                              "note": "what would raise it"}],
                "revision_notes": ["specific, assignable"],
                "overall_comment": "how an evaluator would read it",
            },
            indent=2,
        ))
        return 0

    if not args.input:
        print("error: score needs a judge report (see: colorteam rubric schema)",
              file=sys.stderr)
        return 2

    report = rubric.load_report(args.input)
    judgment = rubric.evaluate(report)
    gate = json.loads(Path(args.gate).read_text(encoding="utf-8")) if args.gate else None
    fused = rubric.fuse(judgment, gate)

    if args.json:
        print(json.dumps(fused, indent=2))
    else:
        print(rubric.render(fused))
    return 0 if fused["verdict"] == "PASS" else 1


def cmd_assemble(args: argparse.Namespace) -> int:
    draft = _read(args.draft)
    rows = matrix_mod.load(args.matrix) if args.matrix else []
    gate = None
    if rows:
        gate = coverage.check(rows, draft, page_limit=args.pages)
    out = assemble.build(draft, rows=rows, coverage=gate, title=args.title,
                         path=args.out)
    markers = assemble.find_markers(draft)
    print(f"→ {out}")
    if rows:
        print(f"  Appendix A: {sum(1 for r in rows if r.live)} requirements")
        print(f"  Appendix B: {gate['covered']}/{gate['requirements_live']} addressed")
    print(f"  Appendix C: {len(markers)} open item(s)"
          + (" — highlighted in the body" if markers else ""))
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

    p_know = sub.add_parser("knowledge", help="manage the evidence base")
    p_know.add_argument("action", choices=["init", "add", "list"], nargs="?",
                        default="list")
    p_know.add_argument("--path", help="file to add")
    p_know.add_argument("--kind", choices=sorted(knowledge.KINDS),
                        help="which kind of evidence it is")
    p_know.add_argument("--json", action="store_true")
    p_know.set_defaults(func=cmd_knowledge)

    p_gfx = sub.add_parser("graphics", help="extract and render the figures in a draft")
    p_gfx.add_argument("input", help="a draft containing ```mermaid figure blocks")
    p_gfx.add_argument("--out", default="graphics", help="output directory")
    p_gfx.add_argument("--svg", action="store_true",
                       help="also write SVGs, if mermaid-cli is installed")
    p_gfx.set_defaults(func=cmd_graphics)

    p_mx = sub.add_parser("matrix", help="the compliance matrix and its round trip")
    p_mx.add_argument("action", choices=["convert", "export", "import"])
    p_mx.add_argument("input", help="markdown table, .json, or a corrected .xlsx")
    p_mx.add_argument("-o", "--out", help="output path")
    p_mx.add_argument("--against", metavar="PATH",
                      help="on import, diff against the matrix you exported")
    p_mx.set_defaults(func=cmd_matrix)

    p_cov = sub.add_parser("coverage",
                           help="deterministic gate: requirement coverage and page math")
    p_cov.add_argument("--matrix", required=True, help="matrix .json, .xlsx, or markdown")
    p_cov.add_argument("--draft", required=True, help="the draft to check")
    p_cov.add_argument("--pages", type=float, help="page limit for the whole document")
    p_cov.add_argument("--words-per-page", type=int, default=coverage.WORDS_PER_PAGE)
    p_cov.add_argument("--json", action="store_true")
    p_cov.add_argument("-o", "--out", help="also write the report as JSON")
    p_cov.set_defaults(func=cmd_coverage)

    p_rub = sub.add_parser("rubric", help="fuse a judge report with the gate")
    p_rub.add_argument("action", choices=["score", "show", "schema"], nargs="?",
                       default="score")
    p_rub.add_argument("input", nargs="?", help="judge report JSON from SCORE")
    p_rub.add_argument("--gate", metavar="PATH",
                       help="coverage report JSON; the gate vetoes the judgment")
    p_rub.add_argument("--json", action="store_true")
    p_rub.set_defaults(func=cmd_rubric)

    p_asm = sub.add_parser("assemble", help="build the .docx with its appendices")
    p_asm.add_argument("--draft", required=True)
    p_asm.add_argument("--matrix", help="matrix for Appendix A and traceability")
    p_asm.add_argument("--pages", type=float, help="page limit, for the traceability note")
    p_asm.add_argument("--title", default="Technical Proposal")
    p_asm.add_argument("-o", "--out", default="proposal.docx")
    p_asm.set_defaults(func=cmd_assemble)

    p_run = sub.add_parser("run", help="run one agent against a document")
    p_run.add_argument("agent", help="agent name, e.g. SHRED")
    p_run.add_argument("--input", required=True, help="the document to process")
    p_run.add_argument("--context", metavar="PATH",
                       help="the solicitation, for agents that evaluate against it")
    p_run.add_argument("--matrix", metavar="PATH",
                       help="a compliance matrix, for agents that check coverage")
    p_run.add_argument("--material", metavar="PATH", action="append",
                       help="source material for DRAFT; repeat for several files")
    p_run.add_argument("--comments", metavar="PATH",
                       help="reviewer feedback; omit and Word comments in --input are used")
    p_run.add_argument("--knowledge", action="store_true",
                       help="attach the ranked evidence base from knowledge/")
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
