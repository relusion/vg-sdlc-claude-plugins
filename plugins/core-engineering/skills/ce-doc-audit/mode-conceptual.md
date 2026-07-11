# Conceptual-Doc Mode — comprehension audit, no execution

Loaded by `SKILL.md` Stage 0 when the document has **no runnable steps** (an
architecture overview, a rationale, a policy, a concept guide). There is nothing
to execute, so this mode runs **only Gate 1 (Role)** — no sandbox, no execution
tier — and produces **role-judgment** and **internal-consistency** findings only.
It never fabricates a run.

## What this mode can and cannot find

- **Can:** comprehension gaps for the role (undefined jargon used before it is
  defined, an unexplained leap, a reference the role cannot resolve), and
  **internal-consistency** defects verifiable by reading (two spans that
  contradict, an orphaned term with no definition, a broken cross-reference or
  dead internal link).
- **Cannot:** any accuracy claim about runtime behavior — there is nothing to run.
  Where the doc makes a factual claim that only execution could settle, record it
  as a `needs-execution` finding (unverified), never as proven or refuted.

## The comprehension walk — read the doc as the role, in order

1. **Track the role's growing knowledge.** Start from the role manifest's *Knows*.
   As the doc introduces a term or concept, add it. At each paragraph ask: *does
   this rely on something the role neither brought nor has been told yet?*
2. **Flag each gap where it first bites**, anchored to the span:
   - term/acronym/reference used before definition, relative to the role's
     boundary → **unclear** (`role-judgment`).
   - a step in the reasoning the role cannot follow from what precedes it →
     **hard-to-follow** (`role-judgment`).
   - a claim here that contradicts a claim elsewhere in the doc → **inaccurate**
     (`internal-consistency`) — cite **both** spans.
   - a promise the doc makes and never fulfills (a "covered below" that isn't, a
     cross-ref to a section/file that does not exist) → **incomplete**
     (`internal-consistency` if checkable, else `needs-execution`).
3. **Reach for a mechanical anchor** where one exists (a `grep`/count that proves a
   term is orphaned, a link-resolve that proves a cross-ref is dead) — those become
   `internal-consistency` findings the report can *confirm* rather than merely rate.
4. **Set `position`** (before/after the role's success criterion) for each finding
   — it caps severity per the spine's rubric.

## Produce the artifacts

Same as executable mode, minus execution evidence: **cluster by root cause**, then
write `docs/doc-audits/<date>-<slug>.md` (findings ordered by severity then span,
lead with the role's boundary + success criterion) and the annotated copy
`docs/doc-audits/<date>-<slug>.annotated.md` with `⟦DOC-AUDIT F-N⟧` markers. There
is no `evidence/` transcript directory unless a mechanical anchor produced one
(e.g. a saved `grep` result). Triage as in the spine, then print the Closing block
(Mode: conceptual · Steps: n/a).
