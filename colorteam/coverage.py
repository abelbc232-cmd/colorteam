"""The deterministic gate: coverage and page math.

The linter answers "is the language safe." This answers the two questions that
decide whether a proposal is responsive at all, and it answers them the same way
every time, with no model involved:

1. **Is every live requirement addressed somewhere in the draft?**
2. **Does the draft fit the page limits the solicitation imposed?**

Both are pass/fail in source selection and both are arithmetic, so neither
belongs to a model. A requirement is counted as addressed when the draft cites
its ID, or when the outline section it was assigned to exists in the draft with
substantive content under it. That is deliberately generous on *how* a team
tracks coverage and strict on *whether* it does.

Page estimation converts words to pages at a configurable density. It is an
estimate and says so — real pagination depends on the template — but a draft
40% over its limit is over its limit under any template, and finding that out
on Tuesday is worth more than knowing it exactly on Friday.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .matrix import Requirement

# Words per page for a typical federal proposal template: 12pt serif, single
# spaced, one-inch margins, before graphics displace text.
WORDS_PER_PAGE = 500


@dataclass
class SectionCount:
    heading: str
    words: int

    def pages(self, words_per_page: int = WORDS_PER_PAGE) -> float:
        return round(self.words / words_per_page, 2)


HEADING = re.compile(r"^(#{1,6})\s+(.*\S)\s*$", re.MULTILINE)


def split_sections(draft: str) -> list[SectionCount]:
    """Word count per heading, so page math can be done per section."""
    matches = list(HEADING.finditer(draft))
    if not matches:
        return [SectionCount("(whole document)", len(draft.split()))]

    counts = []
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(draft)
        body = draft[start:end]
        counts.append(SectionCount(heading=match.group(2), words=len(body.split())))
    return counts


def _section_key(text: str) -> str:
    """A comparable form of a section reference: '2.3', 'Section 2.3', '2.3 Title'."""
    match = re.search(r"\d+(?:\.\d+)*", text or "")
    return match.group(0) if match else ""


def addressed(requirement: Requirement, draft: str, headings: list[str]) -> tuple[bool, str]:
    """Is this requirement handled? Returns the verdict and how it was decided."""
    if requirement.id and re.search(rf"\b{re.escape(requirement.id)}\b", draft):
        return True, "cited by ID"

    key = _section_key(requirement.section)
    if key:
        for heading in headings:
            if _section_key(heading) == key:
                return True, f"section {key} present"

    return False, "no citation and no matching section"


def check(
    rows: list[Requirement],
    draft: str,
    page_limit: float | None = None,
    words_per_page: int = WORDS_PER_PAGE,
) -> dict:
    """Run the gate. Everything here is reproducible arithmetic."""
    sections = split_sections(draft)
    headings = [s.heading for s in sections]
    live = [r for r in rows if r.live]

    # A row that states a limit rather than an obligation to write something —
    # "the Technical Volume shall not exceed 25 pages" — is satisfied by the
    # page math, not by prose. Counting it as unaddressed would report every
    # compliant proposal as non-responsive.
    constraints = [r for r in live if r.page_limit and not r.section]
    content = [r for r in live if r not in constraints]

    covered, uncovered = [], []
    for requirement in content:
        ok, why = addressed(requirement, draft, headings)
        record = {
            "id": requirement.id,
            "requirement": requirement.requirement[:160],
            "section": requirement.section,
            "eval_criterion": requirement.eval_criterion,
            "why": why,
        }
        (covered if ok else uncovered).append(record)

    # A requirement that is scored but unaddressed is worse than one that is
    # merely mandatory, so it is surfaced separately.
    scored_and_missing = [r for r in uncovered if r["eval_criterion"]]

    words = len(draft.split())
    estimated = round(words / words_per_page, 2)
    over_by = round(estimated - page_limit, 2) if page_limit else 0.0

    document_limits = []
    for requirement in constraints:
        try:
            limit = float(re.sub(r"[^\d.]", "", requirement.page_limit))
        except ValueError:
            continue
        document_limits.append(
            {
                "id": requirement.id,
                "requirement": requirement.requirement[:160],
                "limit_pages": limit,
                "estimated_pages": estimated,
                "over": estimated > limit,
            }
        )

    per_section_limits = []
    for requirement in content:
        if not requirement.page_limit:
            continue
        try:
            limit = float(re.sub(r"[^\d.]", "", requirement.page_limit))
        except ValueError:
            continue
        key = _section_key(requirement.section)
        actual = sum(s.pages(words_per_page) for s in sections if _section_key(s.heading) == key)
        if key and actual:
            per_section_limits.append(
                {
                    "section": requirement.section,
                    "limit_pages": limit,
                    "estimated_pages": round(actual, 2),
                    "over": round(actual - limit, 2) > 0,
                }
            )

    passed = (
        not uncovered
        and (page_limit is None or over_by <= 0)
        and not any(s["over"] for s in per_section_limits)
        and not any(d["over"] for d in document_limits)
    )

    return {
        "requirements_total": len(rows),
        "requirements_live": len(content),
        "constraints": document_limits,
        "requirements_excluded": len(rows) - len(live),
        "covered": len(covered),
        "uncovered": uncovered,
        "scored_but_uncovered": scored_and_missing,
        "coverage_rate": round(len(covered) / len(content), 3) if content else 1.0,
        "word_count": words,
        "estimated_pages": estimated,
        "words_per_page": words_per_page,
        "page_limit": page_limit,
        "over_page_limit_by": over_by if page_limit and over_by > 0 else 0.0,
        "section_page_limits": per_section_limits,
        "sections": [{"heading": s.heading, "words": s.words, "pages": s.pages(words_per_page)}
                     for s in sections],
        "passed": passed,
    }


def render(report: dict) -> str:
    lines = []
    lines.append(
        f"coverage: {report['covered']}/{report['requirements_live']} live requirements "
        f"addressed ({report['coverage_rate'] * 100:.1f}%)"
    )
    if report["requirements_excluded"]:
        lines.append(
            f"          {report['requirements_excluded']} row(s) excluded by reviewer flag"
        )
    lines.append("")

    if report["uncovered"]:
        lines.append("UNADDRESSED")
        for item in report["uncovered"]:
            marker = " [SCORED]" if item["eval_criterion"] else ""
            lines.append(f"  {item['id']}{marker}  {item['requirement']}")
            lines.append(f"      {item['why']}")
        lines.append("")
        if report["scored_but_uncovered"]:
            lines.append(
                f"  {len(report['scored_but_uncovered'])} of these are tied to an "
                "evaluation criterion — those are lost points, not just missing text."
            )
            lines.append("")

    lines.append(
        f"pages: {report['estimated_pages']} estimated from {report['word_count']:,} words "
        f"at {report['words_per_page']}/page"
    )
    for item in report.get("constraints", []):
        state = "OVER" if item["over"] else "ok"
        lines.append(
            f"       {item['id']} states a {item['limit_pages']}-page limit — {state}"
        )
    if report["page_limit"]:
        verdict = (
            f"OVER by {report['over_page_limit_by']}"
            if report["over_page_limit_by"] > 0
            else "within limit"
        )
        lines.append(f"       limit {report['page_limit']} — {verdict}")
    for section in report["section_page_limits"]:
        state = "OVER" if section["over"] else "ok"
        lines.append(
            f"       {section['section']}: {section['estimated_pages']} of "
            f"{section['limit_pages']} — {state}"
        )

    lines.append("")
    lines.append(f"gate: {'PASS' if report['passed'] else 'HOLD'}")
    return "\n".join(lines)
