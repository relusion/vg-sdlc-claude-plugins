# HITL Gate Standard — every decision decidable in place

A presentation discipline for **every interactive Human-in-the-Loop (HITL) gate**
in the framework. One rule governs it: *a human standing at a gate must have enough
context and the right authority, in the place the decision is made, to choose well —
without scrolling back, already knowing framework jargon, guessing outside their
role, or rubber-stamping.*

This is primarily a **contributor discipline** — like the skill-naming rule and
the doc-currency rule (CLAUDE.md). Prose quality and decision sufficiency cannot be
mechanically proved, so review and this document remain authoritative. Structural
backstops in `authoring_check.py` protect the shared glossary, gate-locator
discipline, and the four-question/four-option harness limit. When you add or edit any
gate that asks the human to choose, make it conform.

> **This doc is authoring infrastructure — it does not ship with either plugin and no
> skill reads it at runtime.** This file lives outside the plugin packages in the
> development repo's `docs/contributing/` directory, so
> a path like `docs/contributing/HITL-GATE-STANDARD.md` would not resolve in a user's project. Every
> gate is therefore **self-sufficient**: its behavior, and every gloss it prints, live
> **inline in the skill text**. Skills cite the standard by name ("HITL Gate Standard
> R4"), never by a runtime file path. The **runtime home of the shared glossary** below
> is `/core-engineering:ce-plan` §6.6, which prints it; this doc mirrors it for contributors.

> **The two in-repo exemplars** — the target UX already exists; copy these shapes:
> - **R1 (decidable-in-the-dialog):** `spec/SKILL.md` → *Human-in-the-Loop*
>   → the **Decision prompt format** block (the `A. <option> — <consequence>` +
>   `Recommendation:` shape) and the **Two-Surface Rendering Rule**
>   (`plan/stage-4-7-gates.md` §5.3).
> - **R2 (evidence-first verdict):** `implement/SKILL.md` Stage 2 manual
>   verdicts — *"Do the legwork first … so the human renders only the judgment."*
> - **R3 (material vs routine):** `spec/SKILL.md` → *Human-in-the-Loop — tiered*.

---

## The five rules

**R1 — Decidable-in-the-dialog.** Render the analysis as Markdown first (the
Two-Surface Rendering Rule), then ask with `AskUserQuestion`. **Every option carries
its consequence *in the option text*** — what happens if you pick it — so the compact
dialog is sufficient on its own. Never leave a load-bearing consequence only in
scrollback.

**R2 — Evidence-first verdict.** For any attestation, **do the legwork and present
the evidence the human is judging; ask only for the judgment.** Never ask a human to
*confirm a model-derived assertion* (a security obligation, a data-class, an
additive-vs-breaking call, a foundation exception) **without showing its basis and
the concrete cost if it's wrong**, in plain terms the human can weigh. A bare
"confirm the threat-ids?" restated under a new heading does **not** satisfy R2 — the
basis and cost-if-wrong must be *rendered*.

**R3 — Isolate material attestations and route authority.** A *material* judgment
(security model, data-class, destructive/irreversible op, scope/boundary, a contract
break) gets its **own** question — never a bullet inside an informational dump that
rides through on a single "Approve"/"Write". Up to four independent material
questions may share one `AskUserQuestion` call, but each keeps its own evidence,
owner, answer, and checkpointed disposition. A negative assertion is still material;
"nothing detected" is not an exception. Routine items bulk-approve-with-veto.

Every material question names the **decision owner or required expertise**. If the
person at the gate lacks that authority, or the evidence is insufficient, the dialog
must provide a safe **gather evidence / route to owner / park** path. `Abort` is not a
substitute for escalation, and silence is never approval. (Material vs routine: see
the `spec` tiering exemplar.)

**R4 — Triage dense gates.** When a gate prints many rows, **lead with "What needs
your decision"** — only the rows that need a human call (undispositioned, escalated,
or a non-default override). Collapse the auto-resolved rows to a count — **but never
collapse a no-silent-caps signal** (e.g. a bulk-`excluded` run; see the glossary).
**Gloss internal vocabulary on first use**, by *consequence* not by name, reusing the
shared glossary below.

**R5 — Locate & label.** Print a locator — **"Gate N of M — \<name\>"** — at each
interactive gate, where **M is the gates that will actually fire this run** (compute
it; conditional gates change it — say so, never a hardcoded constant). Label every
option by its consequence/what-happens-next, not a bare verb. A round that needs more
than the harness allows per `AskUserQuestion` call (≤ 4 questions, ≤ 4 options each)
**splits with a stated reason** — no silent cap. **The locator doubles as the
telemetry key:** the same `Gate N of M — <name>` string a gate prints is what its
`attestation` metrics line records in `gate_index` (the metrics-stream schema in
`/core-engineering:ce-retro`'s `SKILL.md`) — one vocabulary for the human *and* the audit trail,
never a second one to drift.

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

**Decision-prompt (R1/R3)** — Markdown analysis first, then the dialog:

```text
Gate N of M — <name>

Decision [D-n] — <short title>   [material | routine]
Decision owner: <role or required expertise; say who may accept the risk>
Context:    <1–3 sentences, jargon glossed>
Question:   <the question>
Options:
  A. <option> — <what happens if you pick this>
  B. <option> — <what happens if you pick this>
  C. Need evidence / route to <owner> / park — no decision is recorded
Recommendation: <A/B> — <reasoning>
Confidence: <high/medium/low> — <basis and material unknowns>
```

**Evidence-first attestation (R2)** — for a model-derived assertion:

```text
<Assertion>, because: <the concrete basis — the boundary crossed / the noun's
attribute / the consumers enumerated>.
If this is wrong: <one concrete sentence — what ships unguarded / what breaks>.

Confirm  /  Override (state the reason)  /  Need evidence or route to owner
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
| `/core-engineering:ce-auto-build` end-review (shared-shape attestation) | additive vs breaking, consumer, Boundary Conflict, provisional |

This standard is applied across the `/core-engineering:ce-brief → /core-engineering:ce-plan → /core-engineering:ce-spec → /core-engineering:ce-implement` spine; see
`docs/HOW-IT-WORKS.md` §6 (*Human owns judgment*). `/core-engineering:ce-spec`'s resolve-unknowns and
`/core-engineering:ce-implement`'s manual-verdict gates are the **exemplars** the rest conform to.
