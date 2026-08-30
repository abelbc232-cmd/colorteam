# Compliance matrix schema

Every row in a compliance matrix is one atomic requirement. The matrix is the
single source of truth for what the proposal must contain, and it is the artifact
production checks against before submission.

## Columns

| Column | Contents |
| --- | --- |
| `ID` | Sequential, prefixed by source section. `L-014`, `M-003`, `C-027`. Stable for the life of the pursuit — never renumber. |
| `Source` | Section and paragraph, with page where available. `L.3.2.1, p. 44` |
| `Requirement` | The requirement quoted verbatim. No paraphrase. |
| `Type` | `submission` (what/how to submit), `performance` (what we must do), `evaluation` (how it is scored), `administrative` (forms, registrations, certifications) |
| `Volume` | Which proposal volume it belongs in. |
| `Section` | Which outline section answers it. |
| `Eval criterion` | The Section M factor or subfactor it scores against, or `none`. |
| `Page limit` | Any stated limit that applies. |
| `Owner` | Role responsible for the response. |
| `Status` | `open` / `drafted` / `reviewed` / `complete` |

## Rules

1. **Atomic.** One obligation per row. A sentence containing "the offeror shall
   describe its approach, staffing, and transition plan" is three rows.
2. **Verbatim.** The evaluator reads the solicitation's language. Paraphrase in the
   matrix leads to drift in the response.
3. **Stable IDs.** Requirements get referenced from the outline, the draft, and the
   review comments. Renumbering mid-pursuit breaks every reference.
4. **Two-way mapping.** Every Section L instruction maps to a Section M criterion
   where one exists, and every Section M criterion maps back to at least one place
   in the outline. Unmapped items in either direction are flagged, not silently
   accepted:
   - **L with no M** — mandatory but unscored. Meet it efficiently; do not spend
     page budget on it.
   - **M with no L** — scored but never explicitly requested. This is where
     proposals quietly lose points, and it needs a deliberate home in the outline.
5. **Pass/fail rows are marked.** Page limits, font specifications, file formats,
   naming conventions, and submission mechanics are compliance failures regardless
   of how good the technical content is. They belong in the matrix like any other
   requirement.

## Example rows

| ID | Source | Requirement | Type | Volume | Section | Eval criterion | Page limit | Owner | Status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| L-001 | L.2, p. 12 | "The Technical Volume shall not exceed 30 pages." | submission | I | — | none | 30 | proposal mgr | open |
| L-014 | L.3.2.1, p. 14 | "The offeror shall describe its approach to maintaining link availability in degraded conditions." | submission | I | 2.3 | M-002 | — | tech lead | drafted |
| M-002 | M.2.b, p. 51 | "The Government will evaluate the extent to which the proposed approach demonstrates resilience under degraded and contested conditions." | evaluation | I | 2.3 | — | — | capture | open |
