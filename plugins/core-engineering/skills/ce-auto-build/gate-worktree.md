# Auto-Build — Worktree Parallelism  *(on-demand module)*

Gate module for the `ce-auto-build` skill (orchestrator: `SKILL.md`). **Loaded only when the Stage-0 parallelism bound is `worktree`** (opt-in, default OFF) and the capability preflight confirms support. Governs running provably-independent features concurrently, each in its own git worktree.

**Next:** return to the pipeline in `SKILL.md` (Stage 1+2); the per-feature gates, the circuit-breaker, and the never-commit-to-the-human's-branch rule are unchanged.

---

## Worktree Parallelism (opt-in, default OFF)

By default auto-build is sequential — the safe mode. When the Stage 0 **parallelism** bound is `worktree` *and* the capability preflight confirms support, a group of **provably-independent** features may run concurrently, each in its own git worktree.

**Independence test (all must hold, for every pair in the group).** A hard-dependency antichain alone is **not** enough:

- no hard-dependency path between them, **and**
- no soft-dependency / bridge relation, **and**
- **disjoint MODIFY reach** — from the plan's CALL/MODIFY reachability data (`stage-4-7-gates.md`). CALL-only coupling is fine; any **MODIFY overlap forces sequential** (they would collide on the same files).

**Preserve ADR propagation.** Parallelize only features expected to make no cross-cutting, ADR-class decision. If a parallel **spec** subagent emits a record-don't-park ADR, **pause the group's unstarted spec agents**, fold the ADR into `shared-context.md`'s ledger, and have the remaining features read it fresh — so the sequential guarantee "later features honor earlier ADRs" is not silently lost to concurrency.

**Integration is orchestrator-owned, script-backed, and never auto-resolved.** Each worktree runs the full per-feature pipeline (every gate, per worktree). When a group completes, the **orchestrator merges** each worktree branch back onto the run branch using the bundled deterministic script — never a hand-run `git merge` — so the conflict-stop is a machine fact, not prose:

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/worktree-merge.py" \
  merge --from-branch "<feature-branch>" --into "<run-branch>" --root . --json
```

It runs `git merge --no-ff --no-commit` and **never resolves** — on conflict it runs `git merge --abort` (restoring a clean tree) and reports the conflicting paths. **Dispose on its exit code:**

- **`0` (merged, staged-uncommitted)** → commit the staged merge per **Checkpoint Mode** (the orchestrator's per-feature checkpoint commit; never the human's branch, never pushed). In `none` mode leave it staged for the single run-tree.
- **`1` (merge conflict, aborted — tree left clean)** → **STOP that group** and fall back to running its remaining features **sequentially**. This is the mechanical conflict-stop: the script has already aborted, so no half-merged state survives. The conflicting paths are in the JSON `conflicts` list — surface them, never auto-resolve.
- **`2` (refused / could-not-run)** → record a **degradation** in the run report and go **sequential** for the group. Exit 2 covers the safety refusals: merging into the protected branch (the script reuses git-guard's `protected_branch()` derivation), a dirty target tree, a mismatched checked-out branch, or a non-conflict merge failure.

Then the existing single **integration `verify` pass** runs over the merged result (the behavioral backstop).

Companion subcommands mirror the preflight's conventions (`--json`, `schema_version`): `create --branch <b> --path <p>` (adds a worktree, refusing a non-empty target path), `remove --path <p>`, and `list` (structured worktree inventory).

**Capability-gated.** Enable only when the preflight confirms (a) git worktree support and (b) **per-worktree runtime isolation** — isolated ports / test DBs so concurrent ephemeral servers don't collide. If either is missing, **fall back to sequential** and record it. Every per-feature gate, the circuit-breaker, and the never-commit-to-the-human's-branch rule are unchanged.

Run the bundled deterministic preflight before spawning any parallel group:

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/worktree-preflight.py" --root . --plan "docs/plans/<slug>/plan.json" --json
```

The script returns `parallel_groups` computed from hard dependencies plus
MODIFY-reach disjointness. A feature missing MODIFY-reach is kept sequential.

**Expect singletons here, and do not read that as a failure.** Reach comes from a
plan.json reach key when one exists, else from the union of `specs/<id>/tasks.json`
`files[]` — and in worktree mode the *spec agent runs inside the group*, so the
grouping decision is made before any `tasks.json` exists. `reach_sources` will read
`none` for every feature and the run goes sequential. That is the conservative default
working as designed: a plan-time guess at which files a feature will touch is not
proof, and this script's contract is to prove.

The script does **not** prove runtime isolation; the orchestrator must still
surface ports/test-database isolation as a Stage-0 capability decision. And reach is a
floor even when derived — a task that edits a file its `files[]` never declared can
still collide. The mechanical backstop for that is `worktree-merge.py`'s
conflict-abort (exit 1), never this preflight.
