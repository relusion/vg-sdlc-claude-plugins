# HITL Gate Standard

A gate is for a real human decision, not a progress acknowledgement. The person
at a gate must see enough evidence, alternatives, consequences, and authority
context to decide without reconstructing the workflow from scrollback.

This is contributor infrastructure. Installed skills carry the runtime behavior
inline; `scripts/authoring_check.py` protects locators, dialog limits, and the
shared glossary.

## The five rules

**R1 — Gate decisions, not work.** Ask only for a choice, consent, exception,
or authority-owned judgment. These are not gates:

- a deterministic validator returned PASS;
- a read-only inspection completed;
- a projection was generated from validated data;
- a probe or review found no issue;
- the workflow is moving to its next already-authorized stage.

Report those outcomes and continue. A deterministic failure stops or routes;
the dialog may not reinterpret it as PASS. A clean negative needs a human
decision only when it depends on a material human-owned classification, such as
accepting that inferred data is non-personal.

**R2 — Make the decision decidable in place.** Render concise Markdown before
the dialog. Show the evidence, assumptions, unknowns, cost of being wrong, and
recommendation. Every option says what happens next.

**R3 — Keep material authority human-owned.** Product scope, architecture,
security acceptance, destructive or irreversible operations, contract breaks,
accepted risk, and release are material. Give each independent decision its own
question, owner, evidence, and disposition. If the current person lacks evidence
or authority, offer gather evidence, route to owner, or park. Silence is never
approval.

Architecture selection is the exemplar: retain two to four complete options
when viable, explicit criteria and weights, repository evidence, trade-offs,
unknowns, recommendation, confidence, and sensitivity. At the same locator the
human can select, inspect or ask a question, adjust the frame or an option, or
park. Recompute after an adjustment; bind only the selected final snapshot.

**R4 — Show only what needs a decision.** Lead dense gates with “What needs your
decision.” Summarize deterministic passes and clean routine rows. Preserve any
signal whose aggregation would hide material scope or risk.

**R5 — Locate and constrain the interaction.** Print `Gate N of M — <name>` for
each gate that actually fires. Use at most four questions and four options per
question. Split a larger interaction under the same locator and state why. The
locator is also the `gate_index` telemetry key.

---

## The shared consequence-glossary

Every gate that prints these terms uses **this** plain-language gloss — so a human who
meets a term at two gates never sees two different explanations. Gloss *by consequence*.
(Source sections in `plan/stage-4-7-gates.md`.)

> **Runtime home:** the live copy of this glossary is **inline** in the `/core-engineering:ce-plan`
> Reachability gate (`plan/stage-4-7-gates.md` §6.6.1 Legend), which is what
> actually prints it; single terms also appear inline at the gates that use them
> (Sibling Plans glosses *recorded decision (ADR)*, §8.2.1 glosses *TZ-NNN* / *trust
> boundary*). This table is the **contributor mirror** — when you change a gloss, change
> it in both places. `authoring_check.py` (A9) enforces the sync mechanically:
> term-set parity plus each term's anchor phrase must hold in both copies.

**Disposition values** (§6.3 durable-state, §6.4 surface-removal):

| Term | Gloss (by consequence) |
|---|---|
| `owned-by: <feature>` | A feature in this plan provides this — **no action needed**. |
| `bridge: <desc>` | A temporary stand-in ships now; a **named later feature replaces it**. |
| `excluded: <reason>` | You're deciding this is **intentionally never built** — ship without it. |
| `deprecate: <window>` | The old surface keeps working for a **stated window**; a later feature removes it. |
| `shim: <desc>` | An **adapter** carries old callers onto the new surface. |
| `hard-break: <reason>` | The old surface **breaks immediately** — existing callers must change now. |

**Lifecycle terms** (§6.3):

| Term | Gloss |
|---|---|
| durable noun | Something the app **saves and a user expects to return to** (a saved search, an order, a profile). |
| reciprocal | The matching ability a saved thing needs: if you can **create** it, can you **find / change / delete** it? |
| `revisit` / `amend` / `retire` | **find it again** / **change it** / **delete-or-archive it**. |
| `retain` / `export` / `erase` | **how long it's kept** / **get a copy of it** / **permanently delete it** (the data-protection trio). |
| access-mode: `user-owned-mutable` / `system-or-append-only` | **a thing users create and edit** / **a log or record nobody edits after the fact** — drives *which reciprocals are mandatory*. |
| data-class: `personal` / `sensitive` / `operational` | **tied to a person (safe default)** / **regulated, high-harm (credentials, health, money)** / **no person behind it (config, logs)**. **Downgrading to `operational` drops the keep/copy/delete obligations — so a downgrade is the material move, not the default.** |
| select-to-continue exclusion | A screen that **lists things only to pick one and move forward** (a wizard) does **not** count as "find it again" — you can go forward, not back to manage. |

**Surface & security terms** (§6.4, threat-model):

| Term | Gloss |
|---|---|
| break-class: `contract-break` / `internal-only` | **An outside caller depends on this surface (default)** / **only this plan's own code uses it**. |
| `TZ-NNN` / threat-id | A **security-review obligation**: this feature must carry a security acceptance criterion. |
| trust boundary | A point where data or an action **crosses from less-trusted to more-trusted** (a request off the internet, input from a user). |
| surface-don't-force | We **flag it for review; we do not force a specific fix here**. |
| recorded decision (ADR) | A **technical decision written down once** so later features read and honor it instead of re-deciding. |

**Cross-feature protocol terms** (§8.2.2, interaction-contract):

| Term | Gloss |
|---|---|
| `IC-NNN` / `[CONTRACT: IC-NNN]` | A **cross-feature interaction obligation**: this feature must carry an acceptance criterion pinning a behavioural-protocol invariant or an architecture-determining NFR. |
| idempotency | A **replayed message or retry must not double-apply** (e.g. dedupe on a key). |
| at-least-once (delivery) | The consumer **will sometimes see a duplicate** — it must tolerate replay. |
| per-key ordering | Events for **one entity arrive in order** (no global order promised). |

**Scope discipline** (spine-wide — one lock brand, a different scope per stage):

| Term | Gloss |
|---|---|
| Scope Lock | The boundary a stage may not widen from inside — **frozen for this run; widening goes up a layer, never through it**. Each stage locks a different scope: the planned feature boundary (`/core-engineering:ce-spec`), the approved spec (`/core-engineering:ce-implement`), the frozen file set (`/core-engineering:ce-patch`), the framed decision space (`/product-discovery:ce-market-scan` · `/product-discovery:ce-idea-score`), the release decision (`/core-engineering:ce-ship-release`). |

**Evidence-strength meta-scale** (the one shape behind each genre's own three-state
evidence axis — the per-domain tag strings are load-bearing and stay distinct, this is the
shared mental model they specialize; full rule:
`docs/contributing/SKILL-AUTHORING.md` §5):

| Tier | Means | Each genre's own tag maps to it |
|---|---|---|
| `demonstrated` | a run, scan, or source **actively proved** it (reproduced / directly established) | probe-sec `confirmed` · probe-perf `measured` · probe-infra `scanner-confirmed` · market-scan `confirmed` |
| `read` | taken **directly from an artifact, manifest, or single observation** — recorded as-is, not reproduced and not reasoned | probe-sec `passive` · probe-perf `observed` · probe-infra `manifest-read` · domain `recorded` / `enforced` (a two-to-one source split: human-authored artifact vs enforcing code; `demonstrated` only via a consented live-run upgrade) |
| `inferred` | **model reasoning** — synthesis, extrapolation, or heuristic attribution | probe-sec `suspected` · probe-perf `inferred` · probe-infra `inferred` · market-scan `suspected` · domain `inferred` |

`market-scan`'s `unknown` is a **declared coverage gap** — the absence of evidence, below the
scale (`/core-engineering:ce-domain`'s known-unknown register entries are the same below-the-scale shape). A skill that declares a `Three-State Evidence` rule states its mapping on first use
(the literal `shared evidence scale` clause — `authoring_check.py` A11 enforces it). This
meta-scale is glossed at those runtime print-sites, not in the `/core-engineering:ce-plan` Reachability Legend
(the same treatment as the threat-model / interaction-contract terms above), so it is **not**
registered in `GLOSSARY_ANCHORS` — A11, not A9, keeps it and its per-skill mappings in sync.

---

## Templates

**Decision prompt** — render evidence first, then ask:

```text
Gate N of M — <name>

Decision [D-n] — <short title> [material]
Decision owner: <role or required expertise; say who may accept the risk>
Evidence:   <repository facts and deterministic results>
Unknowns:   <material uncertainty>
If wrong:   <concrete consequence>
Question:   <the question>
Options:
  A. <option> — <what happens if you pick this>
  B. <option> — <what happens if you pick this>
  C. Inspect or gather evidence — return to this locator
  D. Route to <owner> or park — no decision is recorded
Recommendation: <A/B> — <reasoning>
Confidence: <high/medium/low> — <basis and material unknowns>
```

**No-gate result** — report and continue:

```text
<check>: PASS — <short evidence reference>
Next: <already-authorized stage>
```

**Triage lead for a dense gate (R4):**

```text
What needs your decision (3):
  R1. <row> — <plain cost of leaving it as-is>
  R2. <row> — <plain cost>
  R3. ⚠ bulk: <N nouns> all excluded for "<reason>" — a posture, not a per-item call
Auto-resolved (12): all owned by a feature in this plan — no action. [details ↓]

Legend: <only the terms these rows use, from the shared glossary>
```

---

## Per-gate gloss checklist

When you retrofit or add a gate, gloss exactly the terms it prints (from the shared
glossary). The spine's gates and their load-bearing terms:

| Gate | Must gloss |
|---|---|
| `/core-engineering:ce-plan` §0 Sibling Plans | recorded decision (ADR) |
| `/core-engineering:ce-plan` §6.6 Reachability | durable noun, reciprocal, revisit/amend/retire, retain/export/erase, access-mode, data-class, owned-by/bridge/excluded, break-class, deprecate/shim/hard-break, select-to-continue |
| `/core-engineering:ce-plan` §8.2 threat-id confirm | TZ-NNN, trust boundary, surface-don't-force |
| `/core-engineering:ce-plan` §8.2.2 interaction-contract confirm | IC-NNN/[CONTRACT], idempotency, at-least-once, per-key ordering |
| `/core-engineering:ce-spec` §3.5 shared-shape | additive vs breaking, consumer, Boundary Conflict |
| `/core-engineering:ce-auto-build` end review | additive vs breaking, consumer, Boundary Conflict, provisional |

This standard applies across the adaptive plan and build path. A brief is
optional; explicit specification is conditional; compact work may let
implementation compose and lint the canonical spec artifacts. Material
decisions never disappear with the shorter route.
