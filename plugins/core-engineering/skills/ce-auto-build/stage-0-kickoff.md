# Auto Build — Stage 0: Kickoff

Stage file for the `ce-auto-build` skill. The orchestrator is `SKILL.md` — read it first for the Execution Contract, Decision Classification, and the Substrate & Named Agent Selection rules. Load this file when you begin Stage 0.

**Next:** when Stage 0's *Proceed* is given, load `${CLAUDE_SKILL_DIR}/stage-1-2-pipeline.md`.

---

## Stage 0 — Kickoff (interactive, in this skill)

Run **before** spawning the pipeline, while the human is present. **Each interactive prompt below carries an `HITL Gate Standard R5` locator — `Gate N of M — <name>` — where M counts the gates that *actually fire this run* (the **build-preset gate always fires — it is `Gate 1`**, the foundational sweep only when one is found, the clean-tree prompt only when the tree is dirty, the capability prompt only on a gap, plus the kickoff scope confirm and the Stage-3 end-review); compute M, never hardcode it.**

1. Resolve the plan via `docs/plans/plans.json`; load `plan.json` (ship order, deps, `relates_to`), `shared-context.md`, the VC policy.

   **Plan-lint preflight (before any spawn).** A structurally broken plan must park the run *at kickoff*, not after spec-agent budget is already spent. Lint the resolved plan directory — the same structural-integrity gate `/ce-plan` runs at write time and `/ce-plan-audit` runs as its hard-lint floor:

   ```bash
   python3 "${CLAUDE_SKILL_DIR}/scripts/plan-lint.py" docs/plans/<slug> --json
   ```

   Dispose by exit code: **exit 0** → the H1–H8 structural invariants hold, proceed. **exit 1** → **park the run at kickoff** — surface each hard failure and route the human back to `/ce-plan` (a broken DAG, backward dependency, or referential break is a planning defect, not something a build should paper over); do **not** spawn. **exit 2** → the lint could not run: a multi-feature plan falls back to the manual structural checks **loudly** and records the degradation in the ledger; a single-feature minimal plan (no `plan.json` to lint) records `N/A — single-feature minimal plan` and proceeds.
2. Determine scope: whole plan or the given range.
3. **Build preset & bounds.** Collapse the five judgment/verbosity knobs into **one consented choice**, then set the numeric caps.

   **3a — Build preset (`Gate 1 of M — Build Preset`).** This is the run's first interactive gate and it **always fires**. Render it as an `AskUserQuestion` whose **options each carry their consequence in the option text** (HITL R1 — decidable in the dialog), preceded by the locator (HITL R5). A preset sets **gate/verbosity knobs only — never model tier** (any per-subagent model hint stays a *separate* consented Stage-0 choice; the `model-policy.json` ce-auto-build note binds this — a preset must never carry a `model:`/`effort:` selection).

   | Preset | challenger | review | diagnose | enrich-parks | parallelism |
   |---|---|---|---|---|---|
   | **default-safe** *(default)* | material-only | advisory | off | off | off |
   | **thorough** | thorough | blocking-on-high | on | on | off |
   | **fast-floor** | off | off | off | off | off |

   Label each option by its **consequence** (R1):
   - **default-safe** — today's defaults: the Challenger catches the highest-cost spec calls (material-only), the review informs but never blocks (advisory), no diagnose/enrich overhead. The lowest-cost *supervised* profile.
   - **fast-floor** — cheapest: the judgment layers (challenger / review / diagnose) are **off**, but the **external integrity gates — `spec-lint`, `test-guard`, `dep-guard` — still run and still block**. You trade the judgment layers for speed; each dropped layer is named at the Stage-3 end-review as an **accepted degradation** (never a silent one).
   - **thorough** — **highest token spend; strongest unattended bar**: high-severity review findings block (blocking-on-high), failed verification/review gates are root-caused before retry/park (diagnose on), and architectural/multi-option parks arrive decision-ready (enrich-parks on).

   *Recommendation: **default-safe** — supervised autonomy at the lowest safe cost. Choose **thorough** for an unattended, high-stakes batch; **fast-floor** only when the external integrity gates alone are an acceptable bar for this run.*

   **3b — Per-knob override (offered in the same round).** A preset is a starting point, not a lock. After the preset choice, offer to **override any single knob** — its value moves off the preset default, everything else stays. If the human opts to override, the knob questions follow as a **stated follow-up split** (it exceeds one `AskUserQuestion`'s ≤4-question cap — a named split, never a silent cap; HITL R5). The knob domains, each identical to the preset columns above:
   - **challenger mode** (off / material-only / thorough — see *Challenger*; tied to the budget)
   - **review mode** (off / advisory / blocking-on-high — see *Review Gate*; tied to the budget)
   - **diagnose mode** (off / on — `${CLAUDE_SKILL_DIR}/gate-diagnose.md`; on a failed verification/review gate it root-causes before retry/park; tied to the budget)
   - **enrich-parks mode** (off / on — see *Enrich-Parks*; on an architectural / multi-option PARK it drafts a `/ce-decide` scored package for the end-review; never resolves the park; tied to the budget)
   - **parallelism** (off / worktree — `${CLAUDE_SKILL_DIR}/gate-worktree.md`; capability-gated, provably-independent features only). **No preset auto-enables worktree parallelism** — it stays `off` until explicitly overridden here *and* the capability preflight confirms support.
   - If parallelism is `worktree`, load `${CLAUDE_SKILL_DIR}/gate-worktree.md` and run:

     ```bash
     python3 "${CLAUDE_SKILL_DIR}/scripts/worktree-preflight.py" --root . --plan "docs/plans/<slug>/plan.json" --json
     ```

     Treat `status:"blocked"` as a sequential fallback or abort (human choice);
     treat `status:"degraded"` as sequential fallback unless the degradation is
     explicitly accepted. Use only the returned `parallel_groups`; never invent a
     group from a hard-dependency antichain alone.

     At kickoff this proves **capability**, not grouping: no feature has a spec yet,
     so MODIFY reach is underivable (`reach_sources` reads `none` for every feature),
     every group is a singleton, and `status` is `degraded` for that reason alone.
     Expected. Grouping only becomes derivable once `specs/<id>/tasks.json` exists.

   **Record the chosen `preset` and every per-knob override in the run ledger** (they ride the run report's header, so the Stage-3 end-review shows which profile ran). For **fast-floor** — or any override that turns a judgment layer *off* — record each dropped layer (challenger / review / diagnose) as an **accepted degradation** via the same ledger channel Stage 0.2 uses, so the end-review names it in the Degradations bucket rather than letting it pass silently.

   **3c — Caps (set independently of the preset).** feature cap · token/compute budget · verification-retry cap (≈3) · consecutive-park cap. These numeric bounds are **orthogonal to the preset** — accept the defaults or set them here.
4. **Foundational-Unknown sweep** (0.1) — resolve cross-cutting, architecture-shaping unknowns now.
5. **Capability preflight** (0.2) — detect capabilities, classify gaps, set the degradation policy.
6. **Working-tree baseline (clean-tree gate).** The per-feature subagent has no `AskUserQuestion` (Spawn Contract), so the working-tree acknowledgement `implement` Stage 0 makes interactively is the *orchestrator's* to make here, once, while the human is present. Check the tree:
   - **Clean** → record the run-start ref as the **integrity baseline** the step-5 `test-guard` / `dep-guard` gates diff against.
   - **Dirty** → surface it as **its own `AskUserQuestion`** (HITL R3 — isolate the material call: distinct from and *prior to* the step-9 scope confirm, never bundled into it), rendering the cost (HITL R2): uncommitted edits land inside every feature's measured diff, so a pre-existing rogue dependency could be attributed to a generated feature and `test-guard`'s cross-task diff would compare against a polluted base; in `none` Checkpoint Mode the run lands as one tree where generated and pre-existing edits are indistinguishable. Offer: **stash / commit first** (recommended — a clean baseline) · **proceed dirty** (a consented, ledger-recorded *degradation*; the orchestrator snapshots the current tree state and baselines the gates against *it*, not a moving HEAD — and in `isolated-branch` mode commits that pre-existing state as an `auto-build(baseline): pre-existing working-tree state` commit at branch creation, so every feature *including the first* diffs a clean committed parent) · **abort**. **Never proceed over a dirty tree silently.**
7. Destructive-op policy: **park by default**; the human may pre-authorize a class. The same pre-authorization shape covers **Rule-of-Two exceptions**: a feature that needs real secret access or an external write (deploy smoke test, third-party API call) is named *here* and recorded in the ledger — otherwise the subagent that hits it parks (see *Spawn Contract — Rule of Two*).
8. **Checkpoint Mode** (version control): choose **`isolated-branch`** — the orchestrator creates `auto-build/<slug>/<date>` from the current HEAD and commits each feature after its verification-artifact gate passes (a per-feature audit + rollback trail) — or **`none`** (leave all changes uncommitted in the working tree). Either way auto-build **never** commits to the human's branch, pushes, or opens PRs. Creating an isolated checkpoint branch is reversible and non-destructive (it never touches shared history), so by Decision Classification it may **auto-resolve to `isolated-branch`** unless the human or `vc-policy.md` opts out; surface the choice in the end-review.
9. Assemble the inputs each spawned subagent needs: `{ plan_slug, features:[{id,file,hard_deps}] in ship order, foundational_decisions, bounds }`. Confirm the run scope. *Proceed / Abort* — then **initialize the run state** and run the pipeline.

   On *Proceed*, create the run's state file — `run-state.py` is the deterministic owner of every counter, ledger append, metrics line, and circuit-breaker verdict the pipeline touches (it replaces the state prose the orchestrator used to hand-write; the orchestrator is the caller, the script owns the writes):

   ```bash
   python3 "${CLAUDE_SKILL_DIR}/scripts/run-state.py" init \
     --plan-dir "docs/plans/<slug>" \
     --budget <token/compute budget from 3c, or omit for no bound> \
     --retry-cap <verification-retry cap from 3c (≈3)> \
     --park-cap <consecutive-park cap from 3c>
   ```

   This writes `docs/plans/<slug>/ce-auto-build/<date>-state.json` (date defaults to today UTC — the same run date the report uses) with the 3c bounds and zeroed counters. Dispose by exit code: **0** = created, proceed; **2** = a run for this date already exists — do **not** re-init, resume it (`/ce-auto-build <slug> --resume`, see *Resume* in `SKILL.md`; disk wins). A **`--resume`** run never re-inits: it reloads the existing state file.

### 0.1 Foundational-Unknown Sweep

Some Open-Unknowns are **foundational** — they shape architecture, cost, security, and delivery, and many features rest on them (LLM provider, target cloud, framework, deployment constraints). **Too important to assume and too cross-cutting to park mid-run.** Sweep every feature's `open_unknowns` and flag an unknown foundational only when it is **cross-cutting AND architecturally significant AND high blast radius**. Keep the bar tight — local unknowns stay autonomous in the pipeline.

Present the foundational set as one batched round (material). Each: **resolve now** · **consented assumption** (loud, never silent) · or **abort** (a foundation that can't be settled is a precondition). **Promote each resolution to an ADR + the ledger immediately**, then pass it into the pipeline `args` so every spec agent reads it as settled.

**Interface foundations are foundational for a plan that exposes a conventioned
surface.** A surface's interface contract — e.g. design tokens + UI primitives
(`browser`) — is cross-cutting (every feature on that surface), architecturally
significant (the token / contract structure), and high blast radius (changing it
later touches all of that surface). It is the most common foundational gap behind
functional-but-poor autonomous builds. For each **primary interface modality** in
the plan's trace with **no** settled foundation — no matching interface-foundation
Boundary-Owner (`design-system`; the family extends on demand), none detected in
the codebase profile, none provided — raise it in the sweep. Resolve the
**conventions** with the human now (a one-line brief — *"clean, professional SaaS;
light mode; primary #2563eb"* for `browser`), promote it to an ADR (the binding
contract every feature on that surface consumes — and ensure the foundation feature
delivers the conformance *checker*, not just the contract) + the ledger, and thread
it into the pipeline `args`. Then:

- **Plan owns the foundation feature** → this resolves its conventions unknown up
  front, so its spec builds to a chosen direction rather than guessing; the feature
  itself (early in ship order) produces the tokens/primitives or contract every
  later feature on that surface reads.
- **Plan owns none** (a legacy plan, or one that skipped the Interface Foundation
  Gate) → surface it as a foundational gap. **resolve-now** (recommend re-running
  `/ce-plan` to add the owner, or proceed on a consented direction the first feature on
  that surface realizes) · **consented assumption** · or **abort**.

Never let a plan build a surface feature-by-feature with no shared contract — that
is the silent-degradation failure this sweep exists to prevent.

**Security foundations are foundational the same way.** Read the plan's
`threat-model.md`. If it documents a security surface (trust boundaries, `sensitive`
data-classes, per-feature `TZ-NNN` obligations) but the plan assigned **no
security / secrets Boundary-Owner**, that is the security analog of a missing
interface foundation — cross-cutting (auth / secrets / validation span features),
architecturally significant, high blast radius — so raise it in the sweep:
**resolve-now** (recommend re-running `/ce-plan` to add the owner, or proceed on a
consented direction) · **consented assumption** (loud) · or **abort**. A
`## No Security Surface` threat-model needs nothing here. This keeps the per-feature
H5 gate from papering over an absent *foundation* — H5 enforces that each feature
*states* its security criteria; this ensures the cross-cutting security contract has
an owner at all.

### 0.2 Capability Preflight

Proceeding without a capability is a judgment call; silent degradation manufactures false confidence. Detect: build/test/lint (and that they run) · the app can start · browser MCP · container runtime · **a dependency-install proxy (Aikido Safe Chain or equivalent)** · any capability a feature declares. **Safe Chain present** → spawned agents prefix installs with it (registry existence/typo blocked at install time), and the subagent still returns each new dep for the ledger + the `dep-guard.py` re-check. **Absent** → the degraded tier: the agent's own `npm view` / `pip index` existence check + `dep-guard.py`'s offline detection/typo backstop, recorded as the degraded path (never silently assumed). Safe Chain is an install-time **CLI proxy**, not an MCP server — it does **not** belong in `.mcp.json`.

| Tier | Examples | Default |
|---|---|---|
| **Blocking** | no test runner · no build · app won't start | **Abort** |
| **Quality-degrading** | no browser MCP · no container · no linter | **Surface — human chooses** |
| **Cosmetic** | one optional scanner missing | Note and proceed |

Set the **degradation policy**: **best-effort** (proceed through quality-degrading gaps, record each) or **strict** (stop if any quality-degrading/blocking capability is missing). **Degradation is for *absent* capabilities only** — a capability that *is* present must be used to full effect; deferring it for convenience is not a permitted degradation. Record accepted degradations in the ledger.
