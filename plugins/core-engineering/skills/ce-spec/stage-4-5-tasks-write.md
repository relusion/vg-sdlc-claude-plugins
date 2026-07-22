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

Ordering or granularity that affects risk is material; mechanical splits are
routine. The human approves the task list.

---

## Stage 5 — Assemble, Triage, Approve, Write

### 5.1 Assemble

Assemble `ce-spec.md` + `tasks.json` per **`${CLAUDE_SKILL_DIR}/artifact-template.md`** in this skill's directory — do not reconstruct either file's format from memory.

### 5.1.5 Mechanical Lint  *(supplement — does not replace 5.3)*

Before the human checklist, run the **Mechanical Lint Gate** (defined in
`SKILL.md` → *Mechanical Lint Gate*). The final artifact is not written until
Stage 5.5 (Execution Contract item 1), so write the assembled `ce-spec.md` +
`tasks.json` to a **scratch** directory and lint that. Honor the gate's
disposition:

- **PASS** → annotate the items it covers in 5.3 as **`[machine-verified]`** (they stay in the checklist).
- **FAIL** → a **material finding**; do not reach Final Approval (5.4) on an unacknowledged FAIL.
- **Could-not-run** → fall back to full manual self-attestation in 5.3 and **say so loudly**.

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
Never sync silently, and never push a feature-local choice into shared context.

For `plan_mode: single-feature-minimal`, only the Feature-local bucket may
complete here. There is no `shared-context.md` ledger to append to, and this
workflow must not create one. Any cross-feature or plan-error bucket disproves
the minimal shape: route to `/core-engineering:ce-plan` and stop; an ADR does not
bypass that structural escalation.

### 5.3 Validation Checklist Before Writing

The **consolidated final gate**, run on the **assembled, frozen `ce-spec.md`** — not a restatement of earlier gates. Stage 5.1 assembles the artifact *after* propagation triage (5.2), and the Stage 3.3 / 4.3 back-edges can mutate the spec after Stages 2–4 validated it, so several checks below are a deliberate **re-verification on the frozen artifact** (re-confirming Stages 2.3, 3.1/3.3, and 4.3 against what will be written). Do not rubber-stamp: if any item fails, return to the stage that owns it. All must pass. Items (or clauses) marked **`[machine-verified: H#]`** are *also* mechanically enforced by `spec-lint.py` at 5.1.5 (the named hard check) — the marker means the lint **supplements** that item; it stays a checklist item and the human still owns the surrounding judgment.

- [ ] Feature framed; frozen boundary recorded.
- [ ] Every hard dependency is specced or built; minimal mode records
  `N/A — sizing-attested single feature` and has escalated any discovered
  dependency to planning.
- [ ] Every Open Unknown is resolved, or recorded as a signed-off Assumption.
- [ ] Every Scope item → ≥ 1 acceptance criterion → ≥ 1 test case → ≥ 1 task.
- [ ] No orphan task **[machine-verified: H3]**; no criterion or test case outside the boundary — boundary judgment stays the human's.
- [ ] Every reviewer-trigger is addressed by a criterion.
- [ ] A feature exposing a surface with an Interface Foundation carries conformance criteria binding it to the foundation's ADR (`auto` / `manual:harness-gap`); only genuine taste is left `manual:judgment`.
- [ ] The design names real files and real dependency interfaces.
- [ ] The design conforms to every applicable accepted ADR (or an ADR conflict was escalated).
- [ ] Every Boundary Conflict is either fixed-and-logged or escalated.
- [ ] Every judgment call is logged with `decided_by: human`.
- [ ] Architecturally-significant, cross-feature decisions are promoted to ADRs (or confirmed feature-local).
- [ ] Every resolved decision is triaged for propagation; approved ledger entries are queued.
- [ ] Every test case is tagged `auto`, `manual:harness-gap`, or `manual:judgment` **[machine-verified: H2]**; each `manual` case has a reason and a usable check script (human).
- [ ] Every test case carries a `modality`; `manual` modality pairs with `manual:judgment`. **[machine-verified: H2]**
- [ ] Every journey step this feature owns is covered by ≥ 1 test case carrying that step's modality; minimal mode records Journey Map coverage `N/A by construction`.
- [ ] Every SHARED shape this feature modifies carries a `shared-shape-modify` block (consumers enumerated, each `additive`/`breaking`); every `breaking` one is escalated as a Boundary Conflict, or the spec records `Shared-Shape Reconciliation: N/A` (§3.5).
- [ ] Every cross-feature flow this design realizes is traced by a plan Journey Map row, or a new untraced flow was escalated as a Boundary Conflict, or the spec records `Cross-Feature Flow: N/A` (§3.6) — flow judgment stays the human's; minimal mode must record `N/A by construction` or escalate.
- [ ] Every governance reciprocal the plan's Stage 6.3 closure dispositions `owned-by:` this feature (`retain` / `export` / `erase`) is bound by ≥ 1 acceptance criterion and ≥ 1 test case (§2.1); minimal mode records this row `N/A by construction`.
- [ ] Every `TZ-NNN` the full plan's `threat-model.md` or minimal plan's inline Security Projection assigns this feature is bound by ≥ 1 acceptance criterion marked `[SECURITY: TZ-NNN]` **[machine-verified: H5]** (H5 checks the marker; an N/A feature has no threat-ids) **and** proven by ≥ 1 test case (human — the per-AC test-case rule, only advisorily A2) — or the obligation is consent-excluded in the plan (autonomous: parked). Minimal mode may record an explicit empty assessed negative; it never infers N/A from one-feature shape. Whether the security criterion is *substantively adequate* stays the human's.
- [ ] Every `IC-NNN` the plan's `interaction-contract.md` assigns this feature is bound by ≥ 1 acceptance criterion marked `[CONTRACT: IC-NNN]` **and** proven by ≥ 1 test case (**human/agent-attested — no lint**; behavioural-protocol invariants and NFRs are un-derivable from markdown, like §3.5/§3.6) — or the obligation is consent-excluded in the plan (autonomous: parked). Minimal mode records plan-owned interaction obligations `N/A by construction`. Whether the interaction criterion is *substantively adequate* stays the human's.

### 5.4 Final Approval  [material]

Present the full spec, plus any queued ledger entries and new ADRs. Minimal mode
must show `Ledger entries: N/A — no shared-context.md` rather than inventing a
queue. Ask:

| Option | Result |
|---|---|
| Write | Write the spec and append approved ledger entries |
| Adjust | Loop back to the relevant stage |
| Abort | Exit without writing |

### 5.5 Write

Write `docs/plans/[slug]/specs/<id>/ce-spec.md` and `tasks.json`. For a full
plan, append each approved entry to the **Resolved Project Decisions** ledger
in `shared-context.md`, citing this spec as the origin. For
`plan_mode: single-feature-minimal`, write the same normal spec outputs and no
ledger file; any approved local Boundary Conflict is already recorded in the
sole `feature-plan.md` authority.

**Metrics (best-effort, optional).** After writing, append a `stage-complete` line (`stage: "spec"`) — plus any `escalation` raised this run — to `docs/plans/<slug>/.metrics.jsonl` per the `retro` skill's schema. Derive every field from data already produced, label any token figure an estimate, and **never** let this block or fail the spec. It powers `/core-engineering:ce-retro`.

### 5.6 Closing

Confirm the created paths (`ce-spec.md`, `tasks.json` under `docs/plans/[slug]/specs/<id>/`) and any ledger or ADR updates — and, if a Boundary Conflict edited `features/<id>.md` or the minimal plan's Single Feature block, or ADRs were created, note those too. Then point to the next step:

```text
Implement:  /core-engineering:ce-implement <id>
Or spec the next feature:  /core-engineering:ce-spec <next-id>
```

Do not start implementation automatically unless the user explicitly asks.
