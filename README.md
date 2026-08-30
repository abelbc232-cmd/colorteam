# colorteam

[![CI](https://github.com/abelbc232-cmd/colorteam/actions/workflows/ci.yml/badge.svg)](https://github.com/abelbc232-cmd/colorteam/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)

**An AI color team for federal proposals.**

A proposal is a chain of small, rule-heavy, repetitive jobs: qualify the
opportunity, shred the solicitation into requirements, build the outline, write,
score the draft the way the evaluator will, catch the language that creates legal
exposure, and turn the debrief into something that changes the next pursuit.

Most of those jobs are done by hand, by expensive people, under deadline, every
time. `colorteam` gives each one a specialist and lines them up in the order the
work actually happens.

Ten agents, an evidence base, three deterministic gates, and a CLI.

```
qualify ──────── analyze ── plan ─── draft ── pink ── red ─── score ── quality ── assemble
GATE  CLASSIFY   SHRED    OUTLINE    DRAFT    PINK    RED     SCORE    REDLINE    DEBRIEF
                    │                  │              │         │
             matrix export/import   knowledge/   comments +   rubric
             (a human corrects     (never        graphics     (gate vetoes
              the extraction)      committed)                 the judgment)
                    └──────────── colorteam coverage ─────────┘
                            lint · coverage · rubric
                        deterministic — no model involved
```

A human decides between every stage. Nothing chains automatically.

---

## Why it is built this way

**Agents are Markdown files, not code.** Each agent in `agents/` is a Markdown
file with YAML frontmatter. A proposal manager who does not write Python can read,
review, and change an agent, and every change is a reviewable diff in git. That
matters more than it sounds: the quality of these systems lives in the prompts, so
the prompts have to be editable by the people who know the domain.

**The rules that need no judgment are not given to a model.** Prohibited terms,
unsupported superlatives, hedges, and passive voice are checked in pure Python
(`colorteam/lint.py`) against `reference/style-rules.yaml`. Same input, same
findings, every time — which is what makes findings countable across drafts. If the
numbers a team tracks move because a model felt different that afternoon, the
numbers are worthless. Models handle judgment. Regex handles rules.

**One agent, one job.** No agent does two things. That is what makes the output
checkable by a human who is short on time, and it is why the compliance matrix from
`SHRED` can be trusted enough to govern the rest of the proposal.

**DRAFT does not invent facts.** The drafting agent is forbidden from producing a
number, date, contract, customer, or past performance reference that is not in the
source material it was given. Where a fact is missing it emits a marker —
`[PROOF NEEDED: on-time delivery rate for a comparable contract]` — and writes the
sentence around it, then lists every marker in a Placeholder Manifest with what
would close it and who owns it. A fabricated figure in a federal proposal reads
plausibly, survives review, and becomes a false statement in a submitted offer.
That is the one failure this tool must not have, so the constraint is the first
thing in the prompt rather than a caveat at the end.

**The extraction is built to be corrected.** Requirement extraction is the
highest-leverage step and the one a model gets imperfectly right — a requirement
missed there is a requirement nobody writes to. So the compliance matrix round
trips through a spreadsheet: `matrix export` produces a workbook with dropdown
validation and instructions, a proposal manager corrects it in Excel, and
`matrix import` reads it back and *reports* what changed — edits, hand-added
rows, and rows flagged as mis-extracted. Rejected rows stop counting against
coverage but are never deleted, so the record of what the machine extracted and
what a human rejected stays intact.

**The gate is a veto, not a vote.** `colorteam coverage` checks requirement
coverage and page math; `colorteam lint` checks language; both are pure
arithmetic. `colorteam rubric` fuses the model's weighted judgment score with
those gates — and a failed gate produces HOLD regardless of how well the proposal
reads. A proposal that misses a requirement is non-responsive, and no judgment
score may overturn that.

**Claims are grounded in an evidence base, not in the model.** `knowledge/`
holds capability statements, resumes, past performance, prior proposals won and
lost, and pricing history. `--knowledge` ranks that material against the document
in hand and packs the relevant parts into the prompt with the source file named on
every excerpt, so a drafting agent cites where a fact came from and a reviewer
checks it in seconds. Ranking is plain term overlap — no embeddings, no extra
dependency, no network, and a ranking a human can predict and argue with.

**Review feedback is read where reviewers actually leave it.** Reviewers comment
in Word margins, not in a separate document. `colorteam` reads `word/comments.xml`
out of the package directly, including the text each comment is anchored to, so a
commented pink draft is a valid input with no retyping.

**Every run is auditable.** `--dry-run` prints the exact assembled prompt without
calling anything, so a prompt can be reviewed before it is trusted. `--save` writes
each output to `runs/` with a timestamp and provenance header, so outputs diff
between drafts.

**It counts.** `--record` appends every lint result to an append-only history file,
and `colorteam trend` reports the series. A single lint run tells a writer what to
fix; a series tells a manager whether the process is improving, which is the only
claim worth taking to leadership.

---

## Two ways to run it

**As a Claude Project — nothing installed.** Everything here is either a prompt
or a rule, and both are text, so the whole lifecycle runs in a conversation.
Paste `project/instructions.md` into a Claude Project, upload the four files in
`project/knowledge/`, add your evidence base, and type `/classify`. Setup is
about five minutes. See [`project/README.md`](project/README.md).

The pack is **generated** from the same `agents/` and `reference/` files the CLI
uses, and CI fails if it drifts — two copies of the same reviewer prompt
disagreeing would mean the Project runs a version that is not the one under test.

```bash
python -m colorteam project build
```

What you give up: the checks stop being deterministic. A careful reader working
the banned-word list finds the problems; a regular expression finds them
identically every time. Use the Project to do the work; use the CLI when you need
a number you will defend in front of leadership, or a check that runs in CI.

**As a CLI — installed.** Everything below.

## Install

```bash
git clone https://github.com/abelbc232-cmd/colorteam.git
cd colorteam
pip install -r requirements.txt
cp .env.example .env        # add your ANTHROPIC_API_KEY
```

On Windows, use `python -m venv .venv && .venv\Scripts\activate` and `copy .env.example .env`.

The linter and `--dry-run` need no API key. Verify the install with:

```bash
python -m pytest tests/ -q          # 153 passed
python -m colorteam list            # 10 agents
python -m colorteam lint examples/sample-draft.md   # 37 findings, gate HOLD
python -m colorteam trend           # the recorded series
```

If those four work, everything except the live API call is working.

## Use

```bash
# what's in the box
python -m colorteam list

# deterministic language check — no model, no key, exit code 1 if it fails the gate
python -m colorteam lint examples/sample-draft.md
python -m colorteam lint examples/sample-draft.md --json     # for CI

# Word documents too — paragraphs and compliance tables, in document order
python -m colorteam lint examples/sample-draft.docx

# record a snapshot, then watch the series across drafts
python -m colorteam lint examples/sample-draft.md --record --label "pink team"
python -m colorteam trend

# draft a section from the outline, using your own source material
python -m colorteam run DRAFT --input outline.md \
                             --context rfp.docx \
                             --material past-performance.docx \
                             --material tech-description.docx

# run the pink team review against the compliance matrix
python -m colorteam run PINK --input draft.docx \
                            --matrix matrix.md \
                            --context rfp.docx

# build the evidence base once, then draft against it
python -m colorteam knowledge init
python -m colorteam knowledge add --path capability-statement.docx --kind capabilities
python -m colorteam knowledge add --path 2024-award.docx --kind proposals-won
python -m colorteam knowledge list

python -m colorteam run DRAFT --input outline.md --context rfp.docx --knowledge

# pink draft with reviewer comments in the margins → red team draft
python -m colorteam run RED --input pink-draft-commented.docx \
                           --matrix matrix.md --context rfp.docx --knowledge

# pull the figures RED specified and render them
python -m colorteam graphics red-draft.md --out graphics/

# the matrix round trip — the one place a human corrects the machine
python -m colorteam matrix convert shred-output.md -o matrix.json
python -m colorteam matrix export matrix.json -o matrix.xlsx    # correct in Excel
python -m colorteam matrix import matrix.xlsx --against matrix.json

# the deterministic gate: coverage and page math, no model
python -m colorteam coverage --matrix matrix.json --draft draft.docx --pages 25

# fuse the model's score with the gate — the gate wins
python -m colorteam rubric score judge.json --gate coverage.json

# build the .docx, with compliance, traceability, and open-item appendices
python -m colorteam assemble --draft red-draft.md --matrix matrix.json -o proposal.docx

# inspect exactly what an agent will ask, without calling the API
python -m colorteam run SHRED --input examples/sample-rfp.md --dry-run

# run an agent for real
python -m colorteam run SHRED --input examples/sample-rfp.md --save
python -m colorteam run SCORE --input examples/sample-draft.md \
                             --context examples/sample-rfp.md
```

`lint` returns a non-zero exit code when a document fails the thresholds in
`reference/style-rules.yaml`, so it drops into a pre-commit hook or a CI job
unchanged — a draft with prohibited language never reaches a color review.

## What it produces

Against the synthetic sample draft in `examples/`:

```
examples/sample-draft.md: 37 findings in 363 words

  11:15  HIGH   prohibited 'ensure' — Creates an absolute guarantee...
  25:1   HIGH   prohibited 'fully compliant' — Blanket compliance claim...
  30:26  HIGH   prohibited 'guarantee' — Unqualified commitment...
  ...
  high 7 | medium 9 | low 21
  gate: HOLD (thresholds in reference/style-rules.yaml)
```

Full outputs are in [`examples/outputs/`](examples/outputs/).

Why `ensure` is a high-severity finding and not a style nit: in a federal proposal
it reads as an unqualified guarantee, and a guarantee in a submitted proposal can
become a contractual obligation the program office holds you to. The same applies
to *fully compliant*, *all requirements*, *always*, and *never*. These are the
findings that are cheap to catch on Tuesday and expensive to catch on the Friday
of submission.

### The same content, revised

`examples/sample-draft-revised.md` is the identical fictional proposal with every
finding cleared. Read the two side by side — each change replaces a vague claim
with a specific one, which is the entire argument for the tool:

| | findings | high | gate |
| --- | --- | --- | --- |
| `sample-draft.md` | 37 in 363 words | 7 | HOLD |
| `sample-draft-revised.md` | 0 in 432 words | 0 | PASS |

*"Our team will ensure that operational availability is maintained"* becomes
*"Our team sustains operational availability above the 95% monthly threshold at
all three sites."* The first is a legal exposure that says nothing. The second is
scoreable.

### Measuring it over time

`--record` appends the result to `history/lint-history.jsonl`, and `trend` reports
the series. The history committed here is the two sample drafts above:

```
2 snapshot(s) across 2 document(s)

  date         label              words  high   med   low   per 1k  gate
  ------------------------------------------------------------------------
  2026-08-30   pink team            363     7     9    21   101.93  HOLD
  2026-08-30   red team             432     0     0     0     0.00  PASS

  findings per 1k words  █▁
  high severity per 1k   █▁

  Findings per 1k words went down from 101.93 to 0.0 (-100.0%).
```

Findings are normalized per thousand words so drafts of different lengths compare
honestly — raw counts reward writing less, which is not the goal.

---

## The agents

| Agent | Stage | What it does |
| --- | --- | --- |
| `GATE` | qualification | Scores an opportunity on customer knowledge, solution fit, competitive position, contract fit, and resource fit. Weights customer knowledge and competitive position double, because pursuits are won before release. Returns PURSUE / WATCH / DECLINE and the three questions that would change the answer. |
| `CLASSIFY` | qualification | Identifies the solicitation type — RFP, RFQ, RFI/Sources Sought, SBIR/STTR, BAA/CSO, OTA, vehicle on-ramp, task order — and names the artifact each actually requires, with the language that decided it. A team that answers a Sources Sought notice with a full proposal has spent three weeks on a document the government may not evaluate. |
| `SHRED` | analysis | Extracts every atomic requirement into a compliance matrix with verbatim text and exact citations. Maps Section L instructions to Section M criteria in both directions and flags the unmapped ones — an M criterion with no L instruction is where proposals quietly lose points. |
| `OUTLINE` | planning | Turns the matrix into an annotated outline: page budgets allocated by evaluation weight rather than by how much there is to say, a win theme per section, and the specific proof each claim needs. Flags unsupported claims while there is still time to find the proof. |
| `DRAFT` | drafting | Writes a section to pink-team maturity from the annotated outline. Forbidden from inventing facts: missing evidence becomes a `[PROOF NEEDED]` marker with the sentence built around it, and every marker lands in a Placeholder Manifest with an owner. Carries the same style rules `REDLINE` enforces, so it does not generate findings a later stage has to catch. |
| `PINK` | review | Chairs a pink team. Checks coverage against the compliance matrix first — including requirements restated but never answered — then story, discriminators, proof posture, and page allocation against evaluation weight. Returns ON TRACK / AT RISK / REWRITE per section and an assignment list ordered by evaluation weight blocked. Deliberately does no line editing. |
| `RED` | revision | Takes a pink draft plus reviewer comments and produces the red team draft. Dispositions every comment as ACCEPTED / ACCEPTED WITH MODIFICATION / REJECTED / NEEDS DECISION with a reason. Refuses to average conflicting reviewers — it implements the better-supported one and escalates the conflict. A reviewer asserting a figure the evidence does not support produces a marker, not a sentence. Specifies each figure as Mermaid with an action caption. |
| `SCORE` | review | Reads the draft as a source selection board member who may only credit what is on the page. Returns strengths, weaknesses, and deficiencies with quoted evidence, then ranks fixes by points recovered per hour of rework. |
| `REDLINE` | quality | The judgment layer on top of `lint`: unsupported claims, terminology drift, undefined acronyms, broken cross-references, and numbers that disagree between text, tables, and graphics. Every finding carries a suggested replacement in the document's own voice. |
| `DEBRIEF` | post-award | Separates what the government actually said from what the team inferred, traces each finding to the lifecycle stage that created it, and writes corrective actions specific enough to audit next quarter. |

## Layout

```
.github/workflows/ CI — tests on Python 3.10-3.13, plus behavioral checks
agents/            eight agent definitions — Markdown + YAML frontmatter,
                   numbered in lifecycle order
reference/         style-rules.yaml, compliance-schema.md — the knowledge layer
colorteam/
  lint.py          deterministic checks; the only module with no model dependency
  loaders.py       .md / .txt / .docx in, plain text out — plus Word comments
  knowledge.py     the evidence base: load, rank, excerpt, pack with provenance
  graphics.py      pull mermaid figures out of a draft and render them
  matrix.py        the compliance matrix and its spreadsheet round trip
  coverage.py      deterministic gate: requirement coverage and page math
  rubric.py        weighted judgment fused with the gate; builds the worklist
  assemble.py      the .docx, with its three appendices
  trend.py         append-only history and trend reporting
  registry.py      loads and validates agent definitions
  runner.py        prompt assembly, API call, run persistence
  project.py       generates the no-install Claude Project pack
  cli.py           list / lint / trend / knowledge / graphics / matrix /
                   coverage / rubric / assemble / project / run
knowledge/         YOUR evidence base — gitignored, never committed
examples/          synthetic solicitation, a failing draft, its clean revision, outputs
history/           append-only lint history
project/           the no-install Claude Project pack — generated, not edited
reference/         style-rules.yaml, compliance-schema.md, score-rubric.yaml
tests/             153 tests — rules, determinism, loaders, comments, knowledge,
                   graphics, matrix round trip, coverage, rubric, assembly,
                   and that the Project pack has not drifted
```

```bash
python -m pytest tests/ -q
# 36 passed
```

CI runs the suite on Python 3.10 through 3.13 and then checks behavior, not just
imports: every agent definition must load, the failing sample must still fail the
gate, and the revised sample must still pass it. A rules change that silently stops
catching things breaks the build.

## Extending it

Add an agent by adding a Markdown file to `agents/`. No code changes:

```markdown
---
name: PTW
stage: pricing
purpose: Estimate a competitive price range from the solicitation and known competitors.
inputs: [solicitation, competitor_profiles]
references: [compliance-schema.md]
output: A price range with the assumptions behind each bound.
---

You are a price-to-win analyst...
```

`python -m colorteam list` picks it up immediately. The frontmatter contract is
validated on load, so a malformed agent fails loudly rather than producing a
plausible-looking bad result.

---

## Scope and honesty

This is a working reference implementation, deliberately small enough to read in
one sitting. It is not a product.

Everything in `examples/` is synthetic and fabricated for demonstration. No
solicitation, proposal, client deliverable, or employer material appears anywhere
in this repository, and none ever will — the whole point of a tool in this domain
is that the sensitive material stays out of it.

What this repository is meant to show: that a proposal lifecycle can be decomposed
into checkable stages, that the rules-versus-judgment split is a design decision
worth making explicitly, and that the hard part of building one of these is knowing
what the stages are — not the AI.

### What it does not do

`DRAFT` produces a pink-team draft; it does not produce a submittable proposal, and
nothing here should be sent to a government customer without a human writing over
it. Specifically:

- **Agents do not chain.** There is no pipeline command. You run one stage, read
  the output, decide, and run the next. In a domain where a missed requirement
  loses the bid and an overclaim creates contractual exposure, chained AI steps
  compound errors invisibly. The compliance matrix from `SHRED` governs everything
  downstream — if it is wrong and nobody checked, so is the rest.
- **Nothing is remembered between runs.** Each call is independent. The artifacts
  on disk are the state.
- **The .docx is a draft, not a submission.** `assemble` builds the document with
  its appendices and highlights every open item in the body, because an unclosed
  `[PROOF NEEDED]` reaching a customer is a fabrication risk. It does not apply a
  customer's template, and templates are pass/fail.
- **Page counts are estimates.** Words-per-page approximates real pagination. A
  draft 40% over is over under any template; a draft 2% over needs the real one.
- **Nothing you put in `knowledge/` is committed.** That is enforced in
  `.gitignore`, and it is the point: a portfolio repository is the last place a
  real capability statement or a losing proposal belongs.
- **No sources are connected.** It does not pull from SAM.gov, a CRM, or a content
  library, and it does not submit anything anywhere.

MIT licensed.
