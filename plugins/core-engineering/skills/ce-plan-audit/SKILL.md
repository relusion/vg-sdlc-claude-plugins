---
name: ce-plan-audit
description: |
  Independently audit a WRITTEN plan on disk — referential integrity + dependency-DAG soundness (a hard lint) plus model-judged decision quality, codebase-fit, decomposition, reachability, post-write scope drift, and re-projection closure of the read-only artifacts (threat-model / interaction-contract). Findings, not verdicts; never re-plans.
  Triggers: audit/validate/sanity-check a written plan before /ce-spec or /ce-auto-build. Plan-layer sibling of /ce-review.
argument-hint: "[plan-slug]"
allowed-tools: Read, Write, Glob, Grep, Bash, AskUserQuestion, Skill
---

# Plan Audit

**Invocation input:** Plan to audit (optional): $ARGUMENTS


Independently audit the **written plan artifact** of a `docs/plans/<slug>/`
directory — for structural integrity, the soundness of its decisions and
decomposition, fit to the codebase it was planned against, and any drift between
its files. It reports **evidence-backed findings** and **escalates**; it never
edits the plan, re-decomposes the project, or renders a go/no-go on the plan.

`/ce-plan` validates only the **in-flight candidate draft** and writes the artifact
exactly once (its Execution Contract bars writing before final approval). Every
`/ce-plan` gate — sizing, reachability, session-fit — runs on the conversation-held
draft, so **nothing re-checks the persisted plan** after a manual edit, drift, or
a hand-authored plan. This tool does. It also machine-**proves** the
dependency-direction and cycle-freedom invariants that `/ce-plan` itself only
*model-reads* (its Honest Limitations: "Dependency direction is not machine-proven").

This is the **plan-layer sibling of `review`** (which audits implemented
*code*) and the **static counterpart of `retro`** (which aggregates
*run-time* metrics and writes nothing). The discipline chain gains a pre-flight
auditor on the plan itself:

```
plan ─► { plan-audit } ─► spec ◄── implement ◄── { verify · review }
```

**Independence is the point.** An auditor reading the plan in a fresh context
catches what the planning conversation cannot — the same argument behind
`ce-auto-build`'s spawn model and the Challenger.

It runs in two modes:

- **Plan** (`<slug>` argument, or the sole plan) — audit one written plan.
- **Disambiguate** (no argument, multiple plans) — read `plans.json` and ask which.

## Runtime Inputs

- **Plan slug (optional):** e.g. `customer-portal`. Without one, resolve via `docs/plans/plans.json`; if multiple plans exist, ask which to audit.
- **The plan directory:** `docs/plans/<slug>/`.
- **Loaded (read-only):** `plan.json` (the manifest the lint checks — **multi-feature plans only**), `feature-plan.md` (index + Feature Table + Execution Checklist), `shared-context.md` (the **codebase profile** + the **Resolved Project Decisions ledger**), every `features/<id>.md`, the read-only re-projections `threat-model.md` and `interaction-contract.md` (audited for presence + re-projection closure, never re-assigned here — the §6.3 closure and §8/§10 edges own their data), and the `docs/plans/plans.json` registry (for cross-plan dependency resolution). For a **single-feature minimal-output** plan the inputs collapse to the lone `feature-plan.md` — it carries the codebase profile, decisions, and the single feature block inline; there is no `plan.json`, `shared-context.md`, or `features/` directory.

## Preconditions

- A **written plan artifact** exists at `docs/plans/<slug>/` — either a multi-feature plan (directory with `plan.json` + `features/<id>.md`) **or** a single-feature **minimal-output** plan (a lone `feature-plan.md`, no `plan.json`, accepted at `/ce-plan`'s Sizing Gate). If no plan is written at all, there is nothing to audit (a not-yet-written plan is `/ce-plan`'s job, not this one).
- Does **not** require any feature to be specced or implemented — this audits the plan, before downstream work.

## Execution Contract

0. **Session write lease (structural, first act).** `python3 "${CLAUDE_SKILL_DIR}/scripts/write-lease.py" --set --skill ce-plan-audit --allow 'docs/plan-audits/**'` — the write guard now enforces contract item 2 structurally. Last act: `python3 "${CLAUDE_SKILL_DIR}/scripts/write-lease.py" --restore-baseline`. A denied write mid-session means this contract and the action disagree — reconcile; never edit or delete the lease to proceed.
1. **Audit, do not fix.** Find weaknesses and escalate; never edit `plan.json`, `feature-plan.md`, `features/*.md`, or any other artifact. Same discipline as `/ce-review` and `/ce-verify`.
2. **Read-only on existing artifacts.** Write only the dated report under `docs/plan-audits/` and its `evidence/`.
3. **Grounded & evidence-bound.** Every finding cites `file:line` (the manifest entry, the ledger row, the feature block) or a lint failure. No evidence → no finding.
4. **Findings, not verdicts.** Report observations; the human triages. The audit never declares the plan good / bad, sound / unsound, or go / no-go. *(The structural lint is the one exception — a referential break is a fact, not an opinion, and it may assert FAIL.)*
5. **Judge the plan, not the product.** Audit plan internals against the brief / codebase profile *as the contract*. A disagreement with a settled **product** decision is out of scope — do not re-litigate why the product was chosen.
6. **Bounded — do not re-plan.** Audit the plan directory and the codebase profile it cites; one hop to confirm a cited surface exists. **Never** run a fresh decomposition — that is `/ce-plan`'s job, and a finding never expands scope.
7. **Two layers.** Machine-provable structural invariants run as a **hard lint** (`plan-lint.py`); soft judgments are **advisory findings**. Only the lint may block. *(The same `plan-lint.py` is `/ce-plan`'s **write-time twin** — `/ce-plan` Stage 9 runs it over the just-written plan directory before closing, so this audit is re-proving on disk what the plan already gated at write time, and additionally catching post-write hand-edits and drift.)*
8. **Never commit, push, or deploy.**

## Validation Dimensions

### Machine-provable — the hard lint (`plan-lint.py` over `plan.json` + the plan dir)

| Dimension | Checks (HARD — a FAIL is a fact) |
|---|---|
| **Referential integrity** (H1–H2) | every `plan.json` `file` resolves to an existing `features/<id>.md`; ids are unique |
| **Sequencing / DAG soundness** (H3, H5–H6) | `ship_order` present, unique, and the manifest is in ship order; every hard dep points to a strictly-**earlier** feature; **no direct or transitive cycle** — the invariant `/ce-plan` only model-reads, now proven |
| **Dependency resolution** (H4) | every hard/soft dep resolves — an unqualified id to an in-plan feature, a qualified `<slug>/<id>` to a plan registered in `plans.json` |
| **Bridge resolution** (H7) | every plan.json `bridges[].replaced_by` resolves to an in-plan feature with a strictly-**later** `ship_order` — a bridge is scaffolding retired by a valid FUTURE feature (`/ce-plan`'s "every bridge references a valid future feature", now proven, not self-attested) |
| **Re-projection presence** (H8) | a multi-feature plan carries **both** `threat-model.md` **and** `interaction-contract.md` on disk, each present and non-empty (a real projection **or** its attested negative — *No Security Surface* / *No Cross-Feature Protocol*); a missing/empty file is the silent omission the re-projection discipline forbids |

The lint also emits **advisories** (non-blocking): field completeness, ship-order gaps, orphan feature files, manifest↔feature-file `id` mismatch, boundary-owner category uniqueness, the ≤5-unknowns cap, Feature-Table coverage, and **closure-row disposition** (A10/A11) — each `feature-plan.md` §8 Durable-State reciprocal (revisit / amend / retire / retain / export / erase) and each Surface-Removal `continuity` cell dispositioned `owned-by:` / `bridge:` / `excluded:` (respectively `deprecate:` / `shim:` / `hard-break:`), never blank. The markdown-derived advisories (boundary-owner, unknowns, closure rows) are **best-effort** — the lint reads them from the feature files' YAML blocks and the `feature-plan.md` tables; the authoritative pass on those is the model-judged lens below.

### Model-judged — advisory, evidence-bound findings (capped at Medium)

Run every lens over the written plan; each finding names its lens. Walk all of them — do not early-exit.

| Lens | Catches |
|---|---|
| **Decision quality** | a decision in `shared-context.md`'s Resolved Project Decisions ledger with no alternative considered, no rationale, or poor fit to **this** codebase (the Challenger lens applied to plan decisions — demand options ≥2, tradeoffs, why-this-fits-here) |
| **Context / codebase-fit** | a feature scope that contradicts the recorded codebase profile, or a brief assumption the profile disputes that was inherited anyway |
| **Decomposition soundness** | hidden mega-features, duplicate / overlapping scope, or artifact-overhead-only features in the **written** `features/*.md` — flagged for human triage, never re-scored |
| **Risk realism** | the >1-high distribution without justification, or a high-risk feature missing its required justification |
| **Reachability** | a non-deferred journey with an orphaned entry or dead-ended exit in the written trace, or a step missing its verification modality |
| **Scope drift** | a `features/<id>.md` whose scope now exceeds what `feature-plan.md` / `plan.json` records — the post-write-edit case `/ce-plan` cannot see (it froze before write). **The dimension with no `/ce-plan` analog; surface it prominently.** |
| **Solution-fit** | an overall approach that ignores the baseline-health or interface-foundation signals the profile recorded (e.g. ignores a detected design system, assumes absent CI) |
| **Lifecycle closure** | a durable noun or removed surface in the written plan whose reciprocal (revisit / amend / retire · retain / export / erase) or continuity (deprecate / shim / hard-break) disposition is missing — the plan-side of `/ce-plan` §6.3–6.4 |
| **Re-projection closure** | a `threat-model.md` / `interaction-contract.md` `security_obligations` / `interaction_obligations` entry whose `TZ-NNN` / `IC-NNN` resolves to no row, or a re-projection that drifted from the §6.3 closure it mirrors — the write-time re-projection was hand-edited after write (a post-write case `/ce-plan` cannot see, like Scope drift). **Presence and non-emptiness are now the lint's hard H8**; this lens owns the deeper closure the lint cannot judge — never re-assign a data-class or re-decide an edge. **Multi-feature plans only** — a single-feature minimal-output plan omits both re-projections by construction (the *No Security Surface* / *No Cross-Feature Protocol* negatives are satisfied by the directory shape), so absence is not a finding there (mirrors the lint's single-feature N/A). |

**Bias: appropriate fit.** Flag both under-planned (gaps) and over-planned (gold-plating). A finding never expands scope.

## Cross-cutting rule — Findings, Not Verdicts

A finding is `{dimension, severity, file:line, observation, evidence, suggested escalation}`.

Severity:

- **High** — a structural-integrity failure the **lint** proves (dead `file` path, cycle, backward dependency, duplicate id / ship_order).
- **Medium** — a model-judged weakness with real downstream cost (a weak / unfit decision, scope drift, a mis-sliced feature, a missing reciprocal).
- **Low** — completeness gaps, style, a benign advisory.

A **model-judged** finding is at most **Medium** — never High: the model-judged lenses cannot *prove* a defect (they share the model's blind spots, exactly as `review`'s static lenses do). Only the **lint** asserts High / FAIL, and only within its machine-checkable scope.

The human triages each. Escalation routes — the same escalate-up chain as the rest of the toolset:

| Finding shape | Route |
|---|---|
| Structural break in the written artifact (dead path, cycle, backward dep, ship-order / id error) | → `/ce-plan` (amend & re-emit — only `/ce-plan` owns plan shape) |
| A feature is mis-scoped / mis-sliced / over-large / duplicated | → `/ce-plan` |
| Scope drift between a `features/<id>.md` and `feature-plan.md` / `plan.json` | → `/ce-plan` |
| A recorded decision looks weak or unfit, but the slicing is sound | a finding the human triages → feed the next `/ce-spec`'s Challenge gate (do **not** re-decide it here) |
| A recurring pitfall worth remembering | seed `docs/plans/patterns.md` (out of band) |

## Human-in-the-Loop — tiered

- **Stage 0 (material)** — confirm which plan and scope.
- **Stage 2 (tiered)** — triage. Lint FAILs (structural) are material, per-finding; model-judged Mediums batch with approve-with-veto; Lows are recorded.

No fix is ever applied by this workflow — triage routes each real finding to a skill that does.

## Autonomous Mode

When invoked as a pre-flight gate (e.g. by a future orchestrator before `/ce-spec` or `/ce-auto-build`), run without interactive gates:

- Run `plan-lint.py`, emit each finding with dimension, severity, `file:line`, evidence, and a suggested escalation, and write the dated report.
- **Only a lint hard FAIL (exit 1) blocks** — return it to the caller (a dead path / cycle is a fact). Model-judged findings are advisory and **never block** — the run is not gated on the model's own (fallible) judgment calls, the same posture as `review`'s autonomous mode.
- A could-not-run lint (exit 2) degrades to the model-judged review alone, recorded as a degradation (never a silent skip).
- Never edit the plan; never escalate interactively.

Outside autonomous mode, the tiered gates apply as written.

---

## Stage 0 — Load and Scope

Resolve the plan via `docs/plans/plans.json`. With no argument and multiple plans, ask which. Detect the plan **shape**: a multi-feature plan (a `plan.json` is present → both layers run) or a single-feature **minimal-output** plan (only `feature-plan.md` is present, no `plan.json` → the structural lint is **N/A**, model-judged lenses only). Stop and report only if **no** written plan artifact exists at all. Load the inputs listed under Runtime Inputs (read-only). Confirm scope with the human: *Proceed / Abort.*

## Stage 1 — Lint and Review

1. **Run the hard lint first** (multi-feature plans): `python3 "${CLAUDE_SKILL_DIR}/scripts/plan-lint.py" docs/plans/<slug>` (add `--json` to fold results programmatically). Map each **hard failure** to a High finding (dimension = its check: referential / sequencing / resolution / bridge-resolution / re-projection-presence); record each **advisory** as a Low finding (or fold into the matching model-judged lens). An **exit 2** means the lint could not run — fall back to the manual structural checks **loudly**, and record the degradation. For a **single-feature minimal-output** plan there is no `plan.json` to lint: record the lint line as **`N/A — single-feature minimal plan`** (by design, *not* a could-not-run degradation) and proceed to the lenses.
2. **Run the model-judged lenses** over `shared-context.md` (ledger + profile), the `features/*.md`, and the journey trace in `feature-plan.md`. Walk **every** lens regardless of findings — the human wants the complete picture.
3. Capture each finding with `file:line`, a short quoted snippet, and its dimension. Where useful, write a snippet to `docs/plan-audits/evidence/<date>-<slug>/F-N.txt`.

**Bounded:** the plan directory + the codebase profile it cites + one hop to confirm a cited surface. **No fresh decomposition** — flag a mis-slice as a finding; never re-cut it.

## Stage 2 — Triage and Report

Group findings by dimension, assign severity, suggest an escalation per finding, then triage (tiered, per the Findings-Not-Verdicts rule). Write the dated report to `docs/plan-audits/<date>-<slug>.md` — a **dated snapshot, never overwrite a prior run** (the convention of `docs/sec-probes/`, `docs/perf-profiles/`, `docs/ux-audits/`).

---

## Findings File Template — `docs/plan-audits/<date>-<slug>.md`

````markdown
# Plan Audit: <plan-slug>

> Generated by `/ce-plan-audit`
> Date: YYYY-MM-DD · Plan: docs/plans/<slug>/
> Lint: PASS | FAIL (<n> hard) | ERROR (fell back) | N/A (single-feature minimal plan) · Findings: T (H high, M medium, L low)

## Lint Summary (machine-provable)

```
<paste the plan-lint.py output — the H1–H8 result + advisories>
```

## Summary by Dimension

| Dimension | High | Medium | Low | Total |
|---|---|---|---|---|
| Referential / Sequencing / Resolution (lint) | … | — | — | … |
| Decision quality | — | … | … | … |
| Context / codebase-fit | — | … | … | … |
| Decomposition soundness | — | … | … | … |
| Risk realism | — | … | … | … |
| Reachability | — | … | … | … |
| Scope drift | — | … | … | … |
| Solution-fit | — | … | … | … |
| Lifecycle closure | — | … | … | … |
| Re-projection closure | — | … | … | … |

## F-N — <short title>  [<severity>]

- **Dimension:** <dimension>   ·   **Feature:** <id> (or plan-wide)
- **Location:** `docs/plans/<slug>/<file>:line` (or the lint check id, e.g. `H6`)
- **Observation:** <what the auditor saw>
- **Evidence:** ```<snippet>``` (or `evidence/<date>-<slug>/F-N.txt`)
- **Suggested escalation:** <skill>
- **Triage:** Escalate / Defer / Dismiss — <date>, by human
  ↳ Escalated to: <skill> | Deferred as: <note> | Dismissed: <reason>

## Triaged

| ID | Dimension | Severity | Triage | Escalation | Date |
|---|---|---|---|---|---|
| F-1 | sequencing | high | Escalate | /ce-plan | 2026-MM-DD |
````

---

## Closing

```text
Plan Audit complete: <slug>
Lint:        PASS | FAIL (<n> hard) | ERROR (fell back to manual) | N/A (single-feature minimal plan)
Findings:    <total> (<high> high, <med> medium, <low> low)
Triaged:     <triaged> · Pending: <pending>
Report:      docs/plan-audits/<date>-<slug>.md
```

Point to the next action: if any finding was escalated, name the first skill (usually `/ce-plan` for a structural break, or the next `/ce-spec` for a decision flagged for its Challenge gate).

---

## Escalation

Hard structural findings route to `/ce-plan`; decision-quality findings can feed the
next `/ce-spec` Challenge gate or `/ce-decide` when a technical option needs a scored
recommendation. This skill never rewrites the plan it audits.

## Honest Limitations

- **Raises the floor, not the ceiling.** A fresh context catches the planning conversation's blind spots but **shares the model's** — the model-judged lenses cannot catch *shared error*, and risk reading a sound plan as fine. Independent ≠ omniscient.
- **The lint checks STRUCTURE, not soundness.** A clean lint PASS means the plan is *well-formed* — resolvable, acyclic, ordered — **never** that its decisions or decomposition are *good*. That judgment is the model-judged lenses' (fallible) and the human's.
- **Not a re-plan.** It flags a mis-slice or a wrong boundary as a finding and routes to `/ce-plan`; it never re-decomposes. If the decomposition is genuinely wrong, the fix lives in `/ce-plan`, not here.
- **Decision quality is bounded by what is written.** It audits the ledger and feature blocks as the contract; a decision's real-world correctness is the human's call, and a weak-looking decision may be right for reasons the plan did not record (→ a `/ce-spec` Challenge-gate finding, not a verdict).
- **Markdown-derived advisories are best-effort.** Boundary-owner uniqueness and the unknowns cap are read from the feature files' YAML blocks by regex; an unparseable block is skipped, not failed. The model-judged lenses are the reliable pass on those.
- **Does not read the metrics stream.** Execution signals (testability, escalation, park/retry rates, complexity drift) are `/ce-retro`'s job — this audits the plan artifact's static soundness, before/independent of any execution. Keep that boundary.
- **False positives expected.** Triage is the human's; the workflow never auto-acts on a finding.
