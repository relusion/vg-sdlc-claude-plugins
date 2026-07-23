# Feature-Spec Workflow — Stages 4–5: Build the Task List, Assemble, and Write

Stage file for the `spec` skill (orchestrator: `SKILL.md`). Covers the task list and the final assemble / triage / approve / write sequence. Load this file after Stage 3 is complete.

**Next:** Stage 5.6 closes the workflow. At the write step, also read `${CLAUDE_SKILL_DIR}/artifact-template.md` for the `ce-spec.md` + `tasks.json` formats, and run the **Mechanical Lint Gate** defined in `SKILL.md`.

---

## Stage 4 — Build the Task List  *(Gap 4)*

### 4.1 Decompose

Turn the approved design into ordered, concrete tasks. Each task:

- names a specific change (file/area + what)
- is small enough to complete and verify in one focused step
- states its **verification** — the test cases it must make pass, or the command to run
- notes the pitfalls and conventions to honor
- traces to ≥ 1 test case (hence ≥ 1 acceptance criterion)

### 4.2 Order

Order tasks so the feature builds and stays testable incrementally; respect
internal dependencies; a behavior's tests land with or before that behavior.

### 4.3 Traceability

- Every test case → ≥ 1 task. A test case with no task is a gap — add a task.
- Every task → ≥ 1 test case. An **orphan task** is scope creep — remove it, or if it reveals missing scope, raise a Boundary Conflict (Stage 3.3).

### 4.4 Review  [tiered]

Derive mechanical ordering and task splits without a gate. Ask only when
granularity changes delivery risk, ownership, an irreversible sequence, or the
Scope Lock. Compact composition stops on such a decision.

---

## Stage 5 — Assemble, Triage, Approve, Write

### 5.1 Assemble

Assemble `ce-spec.md` + `tasks.json` per **`${CLAUDE_SKILL_DIR}/artifact-template.md`** in this skill's directory — do not reconstruct either file's format from memory.

Immediately before rendering, derive the exact architecture binding from the
already validated Stage-0 state:

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/architecture_context.py" --repo-root . \
  derive docs/plans/<slug> <id> --json
```

Exit 0 returns one `architecture_context`. Copy that exact object into
`tasks.json` and the `ce-spec.md` `## Architecture Context` JSON block. Never
hand-calculate the producer receipt or feature-mapping digest. Exit 1/2 parks
assembly and returns to Stage 0's owning plan/architecture route; a typed
`recommended-absent` or `not-required` result is valid context, not permission
to omit the block.

### 5.1.5 Mechanical Lint

Run the **Mechanical Lint Gate** from `SKILL.md` over the assembled scratch
artifacts:

- **PASS** → report H1–H7 with the command/result. Do not put those rows into a
  human checklist.
- **FAIL** → repair and re-run, or stop. No acknowledgement waives it.
- **Could-not-run** → stop with the tooling/integrity gap. No manual substitute.

### 5.2 Propagation Triage

Classify every resolved decision (from Stages 1 and 3) against four buckets and
route it:

| Bucket | Route to |
|---|---|
| Feature-local | Stays in `ce-spec.md` — no propagation |
| Cross-feature + architecturally significant | An ADR (already promoted in Stage 1.5 / 3.4) |
| Cross-feature, not architectural (a convention, fact, or constraint) | The **Resolved Project Decisions** ledger in `shared-context.md` |
| Reveals a plan error | Escalate to `/core-engineering:ce-plan` — do not propagate |

Appending to the ledger **mutates a shared artifact** — present each proposed
ledger entry as a *material* decision and let the human approve the wording.
Queue approved rows in scratch for the final transaction. Never sync silently,
and never push a feature-local choice into shared context.

### 5.3 Validation Checklist Before Writing

Run this adequacy review on the assembled, frozen artifact after propagation.
Mechanical H1–H7 results are evidence above, not questions. Ask only about an
unresolved row:

- the Scope/Excluded boundary is substantively correct and every Boundary
  Conflict is fixed or escalated;
- acceptance criteria adequately express reviewer triggers, assigned
  `TZ-NNN`/`IC-NNN` obligations, governance reciprocals, and any interface or
  surface-quality contract;
- `manual:judgment` is limited to genuinely subjective residue;
- design paths and dependency interfaces match the real repository;
- shared-shape and cross-feature-flow classifications are complete and any
  breaking/new path was escalated;
- material decisions have the right human owner and propagation route.

If repository evidence demonstrates a row cleanly, report it as derived. If a
row remains uncertain, ask with evidence and cost-if-wrong. Compact composition
requires every adequacy row to be demonstrably clean; otherwise it stops.

### 5.4 Final Approval  [material]

For an explicit route, present the full spec, decision delta, queued feature
corrections, ledger entries, ADR candidates/supersession edits, and the machine
lint result. Approval binds those exact bytes. Ask:

| Option | Result |
|---|---|
| Write | Publish the exact spec transaction and approved shared changes |
| Adjust | Loop back to the relevant stage |
| Abort | Exit without writing |

For compact composition, this gate does not fire: the approved
manifest `specification_route: compact`, matching Markdown projection, clean
adequacy screen, and lint exit 0 authorize the derived write. Report the
artifact diff and that no material decision was made.

### 5.5 Write

Write `docs/plans/[slug]/specs/<id>/ce-spec.md` and `tasks.json`, then publish
the exact approved feature correction, **Resolved Project Decisions** rows, ADR
candidates, and supersession edits from scratch. Cite this spec as each shared
ledger row's origin. If any target changed after approval, stop and reassemble;
never merge unreviewed bytes into the approved transaction.

**Metrics (best-effort, optional).** After writing, append a `stage-complete` line (`stage: "spec"`) — plus any `escalation` raised this run — to `docs/plans/<slug>/.metrics.jsonl` per the `retro` skill's schema. Derive every field from data already produced, label any token figure an estimate, and **never** let this block or fail the spec. It powers `/core-engineering:ce-retro`.

### 5.6 Closing

Confirm the created paths (`ce-spec.md`, `tasks.json` under
`docs/plans/[slug]/specs/<id>/`) and any feature, ledger, or ADR updates. Then
point to the next step:

```text
Implement:  /core-engineering:ce-implement <id>
Or spec the next feature:  /core-engineering:ce-spec <next-id>
```

Do not start implementation automatically unless the user explicitly asks.
