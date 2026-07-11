# Auto Build — Stage 1+2: The Pipeline

Stage file for the `ce-auto-build` skill (orchestrator: `SKILL.md`). Load this file when Stage 0 is complete. The **Substrate** confirmation and **Named Agent Selection** rules that govern every spawn below are run-level and live in `SKILL.md`.

**Next:** when the loop and the integration pass complete — or a circuit-breaker halts the run — load `${CLAUDE_SKILL_DIR}/stage-3-endreview.md`.

---

## Stage 1+2 — The Pipeline (autonomous, skill-driven)

Run the per-feature loop **in this skill**, spawning subagents via the **Task tool**, in ship order — **sequentially by default** (the safe mode). A feature group may run **concurrently** only under the opt-in *Worktree Parallelism* mode (Stage 0; `${CLAUDE_SKILL_DIR}/gate-worktree.md`): capability-gated and restricted to provably-independent features. Track progress with a task list — one task per feature, moved specced → **challenged** → implementing → verifying → **reviewed** → done / parked / failed (a failed verification or review gate may pass through **diagnosing** before a targeted retry or a park) — so the run shows live status. The task list's **durable counterpart is `docs/plans/<slug>/STATUS.md`** — a generated, never-hand-edited board regenerated per feature (step 7) by `status-board.py`, deriving each feature's status from the same on-disk checks the gates use (parked/failed overlaid from the run's `state.json` cache, labeled), so a supervisor can watch a file instead of a session.

### Spawn Contract (every subagent)

Every spawned subagent's prompt must carry these — they make autonomy structural, not prose-deep:

- **`AskUserQuestion` is unavailable this run.** Every gate the shared skill would ask resolves to a decision (per Decision Classification) or a **`park`** returned to the orchestrator — **never block.** Where the spawn supports tool restriction, spawn the subagent *without* the `AskUserQuestion` tool so it cannot hang.
- **No version control in the subagent.** Do not establish a VC policy, create branches, or commit (implement's Stage 0 would otherwise *ask* for a branching policy — suppress it). Leave the working tree for the **orchestrator**, which is the only actor that touches git (per **Checkpoint Mode**).
- **Rule of Two — never all three legs.** Hold at most two of **{untrusted input, secret access, external write}**. You already hold **untrusted-input** (you read repo content, package metadata, and tool output you did not author), so hold *at most one* of the other two — in practice **neither**:
  - **No external write** — no VC, push, PR, or deploy; network use confined to the verified package-registry fetches above.
  - **No secret access** — an auto-build run exports **no credentials** into the session environment.
  - A feature that genuinely needs a secret or an external write (a deploy smoke test, a third-party API call) is a **Stage-0 pre-authorized, ledger-recorded exception** — never a mid-run grant. Absent that pre-authorization, **park**.

  *Backstops (not your gate):* `hooks/git-guard.py` backstops the no-write leg and `hooks/env-guard.py` the no-secret file-read vectors (`/proc/…/environ`, out-of-workspace dotenv) on the Claude Code surface. The hook **cannot** stop env-var *expansion* (`echo $API_KEY`), so the empty environment is **contract, not mechanism** — and both hooks are **absent on the Managed-Agent surface** (prose + the operator's sandbox enforce there).
- **Produce the required artifacts in full** — spec → `ce-spec.md` + `tasks.json`; implement → `verification.md` (including the Try-It-Yourself runbook). Autonomy never drops an artifact, even for "just setup" features.
- **Leave the red-test snapshots on disk.** `implement` captures each task's red tests into `.test-guard/<id>/<task-id>/` and runs the per-task test-integrity gate for tight feedback, but the subagent **must not delete the snapshots** — the orchestrator re-runs `test-guard.py` over them as an *external* gate (step 5) and owns their cleanup. This re-check is **partial independence, not the full spec-artifact guarantee**: the implement agent did not write the spec, but it *does* write the snapshot — so the orchestrator catches a subagent that ran the gate and **misreported its result**, and post-hoc weakening between a real red capture and green, but **not** a subagent that captured a weak snapshot or authored the test weak from the start (that residual shares the model's blind spot — see implement *Honest Limitations*). It is still worth far more than a self-reported pass.
- **Verify every new dependency before install, and return it.** Before adding any new package, confirm it exists on the registry / is not suspiciously new / is not a typosquat (`npm view`, `pip index versions`, or the Safe Chain proxy if Stage-0.2 detected it) — **park** a dep that cannot be verified rather than installing it (offline → park, never install unverified). **Return each verified new dependency** (name@version, ecosystem) in the result's `decisions`, so the orchestrator appends it to the ledger and re-runs `dep-guard.py --declared <those names>` externally (step 5). A dep in the manifest the subagent did *not* return is the undeclared/slopsquat case the gate catches — the same partial-independence the test-guard re-check has (the agent did the network check; the orchestrator re-derives the detection).
- **Read ADRs fresh** from `docs/adr/`, indexed by the ledger in `shared-context.md` — so each subagent honors ADRs from the kickoff *and* earlier features this run (binding; an irreconcilable conflict → park).
- **Critique a rendered surface, and return the findings.** When the feature renders a user-facing surface, the implement subagent runs the **Surface Critique** inverse pass (implement Stage 2) on its ephemeral-server screenshot and **returns `surface_findings`** (each `{class: functional|taste, severity, evidence-tier, surface-kind: dom|canvas, contract-clause|unbound, evidence-ref}`) — the same return channel as `decisions`/verified-deps. A surface defect with no return channel dies as unread text; this is the channel the orchestrator dispositions (step 5½).

For each feature whose hard dependencies are built (and not yet done):

1. **Spawn the spec worker (`spec-author` preferred).** Prompt it to load
   `spec` **and, before Stage 0, to load and apply that skill's own
   `autonomous-mode.md` companion** (the auto-build overlay where spec's Decision
   Classification lives — it is loaded *only* under auto-build, so the spawn
   prompt must name it explicitly) and write `specs/<id>/ce-spec.md` (EARS
   criteria + test cases tagged `auto | manual:harness-gap | manual:judgment` +
   design) and `tasks.json`. It is acting as a per-feature spec author over an
   existing plan, not as a planner. **Pass it:**
   - the feature file and `shared-context.md`;
   - `docs/plans/<slug>/threat-model.md` — this feature's `TZ-NNN` security obligations. Its spec must emit a `[SECURITY: TZ-NNN]` criterion per assigned threat, or **park** an obligation it believes is genuinely N/A (a spawned agent cannot consent-exclude — that needs a human and a `/ce-plan` threat-model edit);
   - `docs/plans/<slug>/interaction-contract.md` — this feature's `IC-NNN` interaction obligations (behavioural-protocol invariants + architecture-determining NFRs). Its spec must emit a `[CONTRACT: IC-NNN]` criterion + ≥ 1 test case per assigned obligation, or **park** one it believes is genuinely N/A (same consent-exclude limit as the threat-model). **Unlike `TZ-NNN` there is no spec-lint check** for `IC-NNN` (a behavioural invariant / NFR is un-derivable from markdown), so the agent's *emit-or-park* surfacing is the only backstop;
   - the hard-dependency spec paths;
   - the settled foundational decisions — **including, for a feature exposing a foundationed surface (`browser` or another live surface), the interface-foundation ADR + artifact path: its spec must emit conformance criteria and build against the shared tokens/primitives or contract, never ad-hoc** (reading ADRs fresh is required by the Spawn Contract).

   **Promote new ADRs:** when the spec makes an architecturally-significant decision it can defend on engineering grounds (a cross-feature pattern, a data contract, a shared convention), **write it as a new ADR in `docs/adr/`** (record-don't-park) so later features honor it — **park** only architecturally-significant decisions that need the *owner's* knowledge. (Foundational ADRs are created at Stage 0; this is the per-feature stream.)

   Returns a structured result (status `specced | parked`, decisions — **including each SHARED-shape `additive`-vs-`breaking` call as a discrete material decision (§3.5), never folded into a bulk design line** — new ADRs / ledger entries).
2. **Challenge gate** — when challenger mode ≠ off, **required**: interrogate the draft's material decisions and **record verdicts in the run report's Challenges table before implement begins** (a feature with material decisions and no recorded challenge is *not ready for implement*). **Material decisions include every SHARED-shape `additive`-vs-`breaking` classification the spec returned (§3.5)** — interrogated here even when the agent called them additive, because that under-call is the highest-cost spec defect with no on-disk gate. Exits: revise (≤ 2 rounds) · escalate-park · accept-and-flag. Protocol and spawned/in-context handling: see *Challenger*. Skip only when mode is off, or there are genuinely no material engineering decisions (record "none").
3. **Spec-artifact gate (real, on disk).** Objective external checks — **not** the subagent's self-report:

   ```bash
   test -f specs/<id>/ce-spec.md && test -f specs/<id>/tasks.json     # artifacts exist
   python3 "${CLAUDE_SKILL_DIR}/scripts/spec-lint.py" specs/<id> --json   # referential integrity + H5; read h5_status
   ```
   `spec-lint` checks every `verifies` resolves to a real TC, every TC is tagged, and there is no orphan task/TC — **plus H5: every `TZ-NNN` the threat-model assigns this feature is covered by a `[SECURITY: TZ-NNN]` AC.** H5 auto-discovers the plan's `threat-model.md` at `specs/<id>/../../threat-model.md` (no flag needed), and the `--json` payload reports its disposition as **`h5_status`**: `ran` (threat-ids resolved, H5 executed), `na` (no threat-model and no `--threat-*` flag — a genuine skip, **never a false block**), or `disarmed` (a threat-model is present but this feature matched no `security_obligations` entry, or the block parse failed — the security gate could not arm). There is **no parallel lint for `IC-NNN`** interaction-contract obligations — a behavioural invariant / NFR is un-derivable from markdown (the deliberate divergence from H5) — so the spawned spec agent's *emit-or-park* surfacing (step 1) plus the end-review is their only backstop, never a hard gate.

   Dispose by exit code:
   | Result | Action |
   |---|---|
   | exit 0 (pass) with `h5_status: ran` or `na` | `run-state.py advance <id> specced`, then proceed to step 4 |
   | exit 0 (pass) but **`h5_status: disarmed`** | **`run-state.py park <id> --class spec-gap`, recorded as a degradation — never a silent H5-N/A.** The threat-model names this plan's threats but H5 could not check this feature against them; the owner fixes the `security_obligations` block (or passes `--threat-ids`/`--feature`) before the feature proceeds |
   | exit 1 (FAIL) or missing files | re-spawn the spec subagent to fix — record the attempt with `run-state.py retry <id>` (**exit 1 = retry cap reached → circuit-break**) |
   | exit 2 (could-not-run) | degrade to the artifact check alone, **record the degradation** (never a silent skip) |
   | advisory warnings | record, do not block |
   | subagent returned `parked` | `run-state.py park <id> --class <returned reason>`; skip + mark dependents blocked |
4. **Spawn the implementation worker (`spec-impl` preferred).** Its **only** spec
   input is the two files on disk — instruct it to **STOP if they are absent** (it
   cannot improvise a spec). Prompt it to load `implement` **and, before Stage 0,
   to load and apply that skill's own `autonomous-mode.md` companion** (the
   auto-build overlay — Decision Classification plus the snapshot / VC / dependency
   / surface-finding rules — loaded *only* under auto-build, so the spawn prompt
   must name it explicitly) and:
   - **honor the accepted ADRs the spec cites and any relevant in `docs/adr/`, read fresh from disk** (an irreconcilable ADR conflict is a `spec_conflict` → park);
   - test-first against `tasks.json`; **park on destructive ops**;
   - run the suite + acceptance criteria; browser-verify this feature's `manual:harness-gap` ACs against an **ephemeral** dev server (build → start → verify → stop); defer `manual:judgment` verdicts; **for a user-facing surface, run the Surface Critique inverse pass on the captured screenshot and return `surface_findings`** (Spawn Contract);
   - **write `specs/<id>/verification.md` as required output** (not gated on any Accept step), **including a Try-It-Yourself runbook section**.

   Returns a structured result (status, test summary, criteria, harness-gap verdicts, **`surface_findings`**, deferred judgments, degradations). When the worker returns, `run-state.py advance <id> implementing` (step 7 transition table) before the step-5 gate.
5. **Verification-artifact gate (real, on disk).** The orchestrator derives `implemented` from disk — the **same checks verify and Resume use** — never the subagent's self-report. Run in order:

   ```bash
   # 5a  Artifact floor — verification.md present AND every task done
   test -f specs/<id>/verification.md
   #     read tasks.json (jq/python3): FAIL if any task is todo/in-progress
   # 5a′ Test-integrity honor ledger — every done task with an auto test case left a
   #     PASS marker; MUST run BEFORE .test-guard/<id>/ is deleted (5b's cleanup)
   python3 "${CLAUDE_SKILL_DIR}/scripts/test-guard.py" --verify-passes --spec-dir specs/<id> --json
   # 5b  Test-integrity, per preserved red snapshot (within-task genie)
   python3 "${CLAUDE_SKILL_DIR}/scripts/test-guard.py" --snapshot .test-guard/<id>/<task-id>
   # 5c  Test-integrity, feature test diff (cross-task erosion)
   python3 "${CLAUDE_SKILL_DIR}/scripts/test-guard.py" --base <baseline> --feature <id>
   # 5d  Dependency-existence (slopsquatting defense)
   python3 "${CLAUDE_SKILL_DIR}/scripts/dep-guard.py" --base <baseline> --feature <id> --declared <returned dep names>
   # 5e  Scope Lock file boundary — no file touched outside this spec's tasks[].files
   python3 "${CLAUDE_SKILL_DIR}/scripts/implement-scope-guard.py" --spec-dir specs/<id> --base <baseline> --json
   ```
   - **5a′** audits the **honor ledger** the implement subagent's per-task `--snapshot` PASSes wrote (`.test-guard/<id>/passes.json` — a sibling of the task dirs that survives their deletion). It closes the gap where a task that reached done *without ever capturing a red snapshot* would be silently unguarded: a `done` task carrying an `auto` test case with no PASS marker is a **structural** test-integrity gap. It **must run before** the orchestrator deletes `.test-guard/<id>/`, and a FAIL **parks as `spec-gap` / `structural`** (never a `bug` retry — a code re-implement cannot manufacture the missing red capture), the same disposition as 5b/5c/5d.
   - **5b** runs over **each** red snapshot the subagent left on disk (Spawn Contract). The orchestrator deletes `.test-guard/<id>/` **only after** 5a′ and this re-check — it owns the lifecycle the subagent deferred.
   - **`<baseline>` (5c, 5d):** in `isolated-branch` mode, the previous checkpoint — current `HEAD` (the parent of this feature's *forthcoming* **pipeline** step-7 checkpoint), which for the **first** feature is the branch's baseline commit (a consented dirty tree is committed as that baseline at branch creation, per Stage 0 step 6 — so feature 01 diffs a clean committed parent, never the dirty tree as its own changes); else (`none` mode) the **run-start baseline** captured at Stage 0 step 6 (the clean run-start ref, or the consented dirty-tree snapshot — never a possibly-dirty live `HEAD`).
   - **5d** re-derives the feature's new direct dependencies and **fails on any the subagent did not declare/verify** (the network existence check was the subagent's job). The undeclared check is **ON by default**: if no deps were returned, pass `--declared` empty — *any* new manifest dep then fails (fail-safe; **never** `--detect-only`, which disables the gate). A typosquat-near-popular name is an **advisory** surfaced at the end-review.
   - **5e** enforces the **Scope Lock's file boundary**: it fails any file the feature touched that is outside the union of this spec's `tasks[].files` (the plan bookkeeping subtree, `.test-guard/`, and `docs/adr/` promotions are sanctioned). The implement subagent *did not write the spec* — so a stray file it touched is a scope widening the orchestrator catches on disk, the mechanical half of "the subagent cannot collapse spec into implementation." A **FAIL parks as `spec-gap`** (never a `bug` retry — re-implementing cannot un-widen the boundary; the fix is a `/ce-spec` edit that names the file or a genuine scope decision). A spec that declares **no `tasks[].files`** (legacy) yields an **advisory**, not a park — the boundary is un-knowable, so the gate degrades loudly rather than parking every feature. Uses the same `<baseline>` as 5c/5d.

   **Dispose by exit code (5a–5e share spec-lint's contract):**
   | Result | Action |
   |---|---|
   | all exit 0 | `run-state.py advance <id> verifying`, then proceed to step 6 |
   | **5a′ / 5b / 5c / 5d / 5e FAIL (exit 1)** | **`run-state.py park <id> --class spec-gap` (or `structural`)** — a test-design, honor-ledger, supply-chain, or scope-boundary defect, **not a code bug.** **Never** route to the Diagnose `bug` path or re-spawn implement: the code was never the problem; retrying burns the cap for nothing. |
   | **5a FAIL, diagnose OFF** (default) | re-spawn implement directly — `run-state.py retry <id>` (**exit 1 = retry cap reached → circuit-break**) |
   | **5a FAIL, diagnose ON** (`${CLAUDE_SKILL_DIR}/gate-diagnose.md`) | root-cause first; a `bug` re-spawns implement **with the diagnosis threaded in** — one targeted `run-state.py retry <id>` (exit 1 = cap → circuit-break); a `spec-gap` / `structural` / `not-a-code-defect` **`run-state.py park <id> --class <that class>`** instead of burning retries |
   | exit 2 (could-not-run) | degrade to the artifact check alone (recorded, never silent) |
   | advisory warnings | record, do not block |

   This gate enforces only the objective on-disk floor; whether the criteria are *substantively right* stays the human's call at the Stage 3 end-review and the review gate.

   **5½. Surface-readability disposition (from the subagent's `surface_findings`).** A returned-finding disposition, not an on-disk script gate — the **functional-vs-taste severity axis** the manual-AC split otherwise lacks (a non-readable surface is a *functional* defect, not deferred taste). Default posture: **park on a clause or cited evidence, never on a bare visual hunch.**
   | `surface_findings` entry | Action |
   |---|---|
   | **functional**, bound to a `must-not` / `must-be-legible` / `primary-affordance` clause, **or** citing a specific blocked use | **`run-state.py park <id> --class surface-defect`** (a `spec-gap`-class park — the criteria were too weak or the layout is broken; never a `bug` retry) so it cannot propagate to dependents |
   | **taste** (palette, brand feel) | recorded for the end-review taste bucket — **never blocks** |
   | **unbound** (a defect on a surface with no authored clause) | recorded **advisory** + suggested route (contract-gap → `/ce-spec`; real defect → re-spawn implement; noise → dismiss at end-review) — **never auto-upgraded to a park, never dropped** |
   | none returned / non-rendered feature | N/A — skip |
6. **Review gate (when review mode ≠ off; skip only when off).** Spawn an **independent review subagent** — `review` in autonomous mode over this feature's diff. Its inputs: the code on disk, the spec as contract (it did **not** write the code), and the **review calibration & memory** read-only — `docs/plans/review-policy.md` (skip-paths / nit caps / convergence) and `docs/plans/<slug>/review-learnings.md` (prior dismissals to suppress, record-with-note). It **records** suppressed matches under "Previously dismissed" but **appends no learnings mid-run** (the human `Dismiss` and its append happen only at the end-review, Stage 3 step 5). It runs the **Stage 1.5 adversarial verification pass** on every High finding (reproduce/refute → `confirmed | suspected`, an in-context second pass — not a nested spawn), returns findings (lens · severity · **confidence** · `file:line` · evidence · suggested escalation), and writes **both** `specs/<id>/code-review.md` (prose) and `specs/<id>/review-summary.json` (machine state, overwritten — schema in `review`).

   **Does it block? — by mode:**
   - **Advisory (default):** **nothing blocks** — every finding is recorded for the end-review, so the run is never gated on the model's own (fallible) high-severity calls. The verification pass still runs and tags confidence (it informs the end-review and `/ce-retro` — never shortcut to save budget).
   - **Blocking-on-high:** read one precomputed key — `jq -r .blocking_high specs/<id>/review-summary.json` (same on-disk read pattern as step 5) — and **block only on `confirmed`-high correctness/security (`blocking_high > 0`)**. A `suspected`-high is recorded for the end-review, never blocks, never burns a retry. A **missing / unreadable `review-summary.json` degrades like spec-lint exit 2** — fall back to the `code-review.md` prose, recorded as a degradation, never a silent skip.

   **Routing a blocking finding:**
   | Finding | diagnose OFF (default) | diagnose ON (`${CLAUDE_SKILL_DIR}/gate-diagnose.md`) |
   |---|---|---|
   | confirmed-high, **reproducible** | re-spawn implement to fix — `run-state.py retry <id>` | Diagnose Gate: a `bug` re-spawns with the diagnosis (`run-state.py retry <id>`); a `spec-gap` / `structural` → `run-state.py park <id> --class <that class>` |
   | confirmed-high, **non-reproducible** (static security / maintainability, no red test) | re-spawn implement to fix — `run-state.py retry <id>` | same — keeps the direct path; a debug `not-a-code-defect` never auto-parks it |
   | suspected-high · medium · low | recorded for the end-review, never blocks | same |

   A fix that needs a spec change is a `spec_conflict` → **`run-state.py park <id> --class spec-gap`**. **A `bug` re-implement whose `run-state.py retry <id>` returns exit 1 (the per-feature cap reached) parks the feature** for the end-review — here the cap-reached signal is disposed as a **park** (`run-state.py park <id> --class spec-gap`), **not** a circuit-break (the run continues; only the run-level `breaker-check` bounds halt it). (Challenge interrogates *decisions* before implement; review interrogates *code* after.) When the review gate passes (advisory: always; blocking-on-high: `blocking_high == 0`), `run-state.py advance <id> reviewed`, then step 7.
7. **Merge + advance.** Do **7a** (required — the run's state depends on it), then **7b** (best-effort — never blocks or fails the run).

   **State is owned by `run-state.py`, never hand-written.** Every state mutation in this loop — each ledger append, counter tick, status transition, and the circuit-breaker verdict — is a single atomic call to `${CLAUDE_SKILL_DIR}/scripts/run-state.py`, disposed by its exit code (the same 0/1/2 discipline steps 3 and 5 use for spec-lint / test-guard). The orchestrator is the caller; the script is the deterministic owner — it owns `state.json`, the provisional `<date>-ledger.jsonl`, and the `.metrics.jsonl` stream, writing each atomically as the relevant transition fires (a status move emits its metrics line; `ledger-append` writes the decision row), so `/ce-retro` inputs are trustworthy by construction. **Never hand-edit `state.json`, a counter, a ledger row, or a metrics line — issue the call.** Every call takes the run locator `--plan-dir "docs/plans/<slug>"` (it resolves the run's newest `<date>-state.json`).

   **The forward transitions (one `advance` per gate — this is where the *"persist after each gate"* in *Resume* happens):**

   | Transition (at) | Call |
   |---|---|
   | spec artifacts pass (step 3) | `run-state.py advance <id> specced --plan-dir "docs/plans/<slug>"` |
   | challenge accepted (step 2) | `run-state.py advance <id> challenged --plan-dir "docs/plans/<slug>"` |
   | implement worker returns (step 4) | `run-state.py advance <id> implementing --plan-dir "docs/plans/<slug>"` |
   | verification-artifact gate passes (step 5) | `run-state.py advance <id> verifying --plan-dir "docs/plans/<slug>"` |
   | review gate passes (step 6) | `run-state.py advance <id> reviewed --plan-dir "docs/plans/<slug>"` |
   | feature complete (7a) | `run-state.py advance <id> done --plan-dir "docs/plans/<slug>"` |

   Optional stages skip cleanly (challenger off → no `challenged`; review off → no `reviewed`): `advance` accepts any strictly-forward move and rejects only a *backward* one (exit 2 = illegal transition — a could-not-do-that to investigate, never a silent skip). A **park** at any gate is `run-state.py park <id> --class <spec-gap|structural|surface-defect|…>` (it bumps the consecutive-park counter and marks the feature terminal); a **retry** is `run-state.py retry <id>` (**exit 1 = the per-feature cap was reached → circuit-break**; the gate steps 3/5/6 dispose on this). Pass `--tokens <chars/4 estimate>` on any of these to accrue the transition's cost to the budget the breaker checks (see *Budget Metering*); `--detail "<string>"` overrides the emitted metrics detail (e.g. `"test-guard: <N weakened>"`).

   **7a — Required state updates (each a `run-state.py` call):**
   - **Ledger the decisions.** For each decision the subagent returned — including each SHARED-shape `additive`-vs-`breaking` call as a discrete row (§3.5), and each verified new dependency as `RPD-N | New dependency <name>@<ver> (<eco>) | verified: exists/age/no-typo | implement <plan>/<id> | (inline)` — append it to the run's machine ledger:

     ```bash
     python3 "${CLAUDE_SKILL_DIR}/scripts/run-state.py" ledger-append --plan-dir "docs/plans/<slug>" \
       --entry '{"id":"RPD-N","feature":"<id>","decision":"…","disposition":"auto|assumed","class":"…","rationale":"…","reversible":true}'
     ```

     `ledger-append` stamps every row `provisional (auto-build <date>)` automatically — the marker the Stage-3 end-review confirms/reverts. These appends are **provisional until the end-review confirms them**: later features in ship order read them fresh as settled (Spawn Contract), so a mis-worded or mis-routed entry propagates before the human sees it — surface every provisional append at the end-review, and a revert then re-spawns the conservative downstream superset (Stage 3 *dependent-aware correction* — every later feature in ship order, since the orchestrator broadcasts the ledger rather than recording which feature read which entry). The canonical cross-feature **Resolved Project Decisions** ledger in `shared-context.md` is still the spec subagents' append target; `ledger-append` owns the *run report's* provisional machine ledger.
   - Append a ship-ordered row to the run report's **Verification index** (link the `verification.md`) — a run-report file edit, not a state mutation.
   - **Tick this feature's box** in `feature-plan.md`'s Execution Checklist (interactive implement does this on Accept; the orchestrator owns it here) — a file edit, not a state mutation.
   - **Advance the feature to `done`** with `run-state.py advance <id> done --plan-dir "docs/plans/<slug>"` (from the transition table above), then update the live task list to match. `advance … done` sets `last_completed_gate`, **resets the consecutive-park counter** (a completed feature breaks a park streak), and emits the `stage-complete` metric.
   - **Checkpoint** (Checkpoint Mode = `isolated-branch` only): commit this feature's working-tree changes + its `specs/<id>/` artifacts to the `auto-build/<slug>/<date>` branch (`auto-build(<id>): <feature title>`) — only **after** the step-5 gate passed, so each checkpoint is a verified boundary; never the human's branch, never pushed. A `parked` / `failed` feature is **not** checkpointed.
   - **Check the circuit-breaker — the verdict IS the exit code:**

     ```bash
     python3 "${CLAUDE_SKILL_DIR}/scripts/run-state.py" breaker-check --plan-dir "docs/plans/<slug>"
     ```

     | Exit | Verdict | Action |
     |---|---|---|
     | 0 | `continue` | proceed to the next feature |
     | 1 | `circuit-break` | **halt** — the JSON reason names the tripped run-level bound (consecutive-park cap or budget). Load `${CLAUDE_SKILL_DIR}/stage-3-endreview.md` and run the end-review on the completed / parked / failed split (per *Circuit-Breaker* in `SKILL.md`) |
     | 2 | could-not-evaluate | the state file is unreadable — **record the degradation and stop**, never continue blind |

     `breaker-check` evaluates only the run-level bounds unambiguous from state (consecutive-park cap, budget). The **per-feature retry cap is `retry`'s own exit-1 signal** (steps 3/5/6), not re-derived here.

   **7b — Best-effort side-effects (a failure here is recorded under *Degradations* in the run report, never blocks):**
   - **Status board:** `python3 "${CLAUDE_SKILL_DIR}/scripts/status-board.py" docs/plans/<slug> --write` once this feature is terminal (done / parked / failed) — disk-derived status (parked/failed overlaid from `state.json`, labeled).
   - **Metrics are emitted by `run-state.py`, not appended by hand.** Each **status/park/retry** call (`advance` / `park` / `retry`) writes the matching `docs/plans/<slug>/.metrics.jsonl` line (schema: `retro`; token figures labeled estimates) atomically as part of the transition, so `/ce-retro` reads a stream that cannot drift from the state it describes. (`ledger-append` and `budget-add` mutate state but emit no metrics line — a decision row and a bare budget accrual are not `.metrics.jsonl` events.) The event/gate the script emits per transition:

   | run-state call | emitted metrics line |
   |---|---|
   | `advance <id> <status>` (pass) | `event:"gate"`, `gate:"pass"` (a status advance) |
   | `advance <id> done` | `event:"stage-complete"` |
   | `park <id> --class spec-gap\|structural` (test-integrity / dependency / scope FAIL) | `event:"park"`, `escalation_type:null` (spec-gap/structural, never a `bug`) |
   | `park <id> --class surface-defect` (step 5½) | `event:"park"`, `escalation_type:null` |
   | `retry <id>` (verification / review re-spawn) | `event:"retry"` (exit 1 = cap → circuit-break) |
   | `advance <id> implementing --escalation /ce-implement` (diagnose `bug` re-implement, mode on) | `event:"escalation"`, `escalation_type:"/ce-implement"` (the one autonomous route) |

   Pass `--detail "<string>"` to carry the specific detail (`"test-guard: <N weakened/deleted/skipped>"`, `"dep-guard: <N> new (<U> undeclared, <T> typo-flag)"`, `"review: high(confirmed=N,suspected=M) med=N low=N"`); the review gate's `fail` is emitted only when a `confirmed`-high blocked (blocking-on-high) — `pass` in advisory.

After the loop, **spawn one integration subagent** — `verify` over the whole built app: one dev server, whole-suite + build + lint, re-confirm each feature's criteria, walk cross-feature journeys (browser, evidence), confirm bridges whose replacer is built are retired; it writes `verification-report.md`. **This pass independently re-renders every `manual:harness-gap` verdict the implement subagents self-certified.** Those verdicts were rendered by the *author* agent in-loop (it can — a tool drives them), so this fresh agent — which did not write the code — re-drives them against the integration server and records its own verdict; a disagreement surfaces at the end-review. This is the harness-gap analog of the spec→implement spawn boundary: a tool-renderable verdict gets a second, independent renderer instead of resting on the author's self-report. It catches a false Pass the author missed, **not** one the model shares across both passes (the floor-not-ceiling limit every model-based gate carries). `manual:judgment` verdicts are different — they are gathered directly from the human at the end-review, never self-certified.

Per-feature `manual:harness-gap` verification is ephemeral inside each implement subagent; cross-feature journeys use the single integration server. *(In the spawn model this supersedes a run-long persistent server — per-feature isolation is worth the cheap rebuild.)*

**Surface-defect timing — caught where introduced, autonomously.** The in-loop catch is **step 5½'s per-feature `surface_findings` park**, not a mid-loop `verify` spawn: a functional surface defect parks its feature *before* any dependent is built, so it cannot ride green through downstream features (the failure the original run hit — a layout defect in feature 04 propagating through 05–08). This works unattended because 5½ is an **evidence-gated finding disposition** (park on a clause or cited blocked use), not a human verdict — honoring Operating Principle 1 (no routine questions mid-loop). The post-loop integration `verify` then re-checks **cross-feature** journey readability, **capturing the surface evidence and deferring its readability verdict to the Stage-3 end-review** (like every other `verify` judgment under auto-build) — human judgment stays batched to the bookends.

**Why subagents, not one context:** each gets a fresh context scoped to one feature (no compaction on large plans), and **the orchestrator — which has filesystem access — enforces the gates as real on-disk checks between agents.** The implement subagent literally cannot collapse spec into implementation: it did not write the spec, and the gate verified the files on disk before it ran.

### Challenger (push to best-fit)

Without the human's interrogation, autonomous decisions drift toward the *first reasonable default* rather than the *best fit*. The Challenger recovers that pressure — and **only** that: it challenges, it never answers.

It is **substrate-independent and required** when mode ≠ off: spawned mode runs it as a fresh challenger subagent; in-context mode runs it as a mandatory self-critique pass with the identical protocol. It is a **gate** — its verdicts are recorded in the run report's Challenges table *before* implement begins — **not** optional scrutiny to be "folded in" if the run drops spawning.

- **Scope:** material **engineering** decisions, especially the **assume-and-flag** class (the agent's labeled guesses), and four high-cost **self-classifications** the spec agent makes with no mechanical gate: the **NEW-vs-SHARED** split on a persisted/wire shape (§3.2 — mislabeling a SHARED shape `NEW` *bypasses §3.5 entirely*, so it never emits an additive-vs-breaking decision at all; verify it against real consumer enumeration), the SHARED-shape `additive`-vs-`breaking` call (§3.5 — a `breaking` change mislabeled `additive` is a **park-class decision dressed as engineering**, exactly the mis-classification check below), a `manual:judgment` test-case tag that should be `auto` / `manual:harness-gap` (a hard test dodged), and a reversible-vs-blocking product call (an `assume-and-flag` that should be a PARK). Skip trivial `auto` decisions. **Never answer** the PARK class (product / business, destructive, ADR-worthy, boundary) — those it may only **escalate-to-park**; answering would fabricate the project owner's knowledge. Interrogating whether a call was *correctly classified* is in scope; *answering* the parked call is not.
- **Each round**, in a fresh context that read the sources independently, it demands: the **options** considered (≥2), the **tradeoffs**, and **why this fits *this* project** (cite codebase / ADRs / conventions / scope). It checks for a **shallow default** (didn't read the code), **gold-plating** (more than scope needs — YAGNI), and **mis-classification** (a park-class decision dressed as engineering).
- **Bias:** appropriate fit, not maximal thoroughness — push back on shallow defaults *and* over-engineering; a challenge must never expand scope (Scope Lock holds).
- **Bounds & exits:** ≤ 2 rounds per feature. **accept** → proceed (`run-state.py advance <id> challenged`) · **escalate-park** → the orchestrator parks the feature (`run-state.py park <id> --class <product|destructive|structural|boundary>`) · **accept-and-flag** → an engineering disagreement that won't converge is taken at its best version and flagged for the end-review (only park-class escalations block).
- **Independence & its limit:** a fresh context that did not make the decisions — it catches *shallowness* and *over-build*, but shares the model's blind spots, so it cannot catch *shared error*. It raises the floor, not the ceiling.
- **Transparency:** every challenge + resolution is recorded in the run report, so the end-review human audits the Challenger too. It sits between spec's own options-drafting and the end-review spot-check: **draft → independent challenge → human final check.**

### Enrich-Parks (scope a park, never resolve it) — *on-demand module*

**Off by default.** When enrich-parks mode is on (a consented Stage-0 choice), an
**architecturally-significant or genuine multi-option PARK-class** fork (never a
product/business or destructive park) is turned via the `/ce-decide`
discipline into a **scored decision package + proposed-ADR draft** (`reasoned` mode,
situation weights marked `inferred`) that rides along as the park's blocking record for the
Stage-3 end-review. It **scopes the choice; it never makes it** — the complement of the
Challenger across the framework's bright line (the Challenger pressures the engineering
decisions the agent *may answer*; Enrich-Parks scores the PARK-class forks it *must not*),
and it is budget-tied, so on a tight budget the bare park still surfaces (no silent loss).
**Load `${CLAUDE_SKILL_DIR}/gate-enrich-parks.md`** for the full protocol and the mandatory
guardrails (reasoned-mode weighting, parks-the-package-never-clears-it, budget-tie).

### Review Gate (review code after implement)

The challenge gate interrogates *decisions* before implement; the **review gate**
interrogates *code* after it — the missing independent check on implementation
quality. `verify` confirms the code *behaves*; the review gate examines
*how it is written*.

- **Substrate-independent:** spawned mode runs it as a fresh review subagent;
  in-context mode runs it as a self-critique pass with the identical lenses. It is
  a **gate** — verdicts recorded in the run report's Code Review table before the
  feature is marked done.
- **Independence:** the reviewer did not write the code (a spawned subagent whose
  only inputs are the code on disk + the spec as contract) — the same reason the
  spawn model beats one self-policing context.
- **Scope (the six lenses):** correctness beyond tests, security, performance, maintainability,
  contract / spec conformance, simplicity (YAGNI). It judges the code against the
  spec and ADRs as contract — a design disagreement is a `/ce-spec` escalation, not a
  code finding.
- **Verification pass (generate-then-verify):** every High finding gets a second adversarial pass (reproduce a behavioral High by tracing it to a reachable trigger/sink; refute a judgment High's `file:line` + ADR citation) → tagged `confirmed | suspected`. This is the precision lever — it runs whenever review runs (both modes), an in-context second pass, not a nested spawn. Findings + per-confidence counts land in `specs/<id>/review-summary.json`.
- **Disposition:** in **advisory** mode (the default) all findings are recorded
  and **nothing blocks** — the run is not gated on the model's own fallible
  high-severity judgment. In **blocking-on-high** mode, **only `confirmed`-high** security /
  correctness findings **block** — the orchestrator gates on `review-summary.json`'s precomputed `blocking_high` count (loop to a fresh implement subagent within the retry cap, or park); a **`suspected`-high is recorded and surfaced at the end-review, never blocks, never burns a retry** (the verification pass demoted it); medium / low are recorded. **Performance is advisory-only** — a perf finding never blocks, even under blocking-on-high (it can never be High): only `/ce-probe-perf` can prove a numeric breach, and it runs out-of-band of this gate. A missing `review-summary.json` degrades to the `code-review.md` prose, recorded — never a silent skip.
- **Independence limit:** the feature's diff + one hop; like the Challenger it
  **raises the floor, not the ceiling** — it shares the model's blind spots and
  cannot catch shared error. Static review, not a pentest (`/ce-probe-sec` owns runtime).

### Diagnose Gate (root-cause a failure before retrying) — *on-demand module*

**Off by default.** When diagnose mode is on (a consented Stage-0 choice), a failed verification-artifact gate (step 5) or a **reproducible** blocking review finding (step 6) is root-caused via `debug` **before** the orchestrator retries or parks — turning a blind retry into a targeted one, and parking early on a `spec-gap` / `structural` / `not-a-code-defect` cause no retry can fix. It changes control flow (retry-vs-park, and which circuit-breaker bounds the run), which is why it is opt-in. **Load `${CLAUDE_SKILL_DIR}/gate-diagnose.md`** for the full protocol — the miss-safe diagnosis gate, routing by class, retry accounting, and resume behavior.

### Substrate Fallback (spawned → in-context)

Driving the spawn → on-disk-gate → spawn loop turn-by-turn can be operationally unreliable (delayed/batched tool-result delivery). If it is, **fall back to in-context execution** — but the fallback loses **only** spec↔implement context-isolation. **Every other discipline still runs, in-context:** spec-first + the on-disk gates, the **challenge gate** (as a self-critique pass), per-feature **ADR promotion**, `verification.md`, the ledger, the `feature-plan.md` checklist tick, and (when diagnose mode is on) the **diagnose gate** as an in-context self-diagnosis pass. None of these is spawn-only — they are gates and artifacts, not a substrate.

The lost isolation is a **structural-guarantee degradation, not a free capability waiver**: record it prominently and surface it at the end-review (e.g. *"spec/implement isolation relaxed for features 02–06"*). **Never silently fold a discipline away because spawning stopped** — only isolation degrades, and it degrades *loudly*.

---

## Budget Metering

The Stage 0 **token/compute budget** is metered so the circuit-breaker fires on data, not vibes. **The running total is owned by `run-state.py`, not hand-kept.** The orchestrator estimates each spawn's cost — `chars/4` over its prompt + returned result (**labeled an estimate**, never billing-grade) — and feeds it in with the transition it belongs to: pass `--tokens <estimate>` on the step-7 `advance` / `park` / `retry` call, or book a cost not tied to a status move with `run-state.py budget-add --tokens <estimate> --plan-dir "docs/plans/<slug>"`. The script accrues it into `counters.budget_spent`; the per-feature rows + the total are read back from state for the run report. The **budget-exhausted circuit-breaker is `breaker-check`'s exit 1** (§ step 7a) — when `budget_spent` crosses the budget, `breaker-check` returns 1 with the `budget-exhausted (<spent>/<budget>)` reason, and the orchestrator behaves like every other breaker: **halt, write the partial summary, run the end-review** on the completed / parked / failed split. Budget pressure **never** marks an unfinished feature done and **never** skips or shortcuts a feature's verification or review to save tokens — that would be the silent degradation the toolset forbids. (No metering capability → the budget bound is advisory; record that as a degradation, don't fake a number.)
