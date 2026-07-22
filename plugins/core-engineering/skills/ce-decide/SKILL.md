---
name: ce-decide
description: |
  Weigh two or more TECHNICAL/architecture options for one decision and render an evidence-tagged Adopt/Adopt-with-mitigations/Spike-first/Reject recommendation plus a proposed ADR — situation-derived weights, knockout gates, a falsifiable DEAD-IF. Engineering-side verdict (unlike /product-discovery:ce-idea-score, which scores PRODUCT ideas).
  Triggers: choose between, compare, or weigh technical/architecture/fix options for one decision. For a complete cross-feature solution baseline rather than one option set, use /core-engineering:ce-architecture.
argument-hint: "[the decision + options, or a path to a /core-engineering:ce-debug diagnosis or problem statement] [--evidence measured|reasoned]"
allowed-tools: Read, Write, Glob, Grep, Bash, WebSearch, WebFetch, AskUserQuestion, Skill
---

# Decide

**Invocation input:** Decision to weigh (and optional `--evidence` mode / a source artifact path): $ARGUMENTS


Take **one decision** and **two or more candidate technical options**, and produce an
**opinionated, evidence-tagged recommendation**: score each option against a fixed
seven-axis engineering rubric with anchored 1-10 bands, **derive the axis weights from
the stated situation and show the derivation**, run each option through knockout gates
and a falsifiable kill-condition, aggregate by **gate-then-weight** (never a bare sum),
and render an **Adopt / Adopt-with-mitigations / Spike-first / Reject** recommendation
naming one option — then draft a **proposed ADR** the human promotes.

> **A verdict tool — on the engineering side of the line.** The framework keeps
> *product, security, and scope* verdicts with the human (`/core-engineering:ce-plan` decomposes, `/core-engineering:ce-brief`
> elicits, `/product-discovery:ce-market-scan` frames but never decides; `/product-discovery:ce-idea-score` is the one *product*
> verdict exception — both `/product-discovery:ce-market-scan` and `/product-discovery:ce-idea-score` now ship in the companion
> `product-discovery` plugin). Choosing among **technical options is engineering judgment the
> agent already exercises** — `/core-engineering:ce-spec` ends a material-decision prompt with
> `Recommendation: <A/B>`, `/core-engineering:ce-plan` runs a Sizing Gate. This skill makes that judgment
> *rigorous and standalone*. It is **not** a second product-verdict exception, and it is
> **not** route-only. The discipline that keeps it honest is the **Decision-Honesty
> Contract** below. The whole artifact is labeled **OPINIONATED engineering decision
> support — a recommendation, not validated fact.**

> **Where it sits.** A discovery / bridging utility (read-only on code, works on any
> repo, writes a dated never-overwritten snapshot). It is **one caller among several**,
> **human-triggered**: a `/core-engineering:ce-debug` fix-fork (after the cause is **confirmed** — a
> planned bug-route approach, or a plan-free investigation's settled cause), a `/core-engineering:ce-plan-audit` decision-quality finding, a `/core-engineering:ce-review`
> structural finding, a human's pre-plan architecture call, or — as a **rigorous upgrade of
> an inline recommendation** — an escalation from `/core-engineering:ce-spec`'s unknown-resolution or `/core-engineering:ce-plan`'s
> Sizing-Gate / candidate review on a consequential fork with no dominant option. Its output — a
> **proposed ADR** — is consumed downstream: the human promotes it into `docs/adr/` and
> `/core-engineering:ce-spec` ingests it, or the chosen option seeds `/core-engineering:ce-plan` (large) / `/core-engineering:ce-patch` (small). It
> renders a recommendation; it never writes code, mutates a plan, or auto-promotes the ADR.

## The Decision-Honesty Contract (the core discipline)

A recommendation is permitted; an *unaccountable* one is not. Six clauses, each
mechanically checked by `decide-lint.py`:

1. **Every score carries an evidence state** — `measured` (a benchmark, profiler run, or
   spike result — cite the number/source), `inferred` (engineering reasoning, codebase
   reading, or pattern-match — flagged), or `unknown` (no basis — a guess, flagged and
   excluded from any confidence claim). *No tag → the score is inadmissible.* A
   `measured` claim names the measurement; reasoning across the codebase is `inferred` at
   most, never `measured`. Where a score hinges on an unmeasured number, **the natural
   next step is `/core-engineering:ce-probe-perf`** — the only tool that proves a numeric breach.
2. **The fatal axes gate, they do not average** — **Efficacy** and **Constraint-fit** are
   **non-compensatory knockouts**: a score ≤ 3 on either **disqualifies that option**, no
   matter how strong the rest. An option that does not solve the problem, or that violates
   a hard constraint, cannot be bought back by a low build cost or a clean blast radius.
3. **The composite never travels alone** — each option's weighted total is printed *with*
   the shared weights, that option's full per-axis vector, and the standing disclaimer
   that the weighting is an opinion, not a fact.
4. **The weights are derived from the situation, in the open** — the axis weights are not
   a fixed house profile; they are adjusted from the default by the **stated situational
   factors** (production wedged → time-to-relief up; connector-wide blast → fit & reuse
   up), and **the derivation is written into the `## Situation` section.** No silent
   weighting; the weights sum to 1.
5. **A falsifiable kill-condition, not a failure story** — the recommendation carries one
   observable **DEAD IF \<X\>** line — *the recommendation is wrong if this is observed* —
   that a human could check, plus the cheapest experiment (often a spike or a `/core-engineering:ce-probe-perf`
   run) that tests it. A narrative "this might not work" does not satisfy this.
6. **Recommend, but the human owns the call** — the recommendation is the tool's opinion
   from one fixed set (Adopt / Adopt-with-mitigations / Spike-first / Reject) naming one
   option, and the artifact states plainly that the human may override it.

## Human-in-the-Loop — opinionated

Material judgment batches to two gates: **Stage 0** (the decision, the options, the
evidence mode, and the situational factors + any non-default weighting) and the **Stage 5**
recommendation read-back (the human may override the call before it is recorded).
Everything between is autonomous scoring against the fixed rubric. Reserve AskUserQuestion
for those two gates and any Stuck-rule question.

## ADR rule — draft, never promote

When the decision is **architecturally significant AND cross-feature** (the same two-test
gate `/core-engineering:ce-spec` uses — it shapes structure / a technology choice / a cross-cutting concern,
*and* a later feature will need it), the artifact ends with a **proposed ADR** in Nygard
form with `Status: proposed`. The tool **drafts**; only a human promotes it into
`docs/adr/NNNN-short-title.md` as `Status: accepted` (mirroring `/core-engineering:ce-spec`'s
`decided_by: human` rule and Autonomous-Mode park-on-ADR-worthy). A feature-local
decision gets **no** ADR — say so, and route it to the spec's Resolved Decisions instead.
ADR sprawl is the failure mode.

## Runtime Inputs

- **One decision + two or more candidate options (required):** from the invocation, the
  user, a `/core-engineering:ce-debug` Route section or classification, or a problem
  statement. If the options are missing or there is only one, ask once. **Do not invent
  options.** If only one option is genuinely viable, say so explicitly (the lint accepts a
  declared single-option case) — do not manufacture a strawman second option.
- **The situation (required):** the decision-shaping factors — urgency (is production
  impaired now?), blast scope (one call site or a connector-wide pattern?), reversibility
  tolerance, deadline, stakes (data loss / customer-facing / compliance?), team
  familiarity. Elicit briefly at Stage 0 if not supplied. These **derive the weights**.
- **Evidence mode (Stage 0):** `measured` (benchmarks / spikes / profiler numbers are
  available or will be gathered — preferred) or `reasoned` (no measurement; **every**
  score is then `inferred` or `unknown`, never `measured`, and the artifact says so).
- **Confirmed cause (when fed by `/core-engineering:ce-debug`):** weigh fixes only against a
  **confirmed** root cause. If the cause is still `suspected` (the Static Ceiling in
  `/core-engineering:ce-debug`'s plan-free mode), stop and route back to its discrimination plan —
  re-run `/core-engineering:ce-debug` — first; do not weigh fixes on un-settled evidence.
- **Optional weighting override:** a fully explicit non-default weight profile (Stage 0
  only, recorded) — but prefer deriving weights from the situation.

## Execution Contract

1. **Gate scope at Stage 0** — confirm the decision, the options (≥ 2 or a declared
   single-option case), the evidence mode, and the situational factors before scoring.
2. **Confirm before you weigh** — never weigh fix options against an unconfirmed cause;
   route back for confirmation first.
3. **Tag or omit** — every score is `measured` / `inferred` / `unknown`; never an
   untagged number. Codebase reasoning is `inferred` at most.
4. **Derive the weights from the situation, and show it** — adjust the default profile by
   the named factors; write the derivation into `## Situation`. Weights sum to 1.
5. **Gate before you weight** — apply the Efficacy / Constraint-fit knockout floors and
   any binary kill-conditions per option first; a disqualified option is marked such (its
   composite is informational only and it may not be the Adopt pick).
6. **Show the vector with each composite** — never a bare total; always weights +
   per-option vector + disclaimer.
7. **No silent caps** — when evidence is unreachable, mark the axis `unknown` and say so;
   never quietly stop.
8. **Recommend, label, and yield** — render one fixed-set recommendation naming one
   option, stamp it the tool's opinion, draft the proposed ADR only when ADR-worthy, and
   record the human's override if given.

---

## The Seven-Axis Engineering Rubric (fixed — `decide-lint.py` checks every axis is scored)

The **axes are fixed** (so the lint stays a real gate); only the **weights** move with the
situation. Each axis is scored **1-10** against its anchored bands, with an **evidence
tag** and a one-line justification.

| Axis | What it measures (operational) | Anchored bands (1 · 4 · 7 · 10) |
|---|---|---|
| **Efficacy** *(knockout)* | How completely the option solves the root cause / meets the requirement | 1 cosmetic — leaves the cause intact · 4 mitigates the common case, the cause can recur · 7 removes the cause for all realistic inputs · 10 makes the failure class structurally impossible |
| **Constraint-fit** *(knockout)* | Whether it respects the hard constraints (platform, public/back-compat contracts, SLO budget, compliance, the runtime model) | 1 violates a hard constraint (breaks a contract / forbidden runtime / busts the SLO) · 4 fits only with a waiver or a contract bump · 7 fits within the existing model · 10 fits natively, strengthens the constraint posture |
| **Reversibility** | One-way-door risk + blast radius — how cheaply it can be backed out, and how much surface/coupling it adds | 1 irreversible (a one-way schema / contract / data migration) · 4 reversible with real effort, wide blast · 7 revertible, contained blast · 10 behind a flag, trivially revertible, near-zero blast |
| **Time-to-relief** | How fast it ships the fix / value — decisive when something is impaired now | 1 weeks of new infra before any relief · 4 a multi-step build · 7 shippable in a focused sitting · 10 a minimal change that relieves immediately |
| **Build cost** | Implementation effort + the risk of introducing new defects (change-risk) | 1 large, risky change across many sites · 4 moderate, some risk · 7 a focused, testable change · 10 trivial, low-risk, well-covered |
| **Operability** | New run-time moving parts, failure modes, and observability / run cost it introduces | 1 a new service + new failure modes, hard to observe · 4 new state/process to watch · 7 within the current operational model · 10 fewer moving parts than today |
| **Fit & reuse** | Alignment with existing patterns + how broadly the fix generalizes (maintainability across the affected surface) | 1 a bespoke one-off that fights the conventions · 4 local fix only, no reuse · 7 follows the conventions, reusable in the area · 10 a pattern that generalizes across the whole affected surface |

**Knockout rule:** `Efficacy ≤ 3` **OR** `Constraint-fit ≤ 3` → that option is
**DISQUALIFIED**; its composite is informational only and it cannot be the Adopt pick.

### Default weight profile (the starting point — re-derived per situation at Stage 0)

| Axis | Default weight |
|---|---|
| Efficacy | 0.22 |
| Constraint-fit | 0.16 |
| Reversibility | 0.14 |
| Time-to-relief | 0.13 |
| Build cost | 0.11 |
| Operability | 0.12 |
| Fit & reuse | 0.12 |

`Composite = Σ (axis_score × weight)`, on a 1-10 scale, using the **situation-derived**
weights (sum 1.0). **Always print** the weights, each option's full per-axis vector, the
composite, and the disclaimer: *"the weighting is an opinionated profile, not a fact; read
the vector, not just the number."* A disqualified option shows its composite marked
informational.

### Situational weight derivation (the headline — no silent weighting)

Adjust the default profile by the stated factors, then re-normalize to sum 1.0, and
**record each adjustment in `## Situation`**. Typical moves:

- **Production impaired now / urgent** → raise **Time-to-relief** (and often lower Build
  cost / Operability, which matter less while firefighting).
- **Connector-wide / repeated pattern** → raise **Fit & reuse** (a fix that generalizes
  beats a local one).
- **Touches money / PII / a public contract / compliance** → raise **Constraint-fit** and
  keep **Reversibility** heavy (a one-way door here is expensive).
- **Throwaway / spike / low stakes** → raise **Time-to-relief** and **Build cost**, lower
  the rest.

### Binary kill-conditions (per option — DEAD if any true, gate before weight)

Mark an option DEAD (forces it out, regardless of composite) if it: violates a published
API / back-compat contract a shipped consumer depends on · requires a runtime / platform
the target forbids · provably breaches the latency / SLO budget · breaches a compliance /
data-residency obligation.

---

## Stage 0 — Scope, Situation & Weighting Gate

Summarize (Markdown): the decision (one sentence), the candidate options (≥ 2, or a
declared single-option case), the evidence mode (`measured` / `reasoned`), the situational
factors, and the **weight derivation** (default → adjusted, each move named). If fed by
a `/core-engineering:ce-debug` investigation, confirm the root cause is **confirmed**. Then ask (AskUserQuestion)
**Proceed / Adjust / Abort**. Score nothing before Proceed. In `reasoned` mode, state up
front that no score can be `measured`.

## Stage 1 — Evidence Pass (tag or omit)

Gather what the mode allows and record evidence rows: the claim, its state (`measured` +
the number/source / `inferred` / `unknown`), and the source (a benchmark, a profiler run,
a file:line, a doc). Read the relevant code read-only to ground `inferred` scores. Drop
unsourced *claims* rather than asserting them — but an axis with no usable evidence is
still scored and tagged `unknown`. No silent caps.

## Stage 2 — Score Each Option Against the Seven Axes

For **each option**, score all seven axes 1-10 against the anchored bands. Each score
gets: the **band it matches**, an **evidence tag**, and a one-line justification **citing
the evidence row / file:line**. A score on an `unknown` axis is an explicit low-confidence
guess.

## Stage 3 — Gates (per option)

For each option, evaluate the Efficacy / Constraint-fit knockout floors and the binary
kill-conditions, and record the result **on its own line, naming the option and its
result token** (e.g. `**Option A** — PASS`, `**Option B** — DISQUALIFIED`), so the
knockout is checkable per option. Then author the
single **DEAD IF** line for the *recommendation* — the observable that would make the
recommended choice wrong — with its cheapest experiment (often a spike or a `/core-engineering:ce-probe-perf`
run). A disqualified or DEAD option cannot be the Adopt pick.

## Stage 4 — Aggregate (gate-then-weight)

Using the **situation-derived weights**, compute each non-disqualified option's weighted
composite. Render the weights, each option's per-axis vector, its composite, and the
disclaimer. Never collapse to a bare number. State the trade-off plainly: *choose X if you
value A (which the situation does); choose Y if B.*

## Stage 5 — Recommendation & Read-Back

Render the recommendation from the fixed set, naming one option, annotated by the
on-disk scorecard (the gates that fired, the deciding axes, the open `unknown`s):

| Recommendation | When | Routes to |
|---|---|---|
| **Adopt** | one option clears the gates and wins the weighted composite with a clear margin | the chosen option → `/core-engineering:ce-plan` (large) / `/core-engineering:ce-patch` (small); promote the proposed ADR |
| **Adopt-with-mitigations** | a winner, but a named weak axis needs a guardrail (the mitigation is stated, and is what the DEAD-IF watches) | as Adopt, carrying the mitigation |
| **Spike-first** | a load-bearing axis is `unknown` and a cheap spike / `/core-engineering:ce-probe-perf` run would settle it | run the named experiment, then re-decide |
| **Reject** | every option is disqualified / DEAD, or none meets the requirement | stop — the scorecard is the recorded rationale; re-open the option set |

Read the recommendation back to the human (AskUserQuestion): **Accept / Override /
Adjust**. Record their decision — an overridden recommendation is stamped
`overridden by human`.

## Stage 6 — Lint & Write

Write the artifact (never overwritten):

```text
docs/decisions/<slug>/<date>.md
```

**Same-day collision rule:** resolve the path before writing. The first run uses
`<date>`; if it exists, use `<date>-2`, then `<date>-3`, and so on. Apply the
resolved key to every artifact from this run; never overwrite.

Then run the Decision-Honesty gate:

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/decide-lint.py" docs/decisions/<slug>/<date>.md
```

**PASS (0)** → done. **FAIL (1)** → a Decision-Honesty violation (an untagged score, a
disqualified option recommended for Adopt, a bare composite, weights that don't sum to 1,
a missing situation derivation, a missing DEAD-IF, an off-list recommendation): fix and
re-lint. **Could-not-run (2)** → check the contract by hand, **loudly**.

### Document Sections

```text
# Decision — <Title>   (OPINIONATED engineering decision support — a recommendation, not validated fact)
slug: <slug>   date: <date>   evidence-mode: <measured | reasoned>

## Decision            (the question being decided, one sentence)
## Situation           (the decision-shaping factors + the weight derivation: default → adjusted, each move named)
## Options             (>= 2 named options, or a declared single-option case)
## Evidence            (per-claim rows: claim — [measured|inferred|unknown] — source)
## Scorecard           (per option: ### Option <X> — <name>, then the 7-axis table)
## Gates               (per option: knockout floors + binary kill-conditions; PASS / DISQUALIFIED / DEAD)
## Kill-Condition      (DEAD IF <observable> — the recommendation is wrong if...; cheapest experiment)
## Weighted Verdict    (Weights line + per-option Vector + Composite lines + the standing disclaimer)
## Recommendation      (Adopt | Adopt-with-mitigations | Spike-first | Reject + the chosen option; human may override)
## Proposed ADR        (Nygard Context / Decision / Status: proposed / Consequences — only when architecturally-significant AND cross-feature; else say "feature-local — no ADR")
```

The Scorecard and Weighted Verdict templates (one canonical shape — `decide-lint.py`
parses these; `### Option …` per option, the seven axis rows, and the Weights/Vector/
Composite lines):

````markdown
## Scorecard

### Option A — <short name>
| Axis | Score | Evidence | Band & justification |
|---|---|---|---|
| Efficacy | 7 | inferred | "removes the cause for realistic inputs" — rests on E1 |
| Constraint-fit | 9 | inferred | "fits the existing runtime model" — rests on E2 |
| Reversibility | 7 | inferred | "revertible, contained blast" — rests on E3 |
| Time-to-relief | 8 | inferred | "shippable in a focused sitting" — rests on E4 |
| Build cost | 6 | inferred | "focused, testable change" — rests on E5 |
| Operability | 7 | inferred | "within the current operational model" — rests on E6 |
| Fit & reuse | 8 | measured | "generalizes across the affected surface" — rests on E7 |

### Option B — <short name>
| Axis | Score | Evidence | Band & justification |
|---|---|---|---|
| Efficacy | 9 | inferred | "makes the failure class impossible" — rests on E1 |
| Constraint-fit | 6 | inferred | "fits with a contract bump" — rests on E2 |
| Reversibility | 4 | inferred | "wide blast, hard to back out" — rests on E3 |
| Time-to-relief | 4 | inferred | "multi-step build before relief" — rests on E4 |
| Build cost | 3 | inferred | "new component + idempotency" — rests on E5 |
| Operability | 5 | inferred | "new service, new failure modes" — rests on E6 |
| Fit & reuse | 7 | inferred | "a generic harness, bigger commitment" — rests on E7 |

## Weighted Verdict
Weights: Efficacy 0.22 · Constraint-fit 0.13 · Reversibility 0.12 · Time-to-relief 0.22 · Build cost 0.08 · Operability 0.08 · Fit & reuse 0.15
Vector (Option A): efficacy 7 · constraint-fit 9 · reversibility 7 · time-to-relief 8 · build cost 6 · operability 7 · fit & reuse 8
Composite (Option A): 7.5 / 10
Vector (Option B): efficacy 9 · constraint-fit 6 · reversibility 4 · time-to-relief 4 · build cost 3 · operability 5 · fit & reuse 7
Composite (Option B): 5.8 / 10
The weighting is an opinionated profile, not a fact; read the vector, not just the number.
````

## Escalation

- A score that hinges on an unmeasured number → mark the axis `unknown`, recommend
  **Spike-first**, and route to `/core-engineering:ce-probe-perf` or a scoped spike.
- The cause is only `suspected` (fed from a `/core-engineering:ce-debug` plan-free investigation) →
  stop; route back to its discrimination plan — re-run `/core-engineering:ce-debug` — to confirm
  before weighing fixes.
- The decision is really a decomposition / boundary question → not this tool's job; route
  to `/core-engineering:ce-plan`.
- The decision is architecturally significant + cross-feature → draft the proposed ADR;
  the human promotes it into `docs/adr/`.
- The human disagrees with the recommendation → record the **override**; the tool yields.

## Honest Limitations

- **A recommendation, not validated fact.** The whole artifact is OPINIONATED engineering
  decision support. The call is the tool's opinion; the human owns it.
- **The weighting is an opinion.** The situation-derived weights are a judgment about what
  matters here; a different reading of the situation warrants different weights. The
  composite is only as defensible as its stated weights — which is why the vector and the
  derivation are always shown.
- **Scores are only as good as the evidence behind them.** In `reasoned` mode every score
  is `inferred`/`unknown`; even `inferred` codebase reasoning can miss a hidden coupling.
  An `unknown`-heavy scorecard should Spike-first, not Adopt. `measured` is the only state
  that proves a number — and proving a numeric breach is `/core-engineering:ce-probe-perf`'s job,
  not this tool's.
- **The lint checks shape, not truth.** `decide-lint.py` verifies that every option is
  scored and tagged, the knockouts were applied, the weights sum to 1 and the situation
  derivation is present, each composite shows its vector, a DEAD-IF exists, and the
  recommendation is on-list. It cannot verify that a score is *correct*, that the option
  set is *complete*, that the weighting *matches* the situation, or that the DEAD-IF is
  genuinely falsifiable. Those are human judgments. A clean PASS means the recommendation
  is *accountable*, not *right*.
- **Knockout floors are deliberately blunt.** Disqualifying on a single ≤ 3 will reject an
  option a specialist could make work; that bluntness is the point. There is no Stage-0
  knockout waiver here (unlike `/product-discovery:ce-idea-score`): an option that fails to solve the problem or
  violates a hard constraint is genuinely out — re-open the option set instead.
- **It decides nothing about product, security, or scope.** Those verdicts stay with the
  human. This tool weighs *engineering* options, drafts (never promotes) an ADR, and
  escalates a decomposition / boundary question to `/core-engineering:ce-plan`.
- **Garbage options in, garbage recommendation out.** It weighs the options it is given;
  it does not generate the option set, and a missing better option will never appear. If
  only a strawman second option exists, declare the single-option case rather than
  manufacturing a contest.
