---
name: ce-verify
description: |
  Verify a plan's implemented features work together — whole-suite regression, journey walks, durable-noun revisits, bridge retirement, dependency-manifest integrity, stakeholder acceptance — and produce the handover report.
  Triggers: verify/integration-test/pre-handover-check a plan. Asks DOES IT BEHAVE (a gate); for code quality use /core-engineering:ce-review.
argument-hint: "[journey]"
allowed-tools: Read, Write, Glob, Grep, Bash, AskUserQuestion, Skill
---

# Verify

**Invocation input:** Journey to verify (optional): $ARGUMENTS


Verify that the implemented features of a plan work together. This is the last
link in the discipline chain: `plan ← spec ← implement ← verify`. Verify checks
that the software **behaves** as specified; its sibling
`/core-engineering:ce-review` checks **how the code is written** (correctness beyond
tests, security, maintainability, conformance) — run both before handover.

This workflow does **not redesign or patch code**. It runs the whole project's
tests, walks the planned journeys end-to-end, checks bridges are retired, and
facilitates stakeholder acceptance. When it finds a defect it **escalates** —
never fixes — keeping `spec` and `implement` as the only path that mutates code.

It runs in two modes:

- **Milestone** (`/core-engineering:ce-verify <journey>`) — verify one journey once
  all its composing features are implemented.
- **Pre-handover** (no argument) — verify the whole project.

It can be run at any point during plan implementation; it operates on whatever
features have been implemented so far. Under `/core-engineering:ce-auto-build` it runs as the
**post-loop integration pass** — it captures the surface evidence and **defers its
readability verdict to the end-review** (auto-build batches human judgment to the
bookends, so this human-verdict skill is not spawned mid-loop). The *in-loop*
surface-defect catch — parking a broken surface before dependents build on it — is
auto-build's per-feature autonomous Surface Critique (`surface_findings`, gated on a
clause or cited blocked use), not this skill.

## Runtime Inputs

- **Journey (optional):** id or short name. Without one, run in pre-handover mode.
- **The plan directory:** locate `docs/plans/[slug]/`. If more than
  one matches, ask the user which to verify.
- **Loaded (read-only):** `feature-plan.md` (traced journeys, bridges, execution
  checklist), `plan.json` plus `architecture-selection.json` (current plan and
  architecture authority), `shared-context.md` (codebase profile, project docs,
  pitfalls, ledger), and
  each feature's `specs/<id>/ce-spec.md`, `tasks.json`, and `verification.md` where
  they exist.

This workflow never modifies source, specs, task state, or any loaded planning
artifact. It owns three bounded writes in the plan directory: create or update
the cumulative `verification-report.md`, replace its derived
`verification-summary.json` freshness receipt, and append optional telemetry to
`.metrics.jsonl`.

## Execution Contract

*Gate locator (HITL R5):* print `Gate N of M — <name>` at every interactive gate; compute M from the gates that actually fire this run, never a hardcoded constant.

0. **Session write lease (structural, first act).** `python3 "${CLAUDE_SKILL_DIR}/scripts/write-lease.py" --set --skill ce-verify --allow 'docs/plans/**/verification-report.md' --allow 'docs/plans/**/verification-summary.json' --allow 'docs/plans/**/.metrics.jsonl'` — the write guard limits this run to the cumulative report, its derived receipt, and optional telemetry. Last act, on success, failure, or early exit: `python3 "${CLAUDE_SKILL_DIR}/scripts/write-lease.py" --restore-baseline`. A denied write means this contract and the attempted action disagree — reconcile them; never edit or delete the lease to proceed.
1. **Verify, do not fix.** Find defects and escalate; never patch code, never edit specs, never edit feature files.
2. **Bounded artifact writes.** Create or update only `verification-report.md`
   and its script-derived `verification-summary.json`; append only to
   `.metrics.jsonl`. All source, plan, spec, task, and implementation
   verification inputs remain read-only. Never hand-compose the summary.
3. **Grounded.** Scenarios come from the plan's traced journeys and the specs' EARS criteria and test cases — never from-scratch tests. The Stage 2.5 revisit walk is the reciprocal of the plan's Stage 6.3 closure rows, scripted off the feature's built write surfaces — not an invented test.
4. **Derive state, don't trust claims.** A feature is `implemented` only if its `tasks.json` exists and every task is `done` and `verification.md` exists; anything less is in progress.
5. **Current authority only.** Before deriving feature state, require the
   current plan and architecture-selection schemas. Legacy/reportless
   architecture selections are diagnostic inputs, never verification
   authority.
6. **Evidence-first HITL.** Automated and tool-demonstrated Pass rows are
   reported without confirmation. Prompt only for a Fail needing disposition,
   uncertain evidence, `manual:judgment`, or stakeholder acceptance. Group
   related flagged rows without mixing their decisions.
7. **Honest scope.** Local end-to-end verification and acceptance facilitation. UAT in a real staging environment is a deployment concern, out of scope.
8. **Never commit, push, or deploy.** Those remain the human's responsibility.

## Human-in-the-Loop — batched

Drive and capture evidence before asking. A clean journey or noun produces no
gate. When one has flagged rows, print `Gate N of M — <journey|noun>` and ask
only about Fail disposition, uncertain evidence, or `manual:judgment`; keep each
decision independently answerable. Deterministic mismatches are reported as
failures and routed, not re-litigated as human verdicts. Pre-handover
stakeholder acceptance remains a material gate.

Never patch code; never modify artifacts outside the two bounded write paths.

---

## How to Run This Workflow

This skill is **staged**: `SKILL.md` (this file) is the orchestrator — it holds the Execution Contract, the Human-in-the-Loop moments, the stage map, the Escalation table, and the Closing block — and each stage's detailed procedure lives in a separate file you load only when you reach that stage, not before.

**The stage and template files named below are bundled in this skill's own directory.** Read each at `${CLAUDE_SKILL_DIR}/<file>` — `${CLAUDE_SKILL_DIR}` is the environment variable that resolves to this skill's directory regardless of the current working directory. Resolve it once if needed (`ls "${CLAUDE_SKILL_DIR}"`) and read each file by its resulting absolute path; **never load a companion file by bare name** — in an installed plugin the working directory is the user's project, so a bare name finds nothing and triggers a filesystem search.

Execute the stages in order. Load each stage file when you reach it — not before. Each opens with a **Next:** header naming the file to load after it.

| Stages | Load this file | Purpose |
|---|---|---|
| 0–1 | `${CLAUDE_SKILL_DIR}/stage-0-1-load-check.md` | Locate the plan, derive scope, and run system checks |
| 2–2.6 | `${CLAUDE_SKILL_DIR}/stage-2-2.6-walks.md` | Journey, durable-noun/governance, and surface-removal evidence walks |
| 3 | `${CLAUDE_SKILL_DIR}/stage-3-acceptance-report.md` | Present the result, stakeholder acceptance (pre-handover only), write `verification-report.md` |

At the write step, `${CLAUDE_SKILL_DIR}/stage-3-acceptance-report.md` directs you to **`${CLAUDE_SKILL_DIR}/artifact-template.md`** for the Report Template. Do not reconstruct the report format from memory.

To begin: load `${CLAUDE_SKILL_DIR}/stage-0-1-load-check.md` and start Stage 0.

---

## Escalation

Verify never fixes code. When a check fails:

| Failure | Escalate to |
|---|---|
| Cross-feature regression / failed criterion | `/core-engineering:ce-implement <id>` — re-open the broken feature |
| Bridge not retired | `/core-engineering:ce-implement <replacer-id>` — the replacer should have retired it |
| Journey broken by missing connection or bad ship order | `/core-engineering:ce-plan` — the journey design itself is wrong |
| Durable noun with no reachable revisit/amend surface (Stage 2.5) | `/core-engineering:ce-plan` — a lifecycle reciprocal was never owned by a feature |
| Durable noun with no real governance consumer — retain/export/erase (Stage 2.5) | `/core-engineering:ce-plan` — a governance reciprocal was never owned by a feature |
| Existing surface broken with no shipped continuity (Stage 2.6) | `/core-engineering:ce-plan` — a deprecation/migration obligation was never owned by a feature |
| Undeclared / unverified dependency in the manifest (Stage 1) | `/core-engineering:ce-implement <id>` — re-open the feature to verify-and-declare or remove the dep; if it is legitimate but unspecced, `/core-engineering:ce-spec <id>` |
| A feature in scope is not yet `implemented` | `/core-engineering:ce-implement <id>` |

These complete the escalate-up chain: `plan ← spec ← implement ← verify`.

---

## Closing

After writing the report, confirm:

```text
Verified: <slug> — <mode>
Scope:    <N> of <M> features implemented
Report:   docs/plans/<slug>/verification-report.md
Status:   verified | failed | partial
```

Point to the next action: if failures escalated, name the skill
(`/core-engineering:ce-implement <id>` or `/core-engineering:ce-plan`); if pre-handover
passed, the project is ready for handover.

**Cross-journey UX — point, don't run.** If at least one in-scope journey carried `browser` verification-modality (the modality you already read at Stage 2 from the plan's Journey Map), append one pointer — otherwise suppress it entirely. This run proved each journey *behaves* and each rendered surface is *readable*, but it did **not** check the cross-journey experiential layer: **cross-feature consistency** (action-label / pattern / navigation / tone drift), **off-path dead-ends** one hop from the traced path, **coverage gaps**, and **missing empty/error states**. For those, run `/core-engineering:ce-ux-audit <slug>` before handover — it walks the plan's traced journeys (and auto-detects an adversarial plan-free probe where no plan owns the surface). Skipping it leaves that layer unchecked: acceptable for a CRUD tool, load-bearing for a game / experience app where flow *is* the product. **Name it, never auto-run it** — it is interactive and browser-driven and renders findings-not-verdicts, so the call stays the human's.

---

## Honest Limitations

- **Local end-to-end, not UAT.** Verifies against a local / dev environment; user-acceptance testing in a real staging or production environment is a deployment concern, out of scope.
- **Shares the model's blind spots.** Journey walks and evidence interpretation run on the same model that built the feature — an error baked into both the implementation and the reading of the evidence can pass. Independent ≠ omniscient.
- **Evidence is bounded.** A demonstrated `Pass` means the captured evidence
  matched the named observable; it proves nothing about inputs not walked.
  Stakeholder acceptance is a separate sign-off.
- **Surface critique is fallible.** Objective contract failures are reported
  from evidence; aesthetic taste remains `manual:judgment` and is never
  converted into a functional Fail.
- **Behavior, not code quality.** Checks that the software *behaves* as specified; it does not review *how the code is written* — run `/core-engineering:ce-review` as well before handover.
- **As complete as the harness.** A step whose modality can't be driven here falls back to a human-run observable and is recorded as degraded — never silently skipped, but not machine-proven either.
- **Closes named writes, not unnamed state.** The revisit walk fires off durable writes that actually shipped (a `db`/`event` step, a write criterion, a `tasks.json` write verb) — the only check keyed to built evidence rather than planned scope, so it can catch a noun the plan never named. But state persisted by a path nothing names as a write (an implicit autosave row, a server session assumed transient) emits no detectable signal and is not walked.
- **Governance horizons longer than a session are attested, not observed.** A `retain` policy whose window exceeds the verify session is confirmed from the wired job/TTL, never watched elapsing — the one governance reciprocal that cannot be walked to completion locally; recorded degraded, never silently passed.
- **Confirms named breaks, not silent ones.** Stage 2.6 walks a surface the codebase profile recorded as shipped and that the plan dispositioned in §6.4 — a surface broken by a path the profile never recorded as shipped emits no signal and is not walked, mirroring the named-writes limit above.
