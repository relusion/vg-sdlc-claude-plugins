# Stage R — Revise an existing plan

Revision is a delta workflow, not a full rediscovery. Preserve unaffected
artifact bytes, stable feature ids, and accepted decisions.

## R0. Establish a valid baseline

Resolve exactly one registry-backed `docs/plans/<slug>/`. Refuse an ambiguous
target.

Before treating an architecture package as present or absent, scan for
`.architecture-publish-` lock, stage, backup, or rejected transaction state.
Such state requires explicit human recovery; never infer absence through an
incomplete publication.

Run:

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/architecture-selection-lint.py" \
  docs/plans/<slug>/architecture-selection.json \
  --repo-root . --require-current-schema --json
python3 "${CLAUDE_SKILL_DIR}/scripts/plan-lint.py" \
  docs/plans/<slug> --require-architecture-direction --json
```

Exit 1 or 2 is a baseline defect/coverage gap. Diagnose and route it; do not
silently build a revision on structurally invalid state.

Load the current plan, feature files, projections, selection/comparison,
accepted architecture package if present, specs, VC policy, and relevant
repository evidence.

## R1. Frame the delta

Record:

```text
Revision Delta
Source plan revision: <n>
Requested outcome: <one sentence>
Trigger: <user request or Back-Edge Summary>
In scope: <changed behavior/features>
Held constant: <unaffected scope and decisions>
Evidence: <paths/checks>
Potentially invalidated: <plan, architecture, spec, implementation ids>
```

Ask only when the delta changes a human-owned scope, architecture, security,
compatibility, ownership, or destructive decision. Otherwise announce the
bounded revision and continue.

## R2. Determine the owning back-edge

- Outcome/non-goal/capability change → Stage 1.
- Architecture driver, constraint, criterion, source, or selected-option change
  → Stage 1A and the same iterative Architecture Direction workbench.
- Feature boundary/order/owner change under a current direction → Stage 2, then
  Stage 5A when applicable.
- Journey, lifecycle, surface, security, or interaction gap → Stage 6.
- Session-fit/specification-route change → Stage 7.
- Rendering-only defect → Stage 8–9.

A downstream spec or implementation concern does not automatically widen the
plan. Use its Back-Edge Summary and route only the smallest owning delta.

## R3. Apply the candidate delta

Rules:

- keep unaffected feature ids, files, and bytes unchanged;
- never reuse a retired feature id for different meaning;
- update hard/soft dependencies, ship order, boundary ownership, journeys,
  durable state, threat/interaction obligations, and bridges only where the
  delta requires;
- preserve the exact current architecture selection unless Stage 1A replaces
  it through explicit human selection;
- rerun Stage 5A when candidate structure changed under a selected direction;
- reassess manifest-owned `specification_route: compact|explicit` and its
  Markdown projection for touched features;
- mark affected specs/implementation evidence stale rather than editing them as
  if they remained current;
- increment `plan_revision` exactly once for the approved write.

Run the affected closure checks from Stages 4–7. Clean checks do not become
gates. Surface material exceptions under the same adaptive decision contract.

## R4. Validate and approve the revision

Assemble the complete proposed plan in a new collision-safe
`docs/plans/.plan-revision-candidate-<slug>-<run-id>/`. Copy every unaffected
file byte-for-byte and render only the approved candidate delta, incremented
`plan_revision`, and exact proposed registry delta.

Before asking for approval, run:

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/architecture-selection-lint.py" \
  docs/plans/.plan-revision-candidate-<slug>-<run-id>/architecture-selection.json \
  --repo-root . --require-current-schema --json
python3 "${CLAUDE_SKILL_DIR}/scripts/plan-lint.py" \
  docs/plans/.plan-revision-candidate-<slug>-<run-id>/ \
  --require-architecture-direction --json
```

Exit 1 requires candidate repair and another lint run; if meaning changes,
return to the owning stage. Exit 2 is non-waivable could-not-run. Only two exit
0 receipts make the candidate approvable. Re-read it and compute a sorted
relative-path/SHA-256 manifest plus the proposed registry-delta hash.

Render an exact before/after summary:

- scope and non-goal delta;
- feature add/change/retire/order delta;
- architecture selection/convergence delta or “unchanged and fresh” evidence;
- specification-route and downstream invalidation delta;
- security, interaction, compatibility, and operational consequences;
- unchanged artifacts whose bytes will be preserved;
- both deterministic PASS receipts and candidate hash manifest; and
- remaining gaps.

Print:

```text
Gate N of M — Final Plan Revision Approval
Source revision: <n>
Target revision: <n+1>
Decision owner: <authorized plan owner>
Validation: architecture-selection PASS; plan PASS
Binding: <candidate manifest SHA-256 + registry-delta SHA-256>
Recommendation: Approve exact bounded revision
If wrong: <delivery/rework consequence>
```

Offer **Approve exact candidate and publish**, **Adjust**, **Need evidence /
route to owner**, and **Park**. Approval binds the displayed, linted bytes and
registry delta, not downstream implementation or release. Any candidate change
invalidates the receipts and requires another approval.

## R5. Publish and revalidate

After approval:

1. re-read scratch and require the approved hashes;
2. publish only changed candidate files plus `plan.json`, preserving untouched
   bytes exactly;
3. publish refreshed selection/options bytes without regeneration;
4. apply the approved registry delta last;
5. require final file hashes to equal the candidate manifest;
6. rerun selection lint with `--require-current-schema` and plan lint with
   `--require-architecture-direction` as post-publication drift checks; and
7. treat exit 1 or 2 as a publication-integrity stop, never as a prompt to
   silently change approved meaning.

Delete only the exact revision-candidate scratch after both post-publication
lints return exit 0. Report changed and preserved files, approved/final hash
equality, invalidated downstream artifacts, validation results, risks, and the
next command.
