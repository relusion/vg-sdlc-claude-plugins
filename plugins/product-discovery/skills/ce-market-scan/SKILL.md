---
name: ce-market-scan
description: |
  Evidence-bound market & competitive scan to validate a raw idea before /ce-brief — three-state evidence, every claim sourced and dated; frames the decision space and routes a disposition but renders NO go/no-go verdict (the Scope Lock).
  Triggers: market/competitor/differentiation research for an idea. For an opinionated score use /ce-idea-score; to first brainstorm MANY raw ideas into a ranked shortlist use /ce-idea-scout.
argument-hint: "[raw idea or product concept]"
allowed-tools: Read, Write, Glob, Grep, Bash, WebSearch, WebFetch, AskUserQuestion, Skill
---

# Market Scan

**Invocation input:** Raw idea / product concept: $ARGUMENTS


Produce a dated, evidence-bound **market context** document for a raw idea, so a
human can judge whether the idea is worth pursuing **before** `/ce-brief` shapes it
into planning input. The skill both **surfaces findings** *and* (Stage 3.5)
**assembles them into the decision space the reader faces** — Strategic Tensions,
Positioning Options, and Load-Bearing Unknowns — then (Stage 5) **closes the loop**:
it surfaces that space back to the human and **routes the idea's disposition**
(*Drop · Adopt · Adopt with changes · Reframe · Re-scan a gap*) without picking one. So
the report **guides without deciding**. It **renders no verdict**: it never decides
whether to build, never ranks or recommends a positioning, and its output is decision
*support*, not market truth.

This skill is a **thin orchestrator**: it SELECTs and lightly tailors questions from
the fixed Question Bank below (extensible — this is a STUB), rather than
free-generating a research plan.

> **Where it sits.** This is a **separate, optional, upstream** skill. It runs
> **before** `/ce-brief` and is **not** part of it. Its output is consumed downstream
> only as a **labeled Reference Document**; its claims never enter a brief's Project
> Description directly, and `/ce-brief` never performs or fabricates market research.

## Expanded Authority Surface

Unlike the elicitation skills, this skill **reads the open web** (WebSearch /
WebFetch) — a wider authority surface than `/ce-brief`'s repo glance. Web access is
therefore **gated** at Stage 0 (the user confirms scope + budget before any fetch),
and every external claim is bound to a citation.

## Three-State Evidence (the core discipline)

These states are **source certainty** — how well a *claim* is sourced; this skill's own
axis. On the shared evidence scale defined by the Skill Authoring Standard:
`confirmed`→demonstrated,
`suspected`→inferred, and `unknown` is a declared gap (no evidence) — even where a word
(`confirmed`, `suspected`) is shared with another genre, the tag strings stay this skill's own.
Every factual statement carries one of three states; **no source → no claim**:

| State | Meaning | Citation |
|---|---|---|
| `confirmed` | a **single source directly states** the claim | source URL + access date (required) |
| `suspected` | an **inference** — including any claim that **synthesizes, aggregates, or extrapolates across sources**, even when every input is individually cited | the inputs cited + flagged as inference |
| `unknown` | a gap the scan could not fill | listed explicitly as a coverage gap |

**Synthesis never graduates to `confirmed`.** Example: "the market is consolidating,"
drawn from three acquisition announcements, is `suspected`; each individual
acquisition is `confirmed`. Differentiation hypotheses are `suspected` at most.

## The Scope Lock — the framed decision space (the Stage-3.5 discipline)

Raw findings leave the reader to assemble the picture themselves. **Stage 3.5** does
that middle work — it assembles the scattered findings into the decision a reader faces
(**Strategic Tensions → Positioning Options → Load-Bearing Unknowns**) — and stops one
structural step short of a verdict. *Findings-Not-Verdicts* forbids deciding **from**
evidence; the **Scope Lock** forbids collapsing the **framed** space. They compose;
neither replaces the other.

Verdict-impossibility rests on **four composing devices**. For each, `scan-lint.py`
checks the part with an on-disk **shape**; the **semantic** part is a human-checked
convention the lint *cannot* verify — named honestly here so no one trusts a guarantee
that isn't there:

- **Plurality + independence** — ≥ 2 options, so there is no singular slot to write
  "do X". *Lint-enforced:* the count (≥ 2, or an explicit thin-option-set declaration).
  *Human:* that the options are genuinely **independent** (a distinct squeeze, a distinct
  belief).
- **Symmetric kill-condition** — every option carries its own death-condition, so none is
  the unmarked "safe" pick. *Lint-enforced:* a `Kill-condition:` line present on each
  option. *Human:* that it is the option's **own**, unfired death — a *fired*
  kill-condition is rendered *"kill-condition currently evidenced — the human judges
  whether that ends it"*, never a dead option.
- **No order, no valence** — so "better-evidenced" cannot be written as "better bet".
  *Lint-enforced:* no verdict / recommendation lexeme (high-recall). *Human:* the
  content-free option order (ascending first-cited finding id) — the lint does **not**
  check order.
- **Evidence-trace** — `suspected` at most, coining no new claim. *Lint-enforced:* every
  Finding id referenced **resolves** in the Findings Index. *Human:* that the cited
  finding is topically **relevant** (the lint checks resolution, not relevance).

A line that collapses the space — a **singular un-caveated** or ranked option set, a
kill-condition-less option, or an imperative probe — is a **Scope Lock violation**
`scan-lint.py` refuses. Like the framework's other linters it is a **high-recall
backstop, not a proof**: a verdict phrased in an unlisted idiom — or a covert steer
hidden in the option *order* or an *asymmetric* kill-condition — will slip past. The
real guarantee is the *composition* of the lint's shape-checks **plus** the human's
judgment on the semantic conventions, never the lexicon alone.

**The Stage-5 hand-off is route-only.** The close (Stage 5) re-opens the framed space to
the human and routes the disposition they pick — it **never recommends, ranks,
pre-selects, or scores** one. Its disposition options are fixed-order; each is annotated
only by *reference to framing already on disk* (a fired kill-condition, an open unknown),
never by an evaluation. The Scope Lock binds the **tool**, not the human: the human is
free to decide *drop*, but the recorded `## Disposition` must be stamped **`by human`**
(`scan-lint.py` H9) — the tool may not write a disposition the human did not choose.

## Runtime Inputs

- **Raw idea / product concept (required):** from the invocation or the user. If empty,
  ask once. Do not invent a concept.
- **Focus + query budget (Stage 0):** which sections matter most, and a bounded
  number of searches/fetches — stated and enforced (no silent overruns).

## Execution Contract

1. **Gate web access at Stage 0** — confirm the idea, focus, and query budget before
   any search or fetch.
2. **Source or silence** — every factual claim is `confirmed` (single source + date),
   `suspected` (inference/synthesis, flagged), or omitted. Never assert uncited.
3. **Synthesis is `suspected`** — aggregating or extrapolating across sources never
   yields `confirmed`, even when all inputs are cited.
4. **Findings, not verdicts** — surface signals, competitors, and risks; never decide
   go/no-go or recommend building.
5. **No silent caps** — when the budget is exhausted, say so and record uncovered
   segments as `unknown`; never quietly stop or quietly exceed.
6. **Never feed claims into the brief** — the output is a labeled Reference Document
   only.
7. **Frame, don't decide (Scope Lock)** — the Stage 3.5 synthesis tier may map the
   decision space but never collapse it. Positioning Options are emitted plural (≥ 2 — or,
   when the evidence grounds fewer, an explicit **thin-option-set declaration**, never a
   single un-caveated option), independent, each with its own kill-condition, in
   content-free order, **never ranked, never recommended**; an option whose kill-condition
   is already evidenced is rendered *"kill-condition currently evidenced — the human judges
   whether that ends it"*, never a dead option; Load-Bearing Unknowns are gaps to close,
   never next steps to take. Evidence state describes the **grounding of the framing**,
   never the **merit of a position**. `scan-lint.py` enforces the *checkable shape* (the
   plurality count, a kill-condition line per option, finding-id resolution, the no-verdict
   lexicon); independence, content-free order, an unfired kill-condition, and topical
   relevance are **human-checked conventions the lint does not verify**.

## Two-Surface Rendering

Render the idea/focus/budget summary and the full report as Markdown in the
conversation. Reserve AskUserQuestion for: the Stage-0 **Proceed / Adjust / Abort**
gate, the Stage-5 **disposition hand-off** (route-only — never a recommendation), and
any Stuck-rule questions.

---

## Stage 0 — Scope & Budget Gate

Summarize (Markdown) the idea, the sections you intend to cover, and the proposed
query budget. Then ask (AskUserQuestion) **Proceed / Adjust / Abort**. Fetch nothing
before Proceed.

The **Stage 3.5** synthesis sections (Strategic Tensions / Positioning Options /
Load-Bearing Unknowns) are **zero-fetch** — they assemble findings already gathered, so
this single gate covers them. The one exception, disclosed here (no silent post-gate
fetch): a Load-Bearing Unknown **may, on explicit human authorization, redirect any
remaining Stage 4.2 budget** toward closing that gap.

## Stage 1 — Select Questions from the Bank

SELECT and lightly tailor from the fixed Question Bank (do not free-generate):

- **Problem framing:** is the problem real, who has it, how is it solved today?
- **Market & segments:** who is the buyer/user, how large/segmented, what trend?
- **Competitors & alternatives:** direct competitors, adjacent tools, status-quo/DIY.
- **Differentiation:** what would make this distinct; what is the wedge? (`suspected`)
- **Risks & unknowns:** adoption, regulatory, incumbent, and timing risks.

Tailoring is allowed; inventing whole new research themes is a STUB-extension
decision — flag it, do not do it silently.

## Stage 2 — Research (source-or-silence)

Run searches/fetches within budget. For each finding, record the claim, its state,
and its citation (URL + access date for `confirmed`). Drop anything you cannot
source rather than asserting it.

## Stage 3 — Compose the Document

Write the sections below as Markdown. At the prose-composition step for **Problem
Framing** and **Differentiation Hypotheses**, hold synthesized claims at `suspected`.
Every line carries its state.

## Stage 3.5 — Frame the Decision Space  *(Scope Lock)*

A **zero-fetch synthesis** pass over the findings already composed — it reads nothing
new; it assembles them into the decision the reader faces. **Conservative: no finding →
no option** — every tension, option, and unknown must trace to a `confirmed` /
`suspected` / `unknown` row already in the document. Honor the **Scope Lock** above.

- **3.5.a — Index findings.** Give every `confirmed` / `suspected` row a stable id
  (`F1`, `F2`, …) and emit the **Findings Index** (`F# = <short> [state]`). Every such
  row gets an id — no silent omission of an inconvenient finding.
- **3.5.b — Strategic Tensions.** One templated line per tension — *"Given `<F#[, F#]>`,
  `<position>` is `<squeezed | contradicted | pressured>`."* It describes **pressure on a
  position**, carries no action verb, is `suspected` at most, and cites ≥ 1 finding id.
- **3.5.c — Positioning Options.** ≥ 2 **independent** options, each escaping a distinct
  squeeze and resting on a distinct load-bearing belief, each with its **own**
  kill-condition. Content-free order; **not ranked, not recommended**. If the findings
  imply fewer than two grounded options, **say so and stop** — do not manufacture a second
  to satisfy the floor, and do not present a single option as "the" answer. Write a
  standalone line beginning **"Fewer than two grounded options"** (the Scope-Lock-honest
  thin-set declaration `scan-lint.py` recognizes) and record it as a coverage limit, not a
  silent verdict.
- **3.5.d — Load-Bearing Unknowns.** The gaps whose resolution would most reshape the
  option set, phrased as **open questions** (never imperatives, never "cheapest" /
  "first"), each naming the existing row it bears on and the options it reshapes.
- **3.5.e — Lint.** Run the Scope Lock gate over the composed artifact:

  ```bash
  python3 "${CLAUDE_SKILL_DIR}/scripts/scan-lint.py" docs/market-scans/<slug>/<date>.md
  ```

  **PASS (0)** → close. **FAIL (1)** → a Scope Lock violation (singular / ranked /
  kill-less option, dangling finding id, imperative or ranked unknown, verdict lexeme):
  fix and re-lint. **Could-not-run (2)** → check the Scope Lock shape by hand, **loudly**.

## Stage 4 — Budget & Close

- **4.1** Tally coverage; list every uncovered segment as `unknown`.
- **4.2 Budget branch (no silent caps):** budget remains → spend it on the
  highest-value gap; budget exhausted → either **decline** and record the gap as a
  coverage limit, or (on explicit human authorization) record a **Stop** and proceed
  against the new cap. Never silently deny or exceed.
- **Write** the artifact (never overwritten):

```text
docs/market-scans/<slug>/<date>.md
```

(A per-idea slug folder holding dated snapshots — an idea is re-scanned over time.
This deliberately differs from sibling tools' flat one-file-per-run layout under
`docs/<tool>/`.)

### Document Sections

```text
# Market Scan — <Title>   (UNVERIFIED market context — not validated fact)
slug: <slug>   date: <date>

## Problem Framing
## Market & Segments
## Competitors & Alternatives
## Differentiation Hypotheses   (suspected at most)
## Findings Index            (Stage 3.5 — F# = <short> [state], one per confirmed/suspected row)
## Strategic Tensions        (Stage 3.5 — suspected; pressure on a position, not an action)
## Positioning Options       (Stage 3.5 — NOT RANKED; ≥ 2 independent, each with its own kill-condition)
## Load-Bearing Unknowns     (Stage 3.5 — gaps to close, not steps to take)
## Risks & Unknowns
## Sources   (URL + access date per confirmed claim)
## Disposition               (Stage 5 — appended after the close: <choice> — by human, <date> + routed next step)
```

The Stage-3.5 tier (templates — every line traces to a Finding id, stays `suspected` at
most, and carries no verdict):

````markdown
## Findings Index
- F1 = <short statement> [confirmed]
- F2 = <short statement> [suspected]

## Strategic Tensions   (suspected — synthesis, not verdict)
Evidence state describes grounding of the FRAMING, not relative merit of any position.

- Given F1 + F2, the <position> is <squeezed | contradicted | pressured>. [rests on: F1, F2] (suspected)

## Positioning Options   (NOT RANKED — framing, not recommendation)
Evidence state describes grounding of the FRAMING, not relative merit of the POSITION.

### Option — <label>
- **Escapes the squeeze of:** <which tension/finding it side-steps> [state]
- **Load-bearing belief that must hold:** <falsifiable belief> [state]
- **Kill-condition (its own death):** <the evidenced thing that, if true, ends THIS option> [rests on: F#]

### Option — <label>
- **Escapes the squeeze of:** <a DISTINCT squeeze> [state]
- **Load-bearing belief that must hold:** <a DISTINCT belief> [state]
- **Kill-condition (its own death):** <its own evidenced death-condition> [rests on: F#]

## Load-Bearing Unknowns   (unknown — gaps to close, not steps to take)
- Whether <X> remains **unknown**; resolving it would reshape Options <…>. Relevant existing row: F#. (unknown)
````

## Stage 5 — Close & Hand Off the Disposition

After the artifact is written, **close the loop**: surface the framed space back to the
human and route the disposition they choose. **Frames, never decides** — no disposition
is recommended, ranked, pre-selected, or scored; every annotation only points at framing
already on disk. This is the one interactive *exit* (Stage 0 is the interactive entry); it
lives entirely outside the Scope Lock's framing tier and never re-opens Stage 3.5.

- **5.1 Read back, don't re-derive.** From the just-written artifact, read which
  Positioning Options carry a *fired* kill-condition, which Load-Bearing Unknowns are
  still open, and the segment coverage tally. Coin nothing new here.
- **5.2 Render the close (two-surface).** Print, as Markdown:

  ```text
  ## Closing — <idea>
  Covered <x>/<y> segments · <N> options framed · <M> load-bearing unknowns open
  Artifact: docs/market-scans/<slug>/<date>.md
  ```

- **5.3 Ask the disposition** (AskUserQuestion; fixed, content-free order; **no
  `Recommendation:` / `Lean:` line**). Each option is annotated only by the on-disk
  framing that bears on it — a *fact* ("Options A, B kill-conditions are evidenced"),
  never an evaluation ("you should drop"):

  | Disposition | Annotated by (factual, optional) | Routes to |
  |---|---|---|
  | **Drop** | the squeeze each option fails to escape / kill-conditions evidenced | Stop — the scan stands as the recorded rationale |
  | **Adopt as-is** | — | `/ce-brief`, idea unchanged |
  | **Adopt with changes** | the named option's escape it narrows to | `/ce-brief`, carrying the narrowing |
  | **Reframe** | the named Positioning Option it pivots to | `/ce-brief`, carrying that option |
  | **Re-scan a gap** | the named open Load-Bearing Unknown | a fresh dated scan scoped to that gap |

- **5.4 Record + route the human's pick** (never the tool's):
  - **Append** a `## Disposition` section to the artifact — `<choice> — by human, <date>`
    plus the routed next step. The `by human` stamp is mandatory (`scan-lint.py` H9); the
    tool may not record a disposition the human did not choose.
  - **Drop** → stop. **Adopt / Reframe** → **name the skill** ("Run
    `/ce-brief`; start from `<the idea | Option X's positioning>`; this scan
    is your context") — **never auto-launch `/ce-brief`, and never feed its claims forward**
    (the claim-consumption seam stays unwired; see Honest Limitations). **Re-scan a gap**
    → name the unknown and offer a fresh dated scan scoped to that segment.
  - **Re-lint:** re-run `scan-lint.py` over the updated artifact so the appended record is
    gated (H9 confirms the `by human` stamp).
- **5.5 Stuck rule.** If the framed space is empty (a thin-option-set declaration, no
  options), still run the prompt, but offer only **Drop / Re-scan a gap / Park** — never
  fabricate options to fill the menu.

## Escalation

This skill frames and routes; it never decides. Human-selected dispositions route to
`/ce-brief` for planning input, `/ce-idea-score` for an opinionated idea verdict,
another `/ce-market-scan` for a named evidence gap, or stop/drop. Claims remain
context, not automatically consumed requirements.

## Honest Limitations

- **Not validated fact.** The whole document is labeled UNVERIFIED market context; it
  is decision *support*, not market truth, and it renders **no** go/no-go verdict.
- **Coverage is bounded by tooling, not just budget.** Robots-blocked, JS-rendered,
  paywalled, or unindexed public pages may be unreachable — **absence of a citation
  is not absence of a source.**
- **Web data is stale, partial, or biased.** Search ranking and recency shape what is
  found; treat a single-source `confirmed` claim as "as stated by that source."
- **STUB.** The Question Bank and section set are a starting point, intentionally
  extensible; a richer bank (pricing teardown, sizing models) is a later content
  decision, not assumed here. The Stage-3.5 tier (Tensions / Options / Unknowns) is an
  explicit, intentional extension of the section set, not improvised at runtime.
- **Frames the decision space; routes it, never decides it.** Stage 3.5 maps which
  positions survive on which belief and which gaps reshape the set; it renders **no**
  go/no-go, ranks **no** option, and recommends **no** pivot/build/kill. The Stage-5 close
  then **routes the disposition the human picks** — it names the next skill for the
  *adopt / reframe / re-scan* the human chose, but recommends, ranks, and pre-selects
  **none** of them, and stamps the record `by human`. Option-framing is decision
  *support*, never a recommendation; the human chooses among the framed options, and both
  the framing tier and the close refuse to choose for them.
- **The option set is bounded by this run's coverage, and `suspected` at most.** Options
  are only as complete as the findings gathered — a position you'd prefer may be absent
  (adding one is yours), and "no finding → no option" keeps the tier inside the evidence
  spine. Every tier line is cross-finding synthesis, so it can never be `confirmed`. It
  does not validate demand, size markets, price, or run the tests its Unknowns point at.
- **No convergence verdict over time.** Across the dated snapshots, a shorter option set
  or fewer unknowns is **not** "progress" and carries no valence — whether any reshape is
  an improvement is solely the human's judgment. A lone surviving option is declared a
  **thin option set** ("fewer than two grounded options") — a coverage limit, never a
  recommendation to pick it.
- **The lint checks shape, not semantics.** `scan-lint.py` enforces the plurality count,
  a kill-condition line per option, finding-id resolution, and the no-verdict lexicon —
  it does **not** verify that two options are genuinely independent, that a kill-condition
  is the option's own and unfired, that the option order is content-free, or that a cited
  finding is topically relevant. Those four are conventions the **human** checks; a covert
  steer hidden in option order or an asymmetric kill-condition can pass every check.
- **The no-verdict lexicon is a high-recall backstop, not a proof.** A verdict phrased in
  an idiom its lexicon doesn't list will slip past; the guarantee is the *composition* of
  the shape-checks plus the human, not the verb grep. A lint hit is a material finding the
  human adjudicates.
- **Separate from /ce-brief.** This skill performs research; it does not elicit intent
  or plan. Its output — including the Stage-3.5 tier — crosses into the pipeline only as
  a labeled Reference Document; raw claims never enter a brief's Project Description as
  fact. *(A future, optional `/ce-brief` seam may let the Sparring Partner consume the tier's
  options one probe at a time, state-labeled — deliberately not wired here.)*
