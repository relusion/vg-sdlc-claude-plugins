---
name: ce-idea-score
description: |
  Score ONE software/startup idea on a seven-axis decision rubric and render an opinionated, evidence-tagged Pursue/Pursue-with-changes/Park/Drop verdict — knockout gates, a falsifiable DEAD-IF, the human owns the call. Verdict-rendering (unlike /product-discovery:ce-market-scan, which renders none).
  Triggers: score/grade/rate/go-no-go ONE idea. Many ideas → /product-discovery:ce-idea-scout.
argument-hint: "[idea / concept] [--evidence researched|judgment-only] [--from <market-scan path>]"
allowed-tools: Read, Write, Glob, Grep, Bash, WebSearch, WebFetch, AskUserQuestion, Skill
---

# Idea Score

**Invocation input:** Idea to score (and optional --evidence mode / --from a market-scan artifact): $ARGUMENTS


Take **one** idea and produce an **opinionated, evidence-tagged verdict**: score it
against a fixed seven-axis rubric with anchored 1-10 bands, run it through knockout
gates and a falsifiable kill-condition, aggregate the axes by **gate-then-weight**
(never a bare sum), and render a **Pursue / Pursue-with-changes / Park / Drop**
recommendation. This is the **engine** the `ce-idea-scout` funnel calls to deep-dive its
survivors, and it runs standalone on any single idea a human brings.

> **A verdict tool, deliberately.** Unlike `/product-discovery:ce-market-scan` — which is evidence-bound
> and structurally refuses to rank or recommend (the Scope Lock) — this skill *does*
> score, weight, and recommend. That is the requested design. The discipline that
> keeps it honest is therefore **not** verdict-avoidance but the **Verdict-Honesty
> Contract** below: the verdict is allowed, but it may never rest on un-evidenced
> guesses dressed as measurement, hide a fatal weakness behind a strong average, or
> bury the per-axis shape behind one composite number. The whole artifact is labeled
> **OPINIONATED decision support — a verdict, not validated fact.**

> **Where it sits.** Furthest upstream, alongside `ce-idea-scout`, *before* `/product-discovery:ce-market-scan`:
> `ce-idea-scout` (generate + triage) → human picks → **`ce-idea-score`** (deep verdict on one
> idea) → human commits → `/product-discovery:ce-market-scan` (optional — the **stakes dial**: skip for a fast
> pick, run it to validate before committing real planning effort) → `/core-engineering:ce-brief` → `/core-engineering:ce-plan`. It
> may **ingest a `/product-discovery:ce-market-scan` artifact as its evidence base** (clean
> separation: market-scan supplies the un-collapsed evidence, idea-score adds the
> opinion layer). It never feeds its verdict into a brief as fact.

## The Verdict-Honesty Contract (the core discipline)

A verdict is permitted; an *unaccountable* verdict is not. Five clauses, each
mechanically checked by `score-lint.py`:

1. **Every score carries an evidence state** — `confirmed` (a source directly states
   it; URL + access date), `suspected` (inference / plausible judgment, flagged), or
   `unknown` (no basis — the number is a guess, flagged and excluded from any
   confidence claim). *No tag → the score is inadmissible.* Synthesis across sources is
   `suspected` at most, never `confirmed` (the market-scan rule).
2. **The fatal axes gate, they do not average** — Feasibility and Distribution are
   **non-compensatory knockouts**: a score ≤ 3 on either disqualifies the idea outright,
   no matter how strong the rest. A small team cannot ship what it cannot build or
   reach. A compensatory sum that lets brilliance buy back a fatal weakness is forbidden.
3. **The composite never travels alone** — any weighted total is printed *with* its
   weights *and* the full per-axis vector *and* the standing disclaimer that the
   weighting is an opinion, not a fact. A bare composite that hides the shape is a
   violation.
4. **A falsifiable kill-condition, not a failure story** — the idea carries one
   observable **DEAD IF \<X\>** line that a human could check in under ~2 weeks, plus the
   cheapest experiment that tests it. A narrative "most likely reason it fails" does not
   satisfy this.
5. **Recommend, but the human owns the call** — the recommendation is the tool's
   opinion from one fixed set (Pursue / Pursue-with-changes / Park / Drop), and the
   artifact states plainly that the human may override it. The score is founder-agnostic
   (see Honest Limitations), so the recommendation is a *direction*, never a mandate.

## Human-in-the-Loop — opinionated

Material judgment batches to two gates: **Stage 0** (idea + evidence mode + the
non-default weighting, if any) and the **Stage 5** recommendation read-back (the human
may override the tool's call before it is recorded). Everything between is autonomous
scoring against the fixed rubric. Reserve AskUserQuestion for those two gates and any
Stuck-rule question.

## Runtime Inputs

- **One idea / product concept (required):** from the invocation, the user, or a single
  survivor handed down by `ce-idea-scout`. If empty, ask once. Do not invent a concept.
- **Evidence mode + research budget (Stage 0):** `researched` (gather cited evidence
  within a stated query budget — preferred) or `judgment-only` (no web access; **every**
  score is then `suspected` or `unknown`, never `confirmed`, and the artifact says so).
- **Optional evidence base:** a path to a prior `/product-discovery:ce-market-scan` artifact whose findings
  seed the evidence pass (each reused finding keeps its state).
- **Optional weighting:** a non-default axis weighting (Stage 0 only, recorded). Absent →
  the default profile below.
- **Optional knockout-floor override:** a team with a specialist edge may, **consciously
  and at Stage 0 only**, waive a knockout floor (recorded with its reason). Absent → the
  floors bind. Never waived silently.

## Execution Contract

1. **Gate evidence access at Stage 0** — confirm idea, evidence mode, budget, any
   non-default weighting, and any conscious knockout-floor override before any search.
2. **Tag or omit** — every score and claim is `confirmed` / `suspected` / `unknown`;
   never an untagged number. Synthesis is `suspected` at most.
3. **Anchor every score** — each 1-10 sits on the rubric band it matches; the
   justification names the band and cites the evidence row.
4. **Gate before you weight** — apply the knockout floors and binary kill-conditions
   first; a disqualified idea is reported as such (the composite is informational only).
5. **Show the vector with the composite** — never a bare total; always weights +
   per-axis vector + disclaimer.
6. **No silent caps** — when the budget is exhausted, say so and mark uncovered axes
   `unknown`; never quietly stop or exceed.
7. **Recommend, label, and yield** — render one fixed-set recommendation, stamp it the
   tool's opinion, and record the human's override if given.

---

## The Seven-Axis Rubric (canonical — `ce-idea-scout` deep-dives against this)

Each axis is scored **1-10** against the anchored bands, with an **evidence tag** and a
one-line justification that cites the evidence row.

| Axis | What it measures (operational) | Anchored bands (1 · 4 · 7 · 10) |
|---|---|---|
| **Market demand** | Pain intensity × number of sufferers — *independent of price* | 1 nice-to-have, few care · 4 real but narrow niche · 7 urgent for a large, reachable segment · 10 acute, widespread, "hair-on-fire" |
| **Distribution** *(knockout)* | Path to the first 100 customers without a sales force or a paid-CAC war | 1 must create a category & educate buyers · 4 outbound enterprise sales, long cycle · 7 rides an existing channel (app store, PLG self-serve, marketplace, partner install base) · 10 built-in viral / network distribution |
| **Feasibility** *(knockout)* | *Buildable* by 2-5 people in 3-6 months | 1 needs a research breakthrough / exclusive dataset · 4 hard, 9-12 mo for a small team · 7 a focused 3-6 mo MVP · 10 a working prototype in weeks on commodity parts |
| **Differentiation** | Distinct to a user *today* — including the 10× reason to leave the incumbent | 1 me-too, no wedge · 4 marginally better on one axis · 7 a clear wedge that wins the first deal vs the incumbent's switching cost · 10 a category-defining, obviously-better experience |
| **Defensibility** | What *still* stops a customer leaving after 18 mo of a funded copycat — **name the moat or score ≤ 3** | 1 any team clones it in a weekend · 4 thin UX-polish moat only · 7 a named data / network / switching-cost moat that compounds with usage · 10 structural lock-in (regulatory, proprietary dataset, multi-year integration) |
| **Revenue potential** | ACV × reachable accounts × gross margin (can you *extract money at scale*) | 1 hard to monetize / loved-but-free · 4 small ACV or thin margins · 7 healthy ACV × a reachable base · 10 large ACV, large base, software margins |
| **Timing** | The **why-now** wedge — the 2025-26 shift that makes it buildable/sellable now and not 24 mo ago, nor a commodity in 24 more | 1 no why-now, could've been built years ago · 4 mild tailwind · 7 a concrete recent shift (a model capability crossed a threshold, a regulation took effect, a cost curve inverted) · 10 a sharp, closing window |

**`Defensibility` rule:** if no specific moat *mechanism* can be named, the score is
capped at **3** — novelty is not a moat.

### Gates (applied before weighting)

- **Knockout floors:** `Feasibility ≤ 3` **OR** `Distribution ≤ 3` → **DISQUALIFIED**.
  The composite is then informational only; the verdict is Drop or Park.
- **Binary kill-conditions (DEAD if any true):** requires a regulated license the team
  cannot obtain in < 12 months · requires > the stated capital ceiling in non-dilutive
  funding · depends on an exclusive dataset the team cannot get.
- **Idea-specific DEAD-IF:** one falsifiable, ~2-week-checkable observable + the cheapest
  experiment that tests it (e.g. *DEAD IF fewer than 3 of 20 cold-outreach target buyers
  take a paid pilot call*).

### Aggregation — gate-then-weight (default profile, tunable at Stage 0)

For a 2-5 person team, Distribution and Feasibility weigh most; Defensibility least
(moat is earned post-PMF, not at the idea stage):

| Axis | Weight |
|---|---|
| Distribution | 0.20 |
| Feasibility | 0.18 |
| Market demand | 0.17 |
| Timing | 0.15 |
| Revenue potential | 0.13 |
| Differentiation | 0.10 |
| Defensibility | 0.07 |

`Composite = Σ (axis_score × weight)`, on a 1-10 scale. **Always print** the weights, the
full per-axis vector, the composite, and the disclaimer: *"the weighting is an
opinionated profile, not a fact; read the vector, not just the number."* A disqualified
idea shows its composite struck through / marked informational.

---

## Stage 0 — Scope, Evidence Mode & Weighting Gate

Summarize (Markdown) the idea, the evidence mode (`researched` / `judgment-only`), the
query budget, the evidence base (if a `/product-discovery:ce-market-scan` artifact was supplied), the
weighting (default or the user's), and any conscious knockout-floor override. Then ask
(AskUserQuestion) **Proceed / Adjust / Abort**. Gather nothing before Proceed. In `judgment-only` mode, state up front that no
score can be `confirmed`.

## Stage 1 — Evidence Pass (tag or omit)

For each axis, gather what the mode allows and record evidence rows: the claim, its
state (`confirmed` + URL + access date / `suspected` / `unknown`), and the source.
Reuse a supplied `/product-discovery:ce-market-scan` artifact's findings, preserving their states. Drop
unsourced *claims* rather than asserting them — but an axis with no usable evidence is
**not** dropped; it is still scored in Stage 2 and tagged `unknown`. Honor the budget;
mark uncovered axes `unknown` (no silent caps).

## Stage 2 — Score the Seven Axes

Score each axis 1-10 against its anchored band. Each score gets: the **band it matches**,
an **evidence tag**, and a one-line justification **citing the evidence row**. Apply the
Defensibility cap (no named moat → ≤ 3). A score on an `unknown` axis is an explicit
low-confidence guess.

## Stage 3 — Gates

Evaluate the knockout floors, the binary kill-conditions, and author the idea-specific
**DEAD IF** line with its cheapest experiment. Record each result. A failed knockout or a
true binary kill-condition forces the verdict to Drop/Park regardless of the composite.

In the artifact's `## Gates` section, record each result with the marker `score-lint`
keys on: a breached knockout floor reads **DISQUALIFIED**, a **fired** binary
kill-condition reads **DEAD** (a clear one reads `not fired`). That on-disk marker is what
makes the "regardless of the composite" rule mechanical — H8 blocks a `Pursue` /
`Pursue-with-changes` verdict whenever the Gates section shows a fired floor or kill.

## Stage 4 — Aggregate (gate-then-weight)

Compute the weighted composite **only on a non-disqualified idea**. Render the weights,
the per-axis vector, the composite, and the disclaimer. Never collapse to a bare number.

## Stage 5 — Verdict, Recommendation & Read-Back

Render the recommendation from the fixed set, annotated by the on-disk scorecard (the
gates that fired, the lowest axes, the open `unknown`s):

| Recommendation | When | Routes to |
|---|---|---|
| **Pursue** | passes both knockouts, no binary kill fired, strong composite, few `unknown`s | `/product-discovery:ce-market-scan` (validate) → `/core-engineering:ce-brief` |
| **Pursue-with-changes** | passes knockouts but a named axis is weak / a narrowing is needed | `/core-engineering:ce-brief`, carrying the narrowing |
| **Park** | a load-bearing axis is `unknown` — verdict can't be earned yet | run the DEAD-IF experiment / a scoped `/product-discovery:ce-market-scan` first |
| **Drop** | a knockout failed or a binary kill-condition is true | stop — the scorecard is the recorded rationale |

Read the recommendation back to the human (AskUserQuestion): **Accept / Override /
Adjust**. Record their decision — an overridden verdict is stamped `overridden by human`.

## Stage 6 — Lint & Write

Write the artifact (never overwritten):

```text
docs/idea-scores/<slug>/<date>.md
```

**Same-day collision rule:** resolve the path before writing. The first run uses
`<date>`; if it exists, use `<date>-2`, then `<date>-3`, and so on. Never
overwrite a prior score.

Then run the Verdict-Honesty gate:

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/score-lint.py" docs/idea-scores/<slug>/<date>.md
```

**PASS (0)** → done. **FAIL (1)** → a Verdict-Honesty violation (an untagged score, a
disqualified idea scored as if it weren't, a bare composite, a missing DEAD-IF, an
off-list recommendation): fix and re-lint. **Could-not-run (2)** → check the contract by
hand, **loudly**.

### Document Sections

```text
# Idea Score — <Title>   (OPINIONATED decision support — a verdict, not validated fact)
slug: <slug>   date: <date>   evidence-mode: <researched | judgment-only>

## Idea
## Evidence            (per-axis rows: claim — [confirmed|suspected|unknown] — source/date)
## Scorecard           (the 7 axes: Axis | Score (1-10) | Evidence [state] | Band & justification)
## Gates               (knockout floors result + binary kill-conditions; PASS / DISQUALIFIED / DEAD)
## Kill-Condition      (DEAD IF <observable>; cheapest experiment to check it)
## Weighted Verdict    (weights table + per-axis vector + composite + the standing disclaimer)
## Recommendation      (Pursue | Pursue-with-changes | Park | Drop — the tool's opinion; human may override)
## Sources             (URL + access date per confirmed claim)
```

The Scorecard and Weighted Verdict templates (one canonical shape — `score-lint.py`
parses these):

````markdown
## Scorecard
| Axis | Score | Evidence | Band & justification |
|---|---|---|---|
| Market demand | 7 | suspected | "urgent for a large segment" — rests on E2 |
| Distribution | 4 | confirmed | "outbound enterprise sales, long cycle" — rests on E5 |
| Feasibility | 8 | suspected | "focused 3-6 mo MVP on commodity parts" — rests on E1 |
| Differentiation | 6 | suspected | "clear wedge vs incumbent switching cost" — rests on E3 |
| Defensibility | 3 | unknown | "no moat mechanism named — capped at 3" |
| Revenue potential | 7 | suspected | "healthy ACV × reachable base" — rests on E4 |
| Timing | 8 | confirmed | "regulation took effect 2025" — rests on E6 |

## Weighted Verdict
Weights: Distribution 0.20 · Feasibility 0.18 · Market demand 0.17 · Timing 0.15 · Revenue 0.13 · Differentiation 0.10 · Defensibility 0.07
Vector: demand 7 · distribution 4 · feasibility 8 · differentiation 6 · defensibility 3 · revenue 7 · timing 8
Composite: 6.3 / 10
The weighting is an opinionated profile, not a fact; read the vector, not just the number.
````

## Escalation

- A score that needs facts the budget can't reach → mark the axis `unknown`, recommend
  **Park**, and route to a scoped `/product-discovery:ce-market-scan` or the DEAD-IF experiment.
- An idea that is really several ideas, or whose feasibility hinges on architecture →
  not this tool's job; route to `/core-engineering:ce-plan` once a single idea is chosen.
- The human disagrees with the verdict → record the **override**; the tool yields.

## Honest Limitations

- **A verdict, not validated fact.** The whole artifact is OPINIONATED decision support.
  The recommendation is the tool's opinion; the human owns the call.
- **Founder-agnostic — therefore a direction, not a mandate.** The score cannot see
  founder-market fit (the largest seed-stage variable), because the idea arrives without
  a team attached. Even `Pursue` means "a direction worth your own re-ranking against your
  unfair advantages," never "build this."
- **The weighting is an opinion.** The default profile suits a generic 2-5 person team; a
  different team, capital position, or thesis warrants different weights. The composite is
  only as defensible as its stated weights — which is why the vector is always shown.
- **Scores are only as good as the evidence behind them.** In `judgment-only` mode every
  score is `suspected`/`unknown`; even in `researched` mode, web data is stale, partial,
  and biased, and synthesis never reaches `confirmed`. An `unknown`-heavy scorecard should
  Park, not Pursue.
- **The lint checks shape, not truth.** `score-lint.py` verifies that every score is
  tagged, the knockouts were evaluated, the composite shows its shape, a DEAD-IF exists,
  and the recommendation is on-list. It cannot verify that a score is *correct*, that a
  cited source is *relevant*, or that a named moat is *real*. Those are human judgments.
- **Knockout floors are deliberately blunt.** Disqualifying on a single ≤ 3 will reject
  some ideas a specialist team could ship or reach; that bluntness is the point (a small
  generalist team is the default reader). Override the floor consciously at Stage 0, never
  silently.
- **Separate from `/product-discovery:ce-market-scan` and `/core-engineering:ce-brief`.** It renders the verdict market-scan
  refuses, but it is not a substitute for market-scan's disciplined evidence base, and its
  output crosses into the pipeline only as a labeled reference — its claims never enter a
  brief's Project Description as fact.
