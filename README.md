# colorteam

**An AI color team for federal proposals.**

A proposal is a chain of small, rule-heavy, repetitive jobs: qualify the
opportunity, shred the solicitation into requirements, build the outline, write,
score the draft the way the evaluator will, catch the language that creates legal
exposure, and turn the debrief into something that changes the next pursuit.

Most of those jobs are done by hand, by expensive people, under deadline, every
time. `colorteam` gives each one a specialist and lines them up in the order the
work actually happens.

Six agents, one deterministic linter, and a CLI.

```
qualification → analysis → planning →  (writing)  →  review  → quality → post-award
    GATE          SHRED      OUTLINE                  SCORE     REDLINE    DEBRIEF
                                                                   ▲
                                                          colorteam lint
                                                    (deterministic, no model)
```

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

**Every run is auditable.** `--dry-run` prints the exact assembled prompt without
calling anything, so a prompt can be reviewed before it is trusted. `--save` writes
each output to `runs/` with a timestamp and provenance header, so outputs diff
between drafts.

---

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
python -m pytest tests/ -q          # 20 passed
python -m colorteam list            # 6 agents
python -m colorteam lint examples/sample-draft.md   # 37 findings, gate HOLD
```

If those three work, everything except the live API call is working.

## Use

```bash
# what's in the box
python -m colorteam list

# deterministic language check — no model, no key, exit code 1 if it fails the gate
python -m colorteam lint examples/sample-draft.md
python -m colorteam lint examples/sample-draft.md --json     # for CI

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

---

## The agents

| Agent | Stage | What it does |
| --- | --- | --- |
| `GATE` | qualification | Scores an opportunity on customer knowledge, solution fit, competitive position, contract fit, and resource fit. Weights customer knowledge and competitive position double, because pursuits are won before release. Returns PURSUE / WATCH / DECLINE and the three questions that would change the answer. |
| `SHRED` | analysis | Extracts every atomic requirement into a compliance matrix with verbatim text and exact citations. Maps Section L instructions to Section M criteria in both directions and flags the unmapped ones — an M criterion with no L instruction is where proposals quietly lose points. |
| `OUTLINE` | planning | Turns the matrix into an annotated outline: page budgets allocated by evaluation weight rather than by how much there is to say, a win theme per section, and the specific proof each claim needs. Flags unsupported claims while there is still time to find the proof. |
| `SCORE` | review | Reads the draft as a source selection board member who may only credit what is on the page. Returns strengths, weaknesses, and deficiencies with quoted evidence, then ranks fixes by points recovered per hour of rework. |
| `REDLINE` | quality | The judgment layer on top of `lint`: unsupported claims, terminology drift, undefined acronyms, broken cross-references, and numbers that disagree between text, tables, and graphics. Every finding carries a suggested replacement in the document's own voice. |
| `DEBRIEF` | post-award | Separates what the government actually said from what the team inferred, traces each finding to the lifecycle stage that created it, and writes corrective actions specific enough to audit next quarter. |

## Layout

```
agents/            six agent definitions — Markdown + YAML frontmatter
reference/         style-rules.yaml, compliance-schema.md — the knowledge layer
colorteam/
  lint.py          deterministic checks; the only module with no model dependency
  registry.py      loads and validates agent definitions
  runner.py        prompt assembly, API call, run persistence
  cli.py           list / lint / run
examples/          synthetic solicitation and draft, plus generated outputs
tests/             20 tests — rule behavior, determinism, prompt assembly, agent validity
```

```bash
python -m pytest tests/ -q
# 20 passed
```

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

MIT licensed.
