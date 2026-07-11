# Autonomous Mode — the auto-build execution overlay for `/ce-implement`

Loaded **only** when `/ce-implement` runs under `/ce-auto-build` (a spawned
implementation worker). The interactive `/ce-implement` never loads this file —
its review-and-approve gates apply as written. Read it once, before Stage 0, and
apply it for the whole run.

---

When invoked by `/ce-auto-build`, run without interactive gates, applying auto-build's **Decision Classification**:

- **Auto-resolve** routine implementation choices (record notable ones in the run ledger).
- **Working tree + version control are the orchestrator's.** Do not check, acknowledge, or stop on a dirty working tree, and do not establish a VC policy or branch — auto-build owns the **clean-tree gate** (its Stage 0) and all git (Spawn Contract). Stage 0's working-tree ack and VC-policy prompts are suppressed here.
- **Park** (return control to the orchestrator) on any **destructive operation** — never auto-run migrations, deletes, or schema changes — and on a **Spec Conflict** (do not escalate interactively).
- **Run verification normally** — `auto` tests must pass per task and per feature; this is never skipped.
- **Do not delete the red-test snapshots.** The per-task gate's PASS step deletes `.test-guard/<id>/<task-id>/` *in interactive mode only*; under autonomous mode **leave every snapshot on disk** for the whole run — the orchestrator re-runs test-guard over them as an external gate and owns their cleanup. Deleting them would blind the orchestrator's independent within-task-genie check (its `--snapshot` re-run would hit an empty dir → degrade). This is the snapshot half of the Spawn Contract.
- **Verify and record every new dependency.** The network existence/age/typo check (step 3) still runs autonomously — use `npm view` / `pip index versions` / Safe Chain (if configured), and **park** a dep you cannot verify rather than installing it. **Return each verified new dependency** (name@version, ecosystem) in the result's `decisions` so the orchestrator appends it to the ledger and re-runs `dep-guard.py --declared <those names>` externally as a gate — a dep in the manifest you did not return is the undeclared/slopsquat case the orchestrator will catch. Offline → park the dep, do not install it unverified.
- **Manual test verdicts — split by kind.** `manual:harness-gap` cases: if a browser MCP and a running app are available, **verify them during the run** (drive the UI, capture evidence) and record an evidence-backed agent verdict; otherwise defer. `manual:judgment` cases: capture evidence where possible but **defer the verdict** to auto-build's end-review.
- **Surface Critique — return, don't drop.** When the feature renders a user-facing surface, run the Surface Critique inverse pass (Stage 2) on the captured screenshot and **return its findings in the result's `surface_findings`** (each `{class: functional|taste, severity, evidence-tier, surface-kind: dom|canvas, contract-clause|unbound, evidence-ref}`) — the same return channel as `decisions`. A **functional** finding bound to a clause or citing a blocked use is a Spec-Conflict-class **park**; the orchestrator dispositions it (a `taste` finding informs the end-review, never parks). A surface defect with no return channel dies as unread text — this is the channel.

Outside autonomous mode, the review-and-approve gates throughout this workflow apply as written.
