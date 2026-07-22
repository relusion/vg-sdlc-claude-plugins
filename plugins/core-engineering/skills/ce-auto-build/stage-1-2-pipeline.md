# Auto Build — Stage 1+2: Sequential Pipeline

Read `SKILL.md` and complete Stage 0 first. Run exactly one feature at a time in
plan `ship_order`.

**Next:** after the loop and integration verification, or after a bound halts the
run, load `${CLAUDE_SKILL_DIR}/stage-3-endreview.md`.

## Worker contract

Every worker is a fresh Task context and receives these constraints:

- It cannot ask the human. An unresolved authority decision returns `parked` with
  the decision, class, evidence, and blocked work.
- It may write only the repository files required by its assigned feature and its
  required evidence artifacts.
- It performs no git operation, credential access, destructive action, external
  write, PR action, or deployment.
- It reads applicable ADRs and plan constraints fresh from disk.
- It reports new dependencies and non-routine decisions explicitly.
- It never reports a gate as passed without leaving the required evidence on disk.

The implementation worker must preserve `.test-guard/<id>/` snapshots until the
orchestrator completes the final cross-feature test-integrity checks. The orchestrator
also maintains two cumulative sets from Stage 0 onward: every spec that reached
implementation, and every dependency name a worker verified. Record dependency names
in the run ledger so resume can reconstruct the set from disk.

## Per-feature loop

For each selected feature whose hard dependencies are done:

### 1. Specify

Spawn `spec-author` (preferred) or a fresh generic specification worker. Direct it
to the existing-plan path in the `spec` skill and its autonomous overlay. Give it
the feature, shared context, relevant ADRs, dependency specs, threat obligations,
and interaction-contract obligations. It writes:

```text
docs/plans/<slug>/specs/<id>/ce-spec.md
docs/plans/<slug>/specs/<id>/tasks.json
```

It may make routine engineering decisions and record reversible assumptions. It
must park product, security-acceptance, destructive, architectural, and boundary
decisions.

Run the external spec gate:

```bash
test -f "docs/plans/<slug>/specs/<id>/ce-spec.md"
test -f "docs/plans/<slug>/specs/<id>/tasks.json"
python3 "${CLAUDE_SKILL_DIR}/scripts/spec-lint.py" \
  "docs/plans/<slug>/specs/<id>" --json
```

- Pass: `run-state.py advance <id> specced`.
- Lint failure or missing artifact: call `run-state.py retry <id>` and spawn one
  repair attempt with the exact failures. Exit `1` from `retry` marks the feature
  failed and halts the batch for end-review.
- `spec-lint` could not run: park as `tooling-gap`; do not treat artifact presence
  alone as equivalent assurance.
- Worker park or a disarmed security-obligation check: `run-state.py park` with the
  returned class. Mark hard dependents blocked.

Book the worker cost on the corresponding state transition.

### 2. Implement and verify

After the spec gate passes, run
`run-state.py advance <id> implementing`. Spawn `spec-impl` (preferred) or a fresh
generic implementation worker. Its specification inputs are only the on-disk
`ce-spec.md` and `tasks.json`; missing files are a stop, not permission to improvise.

Direct it to the `implement` skill and its autonomous overlay. It works test-first,
runs the applicable suite and acceptance checks, and writes
`specs/<id>/verification.md`, including a reproducible try-it-yourself section.

Then run the external gates against the clean Stage-0 baseline. For scope, repeat
`--spec-dir` for the current spec and every earlier spec that reached implementation;
this checks the cumulative diff against the cumulative approved file union. For
dependencies, pass the union of verified dependency names returned by every worker so
far, not just the current worker's names:

```bash
# Artifact floor: verification.md exists and every tasks.json task is done.
python3 "${CLAUDE_SKILL_DIR}/scripts/test-guard.py" \
  --verify-passes --spec-dir "docs/plans/<slug>/specs/<id>" --json
python3 "${CLAUDE_SKILL_DIR}/scripts/test-guard.py" \
  --snapshot ".test-guard/<id>/<task-id>"        # for every snapshot
python3 "${CLAUDE_SKILL_DIR}/scripts/test-guard.py" \
  --base <run-baseline> --feature <id>
python3 "${CLAUDE_SKILL_DIR}/scripts/dep-guard.py" \
  --base <run-baseline> --feature <id> --declared <cumulative-verified-dependency-names>
python3 "${CLAUDE_SKILL_DIR}/scripts/implement-scope-guard.py" \
  --spec-dir "docs/plans/<slug>/specs/<first-started-id>" \
  [--spec-dir "docs/plans/<slug>/specs/<next-started-id>" ...] \
  --base <run-baseline> --json
```

Dispose of results conservatively:

- An implementation worker that returns `parked`: call `run-state.py park` with
  its returned class and evidence, then mark hard dependents blocked. Partial
  writes never convert a park into a pass.
- A returned functional `surface_findings` item that is bound to a contract clause
  or proves a blocked use is a `spec-gap` park. Record taste findings in the ledger
  for end-review; they do not block by themselves.
- Artifact, task, test, build, lint, or acceptance failure: call `retry`. Below the
  cap, spawn a fresh implementation attempt with the exact failure evidence. At the
  cap, mark `failed` and halt for end-review.
- Test-integrity, undeclared dependency, or out-of-scope file failure: park as
  `structural` or `spec-gap`. Retrying code cannot authorize a weak test, package,
  or widened boundary.
- Any gate exit `2`: park as `tooling-gap`. Never convert could-not-run to pass.
- All gates pass: `run-state.py advance <id> verifying`. Retain this feature's
  `.test-guard/<id>/` snapshots until integration verification so a later feature
  cannot erase or weaken its tests undetected.

A non-zero deterministic gate is authoritative. Never replace it with a manual Git
inspection or reinterpret generated-looking paths as a pass. Expected caches and
hook logs must be ignored by the repository before the run; once the gate fails,
apply the disposition above and preserve its evidence for end-review.

`retry` counts failed gate attempts, including the first failure; a cap of two
therefore authorizes one fresh repair. After each repair worker returns and its gates
run, append this durable worker-result row before calling `retry` again:

```json
{"event":"repair-attempt","feature":"<id>","attempt":1,"outcome":"gates-pass|gates-fail|worker-parked","evidence":"<exact short result>"}
```

Use the attempt number returned by the preceding successful `retry` call. This row
is evidence that a repair worker ran; the retry counter alone records only gate
failures.

### 3. Review

Spawn a fresh review worker that did not write the code. It reads the current
feature's returned file list, specification, relevant ADRs, repository review policy,
and the cumulative working-tree diff. It flags any change to an earlier feature's file
that the current spec does not justify. It reviews correctness, security, contract
conformance, maintainability, performance risks, and unnecessary complexity. It writes:

```text
docs/plans/<slug>/specs/<id>/code-review.md
docs/plans/<slug>/specs/<id>/review-summary.json
```

Direct the worker to the existing review contract at
`${CLAUDE_SKILL_DIR}/../ce-review/SKILL.md` and require it to load
`${CLAUDE_SKILL_DIR}/../ce-review/artifact-template.md` before writing. The machine
summary must use that exact `status` / `blocking_high` / `blocking_route` schema;
do not reconstruct a new verdict format from memory. Then validate it externally:

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/review-gate.py" \
  "docs/plans/<slug>/specs/<id>" --require-blocking-route --json
```

Every high-severity correctness or security finding receives an adversarial
confirmation pass and is labeled `confirmed` or `suspected`.

- Missing, unreadable, or schema-invalid review artifacts (gate exit `2`): park as
  `tooling-gap`.
- Confirmed high correctness/security finding (gate exit `1`): read the validated
  gate JSON's `blocking_route`. For `plan-conflict`, park the feature as
  `plan-conflict` with the exact finding and `/core-engineering:ce-plan` as the
  human-owned next action; do **not** call `retry`, advance to `implementing`, or
  send it to an implementation worker. For `implement`, call `retry`; below the
  cap, run `run-state.py advance <id> implementing`, then return to a fresh
  implementation worker with that evidence, re-run every implementation gate,
  and review again. At the cap, mark failed and halt. Any absent/unknown route is
  schema-invalid gate exit `2`, never an implementation default.
- Suspected high, medium, and low findings: record for the final human review. They
  do not silently disappear and do not block the batch.
- No blocking finding (gate exit `0`): `run-state.py advance <id> reviewed`, then
  `done`.

Append worker decisions through `ledger-append`. Regenerate `STATUS.md`, then run
`breaker-check`. Exit `1` halts at the named budget or park bound; exit `2` halts
because state is untrustworthy. Otherwise continue to the next ship-ordered feature.

A parked feature blocks its hard dependents. Mark those dependents blocked in the
report and continue only with later features that are dependency-independent.

## Integration verification

Before spawning the verification worker, rerun `test-guard --verify-passes` and every
retained `--snapshot` for each completed feature. Rerun `dep-guard` with the cumulative
verified dependency set and `implement-scope-guard` with every spec that reached
implementation. A non-zero deterministic gate is an integration failure; retain the
snapshots and report it without repairing in this pass. Only after every cumulative
gate passes may the orchestrator remove the selected features' `.test-guard/<id>/`
directories.

After the loop, spawn one fresh verification worker over the combined working tree.
It runs the whole test suite, build, and lint; rechecks completed features' acceptance
criteria; and exercises available cross-feature journeys and integration bridges. It
writes `docs/plans/<slug>/verification-report.md`.

Do not repair integration failures inside this pass. Record the failing feature or
unknown ownership, evidence, and cheapest next check for the human end-review. A
missing required capability is a coverage gap, not a fabricated pass.

## State transitions and metering

The normal fixed path is:

```text
queued → specced → implementing → verifying → reviewed → done
```

Only a confirmed review failure may move `verifying → implementing`, after `retry`
accepts the attempt. `park` and `failed` are terminal for this run.

Estimate each Task exchange as `(prompt characters + result characters) / 4`. Add
the estimate using `--tokens` on `advance`, `park`, or `retry`; use `budget-add` for
work not tied to a transition. The estimate may be imperfect, but it must be applied
consistently. Budget exhaustion stops new work; it never truncates an active gate or
marks incomplete work done.
