---
name: ce-idea-scout
description: |
  Generate, triage, and rank a shortlist of software/startup ideas — a verdict-rendering funnel (generate → cheap filter → seven-axis score → ranked directions). Opinionated rankings; decision support, not validated fact.
  Triggers: brainstorm/scout/generate/triage MANY ideas into a ranked shortlist. For ONE idea use /product-discovery:ce-idea-score; for market validation /product-discovery:ce-market-scan.
argument-hint: "[domains / constraints, e.g. 'devtools, climate; 3 people, no outside capital']"
allowed-tools: Read, Write, Glob, Grep, Bash, WebSearch, WebFetch, AskUserQuestion, Skill
---

# Idea Scout

**Invocation input:** Domains / constraints (team size, capital ceiling, unfair advantages): $ARGUMENTS


Turn a domain / constraint brief into a **ranked shortlist of directions worth
pursuing**, through a funnel that spends cheap tokens widely and expensive tokens only
where they pay: **generate 15-25 candidates → cheap 3-axis filter → deep-dive the 5-6
survivors on the full `ce-idea-score` rubric → rank, with a top-3 and an avoid-list**. The
deep-dive *is* the `ce-idea-score` engine; this skill owns the generation, the triage, and
the cross-idea ranking around it.

> **A verdict tool, deliberately — and a funnel, deliberately.** Like `ce-idea-score`
> (and unlike `/product-discovery:ce-market-scan`), this skill ranks and recommends. Two failure modes it is
> built to avoid: (1) **shallow-everywhere** — analyzing 12 ideas at full depth in one
> pass produces generic filler and thinner late ideas, then ranks them as if analyzed
> equally; the funnel fixes this by deep-diving only survivors. (2) **fabricated
> rigor** — ranking ideas on market "facts" the model invented; the evidence discipline
> (below) fixes this. The whole artifact is labeled **OPINIONATED decision support — a
> ranked shortlist, not validated fact.**

> **Where it sits.** Furthest upstream:
> **`ce-idea-scout`** (generate + triage → shortlist) → human picks → `ce-idea-score` (deep
> verdict on one idea) → human commits → `/product-discovery:ce-market-scan` (optional — the **stakes dial**:
> skip for a fast pick, run it to validate before committing real planning effort) →
> `/core-engineering:ce-brief` → `/core-engineering:ce-plan`. Its shortlist is **directions to pressure-test**, never
> a build decision (see *Directions, not decisions* below).

## Disciplines

- **The funnel, not the firehose** — generate wide, filter cheap, deep-dive narrow. The
  cheap filter's cuts are **stated, with the reason each candidate was dropped** (no
  silent caps — a dropped idea is named, not vanished).
- **Evidence honesty even in a verdict tool** — any market-fact claim feeding a score is
  tagged `confirmed` (cited, source + date) / `suspected` (inference, flagged) /
  `unknown` (no basis — flagged). In `judgment-only` mode nothing is `confirmed`. *No
  invented company names, funding rounds, or trend statistics* — an unsourced market
  claim is `suspected` at most and marked. This is the discipline borrowed from
  `/product-discovery:ce-market-scan` that keeps the ranking off fiction.
- **Directions, not decisions** — ideas are generated *without a team attached*, so the
  ranking is structurally blind to founder-market fit (the largest seed-stage variable).
  The shortlist is therefore a set of **directions to pressure-test against your own
  unfair advantages**, never "what to build." The artifact says so, and the strongest use
  is to re-rank the shortlist against the team's real assets.
- **The deep-dive is `ce-idea-score`** — survivors are scored on the *canonical* seven-axis
  rubric, anchored bands, gates, and gate-then-weight aggregation defined in the
  `ce-idea-score` skill. This skill does not fork the rubric; it applies it.

## Human-in-the-Loop — batched

Material judgment batches to **Stage 0** (the brief: domains, constraints, team assets,
evidence mode, budget) and the **Stage 4 read-back** (the human reviews the ranked
shortlist and picks which directions to carry forward). Generation, filtering, and
scoring between them are autonomous. Reserve AskUserQuestion for those two gates and any
Stuck-rule question.

## Runtime Inputs

- **Domains / constraints brief (optional):** the spaces to explore (e.g. devtools,
  healthcare, climate), and the constraints — **team size, capital ceiling, and any
  unfair advantage** the team already has (domain access, an audience, a technical edge).
  Team assets are what let the shortlist be re-ranked beyond founder-blind scoring. If
  empty, ask once for at least a domain or a constraint; do not silently pick for the user.
- **Evidence mode + query budget (Stage 0):** `researched` (cited evidence within a
  stated budget — preferred) or `judgment-only` (no web; all claims `suspected`/`unknown`).
- **Candidate / survivor counts (Stage 0, defaults):** generate **15-25**, deep-dive the
  top **5-6**. Adjustable, but stated — never silently widened or narrowed.

## Execution Contract

1. **Gate scope at Stage 0** — confirm domains, constraints, team assets, evidence mode,
   budget, and the candidate/survivor counts before generating.
2. **Generate wide, then cut with reasons** — no silent caps; every dropped candidate is
   named with the reason.
3. **Tag or omit** — every market-fact claim is `confirmed` / `suspected` / `unknown`;
   never an untagged assertion. Synthesis is `suspected` at most. No invented facts.
4. **Deep-dive on the canonical rubric** — survivors are scored via the `ce-idea-score`
   seven-axis rubric and gate-then-weight; knockouts gate, they do not average.
5. **Rank as directions** — the shortlist is opinionated and ranked, labeled a set of
   directions to pressure-test, never a build mandate; founder-fit is named as unseen.
6. **Hand off, don't decide for them** — the human picks which directions advance to a
   full `/product-discovery:ce-idea-score` or `/product-discovery:ce-market-scan`.

---

## Stage 0 — Scope & Constraint Gate

Summarize (Markdown): the domains to explore, the constraints (team size, capital
ceiling, unfair advantages), the evidence mode + budget, and the candidate/survivor
counts. Then ask (AskUserQuestion) **Proceed / Adjust / Abort**. Generate nothing before
Proceed.

## Stage 1 — Generate Candidates (wide)

Produce **15-25 one-line candidates**, each: a concept (≤ 1 sentence), the primary
customer, and the single sharpest **why-now** (the 2025-26 shift that makes it possible
now). Favor non-obvious recombinations across domains. Do **not** deep-analyze here — this
stage is breadth. Drop the loaded word "revolutionary"; the test is *non-obvious but
buildable-and-sellable now*.

## Stage 2 — Cheap Filter (triage to survivors)

Score each candidate fast on **three cheap axes only** — a 1-5 quick read each, evidence
tag on any market claim:

- **Demand signal** — is there a visible, urgent pain (not a vitamin)?
- **Buildability** — could 2-5 people ship an MVP in 3-6 months?
- **Why-now strength** — is the timing wedge concrete, or hand-wavy?

Keep the top **5-6**. **Write the cut list**: every dropped candidate with a one-line
reason (no silent caps). A candidate killed cheaply here beats a thin full scorecard on a
doomed idea.

## Stage 3 — Deep-Dive Survivors (the `ce-idea-score` rubric)

**Load the rubric, don't recall it.** Read the `ce-idea-score` skill's `SKILL.md` for the
canonical anchored bands, knockout floors, and gate-then-weight weights before scoring —
this skill *applies* that rubric, it never forks or reconstructs it from memory.

Apply the **canonical seven-axis scorecard from the `ce-idea-score` skill** to each survivor —
Market demand · Distribution · Feasibility · Differentiation · Defensibility · Revenue
potential · Timing, with its anchored bands, the Defensibility "name-the-moat-or-≤3" cap,
the **knockout floors** (Feasibility/Distribution ≤ 3 → disqualified), the binary
kill-conditions, a falsifiable **DEAD IF** line per survivor, and the **gate-then-weight**
composite (weights + per-axis vector + disclaimer; never a bare sum). Render a compact
inline scorecard per survivor (reuse `ce-idea-score`'s Scorecard columns — Axis · Score ·
Evidence · justification — abbreviated). Promote any survivor to a full `/product-discovery:ce-idea-score` run for the
rigorous standalone artifact and its `score-lint.py` gate.

## Stage 4 — Rank, Shortlist & Read-Back

Assemble and render (two-surface), then read back to the human:

- **Ranked table** — survivors by composite, **with the per-axis vector shown** (never the
  bare number), and disqualified ideas marked as such.
- **Top 3 directions** — annotated by their scorecard (the gates they pass, their wedge).
- **Avoid-list** — the disqualified / fatally-weak ideas and the specific reason.
- **Common patterns** — what the strongest directions share (a descriptive observation).
- **The framing line** — "these are directions to pressure-test against your team's unfair
  advantages, not a build decision; founder-market fit is not scored here."

Ask (AskUserQuestion) which directions to carry forward.

## Stage 5 — Write & Hand Off

Write the artifact (never overwritten):

```text
docs/idea-scout/<date>.md
```

For each direction the human carries forward, **name the next skill** — *"Run
`/product-discovery:ce-idea-score` on \<direction\> for a full standalone verdict, or
`/product-discovery:ce-market-scan` for an evidence-bound validation"* — never auto-launch it,
never feed the ranking forward as fact.

### Document Sections

```text
# Idea Scout — <Domain(s)>   (OPINIONATED decision support — a ranked shortlist, not validated fact)
date: <date>   evidence-mode: <researched | judgment-only>   generated: <N>   deep-dived: <M>

## Brief                 (domains, constraints, team assets)
## Candidates            (the 15-25 one-liners: concept · customer · why-now)
## Cut List              (every dropped candidate + one-line reason — no silent caps)
## Survivor Scorecards   (per survivor: the 7-axis idea-score scorecard, evidence-tagged, + DEAD-IF)
## Ranked Shortlist      (by composite, per-axis vector shown; disqualified marked)
## Top 3 Directions      (annotated by scorecard)
## Avoid                 (disqualified / fatally weak + the reason)
## Common Patterns       (descriptive)
## Sources               (URL + access date per confirmed claim)
```

## Escalation

- A survivor that needs facts the budget can't reach → mark the axis `unknown` and route
  it to a scoped `/product-discovery:ce-market-scan` before scoring stands.
- The human wants to commit to one direction → hand to `/product-discovery:ce-idea-score` (full verdict) then
  `/product-discovery:ce-market-scan` → `/core-engineering:ce-brief` → `/core-engineering:ce-plan`.

## Honest Limitations

- **A ranked shortlist, not validated fact.** The whole artifact is OPINIONATED decision
  support. The ranking is the tool's opinion under an opinionated weighting.
- **Directions, not decisions.** Ideas are generated team-less, so the ranking cannot see
  founder-market fit — the largest seed-stage variable. Even the #1 direction means "worth
  pressure-testing against your unfair advantages," never "build this." The honest use is
  to re-rank against the team's real assets; a stronger variant of this tool would *start*
  from those assets and search for idea-fit.
- **Generation is bounded and biased.** A fixed 15-25 candidate sweep over named domains
  cannot be exhaustive, and the model's training shapes what it proposes; a great idea
  outside the brief's domains will simply be absent. Widen the domains, not the count, to
  explore more.
- **The ranking is only as good as the evidence and the weights.** In `judgment-only` mode
  every score is `suspected`/`unknown`; the default weighting suits a generic small team.
  An `unknown`-heavy shortlist ranks directions to *investigate*, not to *back*.
- **The cheap filter can cut a late bloomer.** A 1-5 triage on three axes will sometimes
  drop an idea that a full scorecard would have rescued; the cut list exists so those
  calls are visible and reversible, not silent.
- **Shape, not truth.** The funnel and the evidence tags keep the ranking *accountable*,
  not *correct*. `ce-idea-score`'s `score-lint.py` gates a promoted survivor's standalone
  artifact; this skill relies on the same discipline in prose for the inline scorecards.
- **Separate from `/product-discovery:ce-market-scan` and `/core-engineering:ce-brief`.** It generates and ranks; it neither runs
  market-scan's disciplined evidence base nor elicits intent. Its shortlist crosses into
  the pipeline only as a labeled reference — never into a brief's Project Description as fact.
