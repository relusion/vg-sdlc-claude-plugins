---
name: ce-auto-build
description: |
  Autonomously spec + implement every feature in a plan in ship order as a spawning orchestrator — a fresh agent per feature, on-disk gates between them, a mandatory end-review; never auto-commits.
  Triggers: auto-build/autopilot/batch spec+implement a whole plan's features unattended.
argument-hint: "[plan-slug] [range e.g. 01..05] [--resume] [--parallel worktree]"
allowed-tools: Read, Write, Edit, Glob, Grep, Bash, AskUserQuestion, Skill, Task
disable-model-invocation: true
---

# Auto Build

**Invocation input:** Plan and optional range: $ARGUMENTS


Drive the full `spec → implement` cycle across every feature in a plan, in ship
order — as a **spawning orchestrator**. This skill does not do the per-feature work
itself; it **spawns a fresh agent for each feature's spec and each feature's
implement** — preferring the plugin-shipped `spec-author` and `spec-impl` custom
agents when the Claude Code runtime exposes named agents — enforces the gates
between them, owns the run-level state, and renders live per-feature status. It
is the toolset's autopilot — its most consequential skill.

**Supervised autonomy, not fire-and-forget.** The human's judgment is *batched* to
two interactive bookends (Stage 0 kickoff, Stage 3 end-review); the per-feature
pipeline in between is autonomous.

**On-demand modules.** Off-common-path detail loads only when it is actually
needed, so the common run never pays its context: three off-by-default gates — the
**Diagnose Gate** (`${CLAUDE_SKILL_DIR}/gate-diagnose.md`, diagnose mode on),
**Enrich-Parks** (`${CLAUDE_SKILL_DIR}/gate-enrich-parks.md`, enrich-parks mode on), and
**Worktree Parallelism** (`${CLAUDE_SKILL_DIR}/gate-worktree.md`, parallelism = worktree,
backed by `${CLAUDE_SKILL_DIR}/scripts/worktree-preflight.py`) —
plus the write-time **Run Report Template** (`${CLAUDE_SKILL_DIR}/run-report-template.md`,
loaded at the Stage-3 end-review when the report is written). The stage procedures themselves load the same way — see *How to Run This Workflow* below.

**The gate modules and stage files named below are bundled in this skill's own directory.** Read each at `${CLAUDE_SKILL_DIR}/<file>` — `${CLAUDE_SKILL_DIR}` is the environment variable that resolves to this skill's directory regardless of the current working directory. Resolve it once if needed (`ls "${CLAUDE_SKILL_DIR}"`) and read each file by its resulting absolute path; **never load a companion file by bare name** — in an installed plugin the working directory is the user's project, so a bare name finds nothing and triggers a filesystem search.

## Architecture — a spawning orchestrator

```
Stage 0 — kickoff (THIS skill, interactive)
  build preset (Gate 1) · foundational-unknown sweep · capability preflight · bounds · destructive/VC policy
  │   assemble args (ship-ordered features, foundational decisions, ledger digest, bounds)
  ▼
Stage 1+2 — per-feature spawn loop (THIS skill, autonomous, live task-list status)
  for each feature, in ship order, SEQUENTIALLY:
    ① spec-author agent (preferred) ─► writes ce-spec.md + tasks.json ─► returns SpecResult
    ② [GATE] artifacts on disk? parked?  ──► skip + block dependents, or continue
    ③ spec-impl agent (spec files are its ONLY input; preferred) ─► code + tests + verification.md ─► returns ImplementResult
    ④ [GATE] verification.md on disk? criteria met?  ──► fail → DIAGNOSE (mode on) → targeted-retry / park / circuit-break
    ⑤ review agent (independent — did NOT write the code) ───► code-review.md ───► returns ReviewResult
    ⑥ [GATE] findings recorded; (blocking-on-high) high-sev → DIAGNOSE (reproducible) → targeted-retry / park, else continue
    ⑦ orchestrator merges decisions → ledger; marks done; updates live status
  then: integration agent (verify over the whole built app)
  │   returns a structured run summary
  ▼
Stage 3 — end-review (THIS skill, interactive)
  decisions ledger · parked features · manual:judgment verdicts · verification · sign-off
```

*DIAGNOSE* = the **Diagnose Gate** (Stage-0 opt-in, **off by default**; on a failed verification or review gate it root-causes the failure via `debug` before the orchestrator retries or parks — load `${CLAUDE_SKILL_DIR}/gate-diagnose.md` when diagnose mode is on).

Two agents per feature; the **orchestrator enforces spec→implement as an external
boundary** — the implement agent's only spec input is the files on disk, so it
*structurally cannot* collapse spec into implementation. On the Claude Code plugin
surface, the preferred leaves are `spec-author` for the per-feature spec pass and
`spec-impl` for implementation. If named plugin agents are unavailable, spawn
generic Task workers with the same role contracts and skill invocations; if Task
  itself is unavailable, use the Substrate Fallback. This is why the spawn model is
more robust than a single self-policing context.

## How it preserves the toolset's principle

Engineering decisions resolve autonomously (recorded); product / destructive / architectural / boundary decisions park (never silently guessed); the human reviews **once, after** — at the **end-review**, plus any mid-run **circuit-breaker** halt.

## Runtime Inputs

- **Plan slug (required):** which plan to build. If absent, read `docs/plans/plans.json` and ask.
- **Feature range (optional):** e.g. `01..05` — autopilot the early features, hand-drive the rest. Default: the whole plan.
- **Build preset (Stage 0):** one consented kickoff choice — **default-safe** [default] / **thorough** / **fast-floor** — that sets the challenger / review / diagnose / enrich-parks / parallelism knobs in a single `Gate 1` gate, any knob overridable in the same round. Sets **gate/verbosity knobs only, never model tier**; recorded in the ledger and surfaced at the end-review (fast-floor's dropped judgment layers as accepted degradations).
- **Bounds (Stage 0):** feature cap · token/compute budget · verification-retry cap (≈3) · consecutive-park cap · diagnose mode (off [default] / on) · parallelism (off [default] / worktree; also accepted as `--parallel worktree`).
- **`--resume` (optional):** resume a circuit-broken or interrupted run from its persisted state (see *Resume*) — the state file is a cache; disk is the source of truth, and every "terminal" feature is re-validated against disk on resume.

## Preconditions

- The plan exists with `plan.json` and per-feature files.
- Build / test / lint commands are discoverable (from `shared-context.md`).
- The repo VC policy is readable (`docs/plans/vc-policy.md`). What auto-build will and won't do with git is governed by **Execution Contract item 8** and the Stage 0 **Checkpoint Mode** (in `${CLAUDE_SKILL_DIR}/stage-0-kickoff.md`) — not redefined here. *(An optional plugin hook — `hooks/git-guard.py` — backstops these git rules at the tool layer in the Claude Code deployment; see `hooks/README.md`. Prose remains the enforcement on the Managed-Agent path.)*
- Capability dependencies (browser MCP, container runtime, build/test/lint, runnable app) are triaged at the Stage 0 **capability preflight**, not assumed.

## Execution Contract

1. **Supervised autonomy.** No routine questions during the pipeline; one mandatory end-review after. "Done" requires human sign-off.
2. **Decision Classification governs every judgment call** (below). Foundational unknowns are resolved up front (Stage 0), not mid-run.
3. **The orchestrator enforces the gates as external checks** — spec-artifact gate before implement, verification-artifact gate before done, (when challenger mode ≠ off) the **challenge gate** before implement, and (when review mode ≠ off) the **review gate** after verification. Objective, not self-policed. These disciplines are **substrate-independent** — they run whether features are spawned *or* executed in-context (see *Substrate Fallback*).
4. **Verification is never skipped.** Every feature is tested + its acceptance criteria checked; integration verify runs at the end. Manual ACs split by kind: `manual:harness-gap` browser-verified by the implement agent against an ephemeral server; `manual:judgment` deferred to the end-review. **A second axis cuts across this kind-split — functional vs taste:** a user-facing surface defect that is *functional* (overlap, clipping, off-screen, illegible density, an occluded primary affordance) is a `surface_findings` park (step 5½), **not** deferred taste; only a *readable-but-unpolished* surface stays `manual:judgment` taste for the end-review. The orchestrator owns each `verification.md`.
5. **Record every non-routine decision** in the run ledger (merged from agent returns).
6. **Spec-before-implement, in ship order.** Never implement before `ce-spec.md` + `tasks.json` exist — structurally guaranteed by the two-agent boundary. Never build a feature before its hard dependencies (including cross-plan qualified deps).
7. **Circuit-breaker bounds the run** (below).
8. **Never commit to the human's branch, push, open PRs, merge, or deploy.** The human owns what enters shared history. The one exception: in **Checkpoint Mode** (Stage 0) the orchestrator may make per-feature commits to an *isolated* `auto-build/<slug>/<date>` branch — an audit/rollback trail, never the human's branch, never pushed. Output: `docs/plans/<slug>/ce-auto-build/<date>-run.md`.

## Decision Classification — the heart

Every judgment call a spawned agent would surface is classified and given a disposition:

| Class | Examples | Disposition |
|---|---|---|
| **Engineering default** | validation, follow existing patterns, error handling, test structure, naming, a library already in the stack | **AUTO** — resolve, record, continue |
| **Product / business (reversible)** | a default easy to change later (soft-delete vs hard, default page size) | **ASSUME & FLAG** — proceed on a labeled assumption, record loudly |
| **Product / business (blocking)** | auth provider, retry-vs-manual, source-of-truth | **PARK** |
| **Destructive / irreversible** | migrations, data deletes, schema changes | **PARK** — never auto-run, never assume |
| **Architecturally significant** | ADR-worthy, cross-feature structural | **PARK** |
| **Boundary conflict** | spec-vs-reality needing scope change | **PARK** |

A spawned agent returns `status:"parked"` (with a reason) rather than guessing a PARK-class decision. **Foundational** unknowns (cross-cutting + architectural — LLM provider, target cloud) are resolved up front at the Stage 0 sweep, before any agent spawns; only a foundational decision missed by the sweep and surfacing mid-run trips the circuit-breaker.

## The Decision Ledger

The orchestrator merges `decisions` from every `SpecResult` / `ImplementResult` into the run report. Each entry: feature · point · disposition (auto/assumed/parked) · class · confidence · what was decided · rationale · reversible · where. This is what makes the end-review tractable — the human reviews decisions, loudest-first.

## Human-in-the-Loop — inverted

Two material bookends, autonomous in between: **Stage 0** (build preset + foundational sweep + capability preflight + policies — the last interaction until the end-review or a circuit-breaker) and **Stage 3** (the end-review). In the pipeline between them, spawned agents **never prompt the human — they park instead** (Spawn Contract).

---

## How to Run This Workflow

Execute the stages in order. Load each stage file when you reach it — not before. Each opens with a **Next:** header naming the file to load after it.

| Stages | Load this file | Purpose |
|---|---|---|
| 0 | `${CLAUDE_SKILL_DIR}/stage-0-kickoff.md` | Kickoff — foundational-unknown sweep, capability preflight, bounds, clean-tree baseline, destructive-op policy, Checkpoint Mode |
| 1+2 | `${CLAUDE_SKILL_DIR}/stage-1-2-pipeline.md` | The per-feature spawn loop — Spawn Contract, on-disk gates, Challenger, Enrich-Parks, Review Gate, Diagnose Gate, Substrate Fallback, integration verify, Budget Metering |
| 3 | `${CLAUDE_SKILL_DIR}/stage-3-endreview.md` | End-review — triage block, the seven review buckets, run report, closing |

To begin: load `${CLAUDE_SKILL_DIR}/stage-0-kickoff.md` and start Stage 0.

---

## Substrate & Named Agent Selection

Run-level rules — they govern every spawn in the Stage 1+2 pipeline.

**Substrate — confirm and record at run start.** The spawn loop requires the **`Task`** tool; record which substrate is actually in force on the run report's `Substrate:` line: **spawning orchestrator with plugin agents** (`Task` is available and named `spec-author` / `spec-impl` workers are available — the preferred Claude Code plugin mode), **spawning orchestrator with generic Task workers** (`Task` is available, but named workers are not selectable — still preserves spec↔implement isolation), or **in-context (spec/implement isolation relaxed)** (the *Substrate Fallback*, in `${CLAUDE_SKILL_DIR}/stage-1-2-pipeline.md`). The fallback degrades *loudly*, never silently. *(Deployment note: in Claude Code the `Task` tool must be listed in the skill's `allowed-tools`; the Claude Managed Agent deployment instead spawns via `callable_agents` in the cookbook `agent.yaml` — a different substrate enforcing the same contract.)*

### Named Agent Selection

When spawning through `Task` on the Claude Code plugin surface:

- Use `spec-author` for the per-feature specification pass. It must run only the
  existing-plan spec path here — auto-build must not let it re-plan or
  widen scope.
- Use `spec-impl` for the implementation pass. Its only spec input is the
  already-written `ce-spec.md` and `tasks.json` on disk.
- If a named agent cannot be selected, spawn a generic Task worker whose prompt
  explicitly carries the same role, constraints, Spawn Contract, and required
  skill invocation (`spec` for spec, `implement` for implement).
- Record `Worker selection: plugin agents | generic Task workers | in-context` in
  the run report. Generic Task workers are an operational fallback, not a license
  to skip any artifact or gate.

## Resume

A circuit-broken or interrupted run is resumable. The state file `docs/plans/<slug>/ce-auto-build/<date>-state.json` is **schema-versioned and owned by `run-state.py`** — created by `init` (Stage 0 step 9) and rewritten atomically by every `advance` / `park` / `retry` call, so it persists **after each gate** without a hand-written JSON edit. Its script-owned core is `schema_version`, `bounds {budget, retry_cap, park_cap, spawn_caps}`, `counters {consecutive_parks, budget_spent}`, `retry_counts`, and per-feature `{status, last_completed_gate, park_class}`. The resume caches ride alongside (preserved across `run-state.py`'s read-modify-write): `review_summary: { blocking_high, high_confirmed, high_suspected }` mirrors the feature's `review-summary.json` (on resume the on-disk `review-summary.json` wins, and its absence forces a re-review, per *disk wins* below), and `last_diagnosis: { dx_id, class }` is set **only** when the feature is at the diagnose routing state, so resume re-enters the re-implement step from the persisted routing `class`, never by re-parsing the cumulative `diagnosis.md` (which appends each `DX-N`, so a regex over it could read a stale prior entry). `/ce-auto-build <slug> --resume` reloads it (never re-`init`s) and continues.

**The state file is a convenience cache, not the authority — disk wins.** On resume, re-validate every feature the cache calls *terminal* (`done` / `parked` / `failed`) against disk with the **same on-disk checks the gates use** (`test -f ce-spec.md && tasks.json all-done && verification.md` — legacy `spec.md` accepted — exactly verify's *derive state, don't trust claims*). If the cache and disk disagree, **disk wins** and the feature re-enters the pipeline. Resume re-enters at the **first non-terminal feature in ship order**, re-threads the settled foundational decisions + ledger, and still ends in the mandatory **Stage 3 end-review**. A missing or unreadable cache is not an error — fall back to a fresh run that derives all state from disk.

## Worktree Parallelism (opt-in, default OFF) — *on-demand module*

By default auto-build is sequential — the safe mode. When the Stage 0 **parallelism** bound is `worktree` *and* the capability preflight confirms support, a group of **provably-independent** features (no dep relation + disjoint MODIFY reach) may run concurrently, each in its own git worktree, merged back by the orchestrator (which **never** auto-resolves a conflict) with the single integration `verify` pass as the backstop. **Load `${CLAUDE_SKILL_DIR}/gate-worktree.md`** for the independence test, ADR-propagation handling, merge policy, and capability gating.

## Circuit-Breaker

**The verdict IS `run-state.py breaker-check`'s exit code, not a prose re-derivation.** After each feature the orchestrator calls `breaker-check` (pipeline step 7a): **exit 0 = continue**, **exit 1 = circuit-break** (the JSON reason names the tripped run-level bound), **exit 2 = could-not-evaluate** (unreadable state — halt, recorded, never continue blind). The prose only *interprets* the reason; the script owns the count. `breaker-check` covers the two run-level bounds unambiguous from state — **consecutive parks reach the cap · the budget is exhausted**. The **per-feature retry cap** is `run-state.py retry`'s own exit-1 signal (a feature that fails verification beyond the cap), disposed at the failing gate (steps 3/5/6), not by `breaker-check`. The remaining halt conditions stay orchestrator judgment on top of the exit code: a hard dependency can't be resolved · a required capability is lost mid-run · a foundational decision surfaces mid-run (invalidates the foundation other features assumed — halt, don't park one feature). With diagnose mode on, a `spec-gap` / `structural` / `not-a-code-defect` diagnosis parks the feature (toward the consecutive-park cap) instead of consuming retries, and a blocking-review `bug` that exhausts the cap parks rather than halting the run. On any break the skill runs the end-review on the completed/parked/failed split.

## Escalation

Auto-build escalates by parking, halting, or routing to the owning skill; it never
answers product/security/scope authority itself. Boundary conflicts go to `/ce-plan`,
Spec Conflicts to `/ce-spec`, implementation failures to `/ce-implement` or
`/ce-debug`, behavior gaps to `/ce-verify`, code-quality findings to `/ce-review`,
and unwalked browser experience to `/ce-ux-audit` (which walks a plan's traced journeys or, plan-free, adversarially probes the running app).

## Honest Limitations

- **Sequential by default; opt-in parallelism is bounded — and in practice, usually still sequential.** The default mode runs features one at a time — the win is context-isolation, observability, and structural gates, not speed. The opt-in *Worktree Parallelism* mode runs provably-independent features concurrently (disjoint MODIFY reach + no dep relation, capability-gated), trading the simple serial ADR-propagation guarantee for reconciliation at group boundaries + an integration verify, and falling back to sequential whenever isolation or a clean merge can't be guaranteed. **Be clear about how often it actually parallelizes here:** MODIFY reach is derived from `specs/<id>/tasks.json` `files[]` (or an explicit plan.json reach key), and in this mode the spec agent runs *inside* the group — so at grouping time no spec exists, reach is underivable, and every feature is its own group. Auto-build therefore runs sequentially unless a plan carries explicit reach keys. That is the conservative contract, not a defect: a plan-time guess at which files a feature will touch is not proof. `worktree-merge.py`'s conflict-abort remains the mechanical backstop regardless.
- **Input-threading is the orchestrator's burden.** Each spec/implement subagent's prompt carries the dependency interfaces, foundational decisions, ledger, and **the accepted ADRs (read fresh from `docs/adr/`)** — the agent has a fresh context, and the ADR set grows during the run, so later features must read it fresh to honor earlier ones. Files carry most of it; the orchestrator passes pointers.
- **Supervised, not fire-and-forget.** "Done" requires the end-review sign-off.
- **Cross-feature consistency** rests on agents reading existing code + shared-context; `verify`'s drift checks are the backstop.
- **Spec self-classifications are surfaced, not mechanically gated.** The highest-cost spec calls with no on-disk check — SHARED-shape `additive`-vs-`breaking` (§3.5), `manual:judgment` tag-honesty, reversible-vs-blocking — are now *returned as discrete decisions*, interrogated by the Challenge gate (it targets "a park-class decision dressed as engineering"), and rendered as isolated evidence-first attestations at the end-review. This **raises the floor, not the ceiling**: the Challenger shares the model's blind spots, so a *latent* breaking change (no consumer test exercises it, the consumer set was mis-enumerated) can still be self-called additive and reach the human only at the end-review — better surfaced than before, not proven safe. A mechanical gate stays impossible (un-lintable from markdown); the discipline is detection-by-surfacing, not detection-by-proof.
- **`manual:harness-gap` verdicts get a second renderer, not a human one.** The implement subagent self-certifies them in-loop; the integration `verify` re-drives them independently (a fresh agent that did not write the code). That catches a false Pass the *author* missed, not one the *model* shares across both passes — the same blind-spot limit as the review gate. Only `manual:judgment` verdicts are rendered by the human (at the end-review).
- **End-review correction is dependent-aware but coarse (a conservative superset).** An overridden/reverted decision re-spawns the feature *and* its downstream dependents — never the feature alone — but the orchestrator broadcasts the ledger to all later features rather than recording which one read a given entry, so it re-spawns **every later feature in ship order** that could have consumed it (over-approximate, never under). That superset is derivable from ship order, so it survives `--resume` with no persisted consumer map; the cost is re-spawning some features that did not actually depend on the call. Cross-feature consistency reached through unlogged codebase reads (not the ledger) is outside even this; `verify`'s drift checks are the backstop there.
- **The clean-tree gate is consent, not enforcement.** Stage 0 checks the working tree and, when dirty, takes a consented baseline (stash / commit / proceed-dirty-recorded / abort) and baselines the integrity gates against the captured state — but a human who waves through "proceed dirty" still owns the commingled-diff risk. The gate makes it loud and pins the baseline; it does not prevent it.
- **Challenger raises the floor, not the ceiling.** It catches shallow defaults and over-build but shares the model's blind spots (can't catch shared error), and it **never answers** park-class decisions (that would fabricate the owner's knowledge). Bounded by ≤ 2 rounds + the Stage 0 mode.
- **Review gate raises the floor, not the ceiling.** The independent code review (`review`) catches the author's blind spots but shares the model's — it cannot catch shared error, and it is static, not a pentest (`/ce-probe-sec` owns runtime). High-severity security / correctness findings block; the rest inform the end-review.
- **Diagnose gate raises the floor, not the ceiling (and is off by default).** When diagnose mode is on, a failed verification / review gate is root-caused (`debug`) before the orchestrator retries or parks — a blind retry becomes targeted, and spec / structural / unreproducible causes park early instead of burning the retry cap (so the built/parked/failed split differs from an off run by design). It shares the model's blind spots (cannot catch shared error); a mis-diagnosis surfaces as the next failure or at the end-review, a `suspected` cause is flagged not proven, and bisection is skipped under autonomy. Reproducible failures only — a non-reproducible blocking review finding keeps the direct re-implement path. Bounded by the retry cap + the Stage 0 mode.
- **Capability-bounded.** Triaged at the preflight — abort / degrade-with-consent / note; never silently lowered.
- **Budget is an estimate, not a meter.** The token/compute bound is enforced on a `chars/4`-class estimate (no billing API) — a guardrail that trips the circuit-breaker, not an accountant — and it never trades a feature's verification or review for tokens.
- **Resume is disk-validated, not cache-trusted.** `--resume` re-derives every "terminal" feature's state from disk; the persisted `state.json` — now **schema-versioned and owned by `run-state.py`** (its shape is script-defined, no longer loosely specified prose) — is a convenience cache that disk overrides on any disagreement, so resume can never skip work disk wouldn't already justify.
- **The status board is a per-terminal-state snapshot, not live.** `STATUS.md` is regenerated only as each feature reaches done/parked/failed (step 7) — it is **stale mid-feature**, after interactive `/ce-implement` · `/ce-review` · `/ce-verify` outside auto-build, and after a circuit-break (frozen at the last terminal feature). It is a projection, never a gate; regenerate it on demand with `status-board.py`. Its parked/failed rows come from the `state.json` cache (disk wins for every other state), and a feature with an unsafe id or an unreadable review file is shown with a degraded status + a Note, never silently.
- **Checkpoint commits are not the human's history.** (Mechanics: **Execution Contract item 8** + Stage 0 **Checkpoint Mode**.) In `none` mode there are no commit boundaries: the whole run lands as one uncommitted working tree.
- **Foundational sweep is only as complete as the plan.** A fork the planner never surfaced appears mid-run as a circuit-breaker.
- **Interface foundations raise the floor, not the ceiling.** Resolving a surface's conventions up front and threading a shared contract to every feature — e.g. design tokens + primitives (`browser`) — buys *consistency and conformance* (and, for UI, contrast + spacing discipline), enforced by the foundation's conformance checker. On top of that, the in-loop **Surface Critique** pass surfaces *functional* surface defects (occluded affordance, clipping, illegible density, broken hierarchy, a surface failing its stated goal) as evidence-bound `surface_findings` the orchestrator can park on (step 5½) — the model can now *critique* a rendered view against its contract, not merely defer it. But critique is **findings, not proof**: it shares the model's visual blind spots, can miss or invent a defect, renders no verdict, and raises the floor not the ceiling. Genuine aesthetic preference (palette, brand feel, delight) stays *readable-but-unpolished* taste — a `manual:judgment` verdict, the human's call at the end-review.
- **More machinery** than a single-context run: per-feature subagent spawns + the orchestrator's gate-and-merge logic. Worth it for isolation + structural gates — and it stays a Markdown skill, not a separate runtime.
