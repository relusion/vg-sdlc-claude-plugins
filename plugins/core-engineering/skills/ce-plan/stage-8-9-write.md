# Stage 8–9 — Validate, approve, and publish

Load `${CLAUDE_SKILL_DIR}/artifact-template.md`. Build the complete candidate
from the current checkpoint; do not reconstruct the artifact contract from
memory.

## 8. Assemble the exact candidate in scratch

Before asking for final approval, re-check:

- Scope Lock, feature order, dependencies, and specification routes;
- journey, durable-state, and surface-removal closure;
- threat and interaction projections;
- selected architecture hashes and convergence, deferred rationale, or the full
  evidenced not-required screen;
- unresolved gaps, human decisions, source freshness, and
  `candidate_revision`.

If a material input changed, return to its owning stage.

Create a collision-safe scratch directory directly beneath `docs/plans/`, for
example:

```text
docs/plans/.plan-candidate-<slug>-<run-id>/
```

It must be a new regular directory with no symlink components. This direct
location lets the colocated validators resolve the repository and
`docs/plans/plans.json` exactly as they will after publication. A pre-existing
path is never reused or overwritten.

Render every proposed plan artifact there:

```text
feature-plan.md
shared-context.md
architecture-selection.json
architecture-options.md          # only when exploration produced it
threat-model.md
interaction-contract.md
features/<id>.md
plan.json
```

Also render, but do not apply, the exact `docs/plans/plans.json` registry delta.
Use one plan-directory shape even for one feature.

Candidate rules:

- write each feature exactly once with the artifact-template headings;
- persist the manifest-owned `specification_route: compact|explicit` and its
  exact human-readable projection in every feature file;
- list manifest features in ship order with resolvable relative paths;
- include current `plan_revision`, `plan_tier`, and complete
  `architecture_disposition`;
- copy the exact reviewed draft `architecture-selection.json`;
- when exploration ran, copy the exact immutable
  `architecture-options.md` bytes and retain its report hash binding;
- for `not-required`, create the template's current-schema empty-option
  `not-applicable` selection using the plan authority and rationale;
- never label a model inference, clean lint, or absent surface as human
  approval; and
- write `threat-model.md` and `interaction-contract.md` from the validated
  projections, including their assessed-negative form when applicable.

The architecture disposition records:

```text
decision, triggers, rationale, decided_by, direction, convergence
```

For required/recommended selected architecture, direction binds the exact
selection artifact, exploration id, option id/hash, authorized human decision,
and summary; convergence binds Stage 5A status, iterations, summary, and
decision refs. For not-required it records empty positive triggers,
`not-applicable`, and zero iterations.

## 8.1 Validate the exact candidate

Run selection validation first:

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/architecture-selection-lint.py" \
  docs/plans/.plan-candidate-<slug>-<run-id>/architecture-selection.json \
  --repo-root . --require-current-schema --json
```

Then run:

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/plan-lint.py" \
  docs/plans/.plan-candidate-<slug>-<run-id> \
  --require-architecture-direction --json
```

For each command:

- exit 0: record PASS and continue;
- exit 1: repair the scratch candidate and rerun; if the repair changes a
  material decision, return to its owning stage before rebuilding;
- exit 2 or no valid result: stop and report a could-not-run coverage gap.

A hard failure or could-not-run result is non-waivable. A manual/model re-check
may diagnose it but cannot substitute for exit 0.

After both pass:

1. re-read every candidate file;
2. compute a sorted manifest of `relative path → SHA-256`;
3. bind the exact proposed registry delta and its SHA-256; and
4. confirm the architecture selection/report hashes match the candidate bytes.

Any rewrite invalidates the PASS receipts and hash manifest; rerun both
validators before approval.

## 8.2 Final decision surface

Render:

1. outcome, in-scope, and non-goals;
2. the ordered feature table with value, dependencies, risk, complexity, and
   `Specification route`;
3. architecture applicability, selected option and human rationale (or
   deferred/not-required basis), comparison path, assumptions, material
   unknowns, confidence/sensitivity, and convergence;
4. journey and lifecycle closure;
5. security, interaction, compatibility, and operational obligations;
6. both deterministic PASS receipts;
7. the candidate file-hash manifest and exact registry delta;
8. every accepted exception with owner, authority, consequence, and affected
   ids; and
9. remaining coverage gaps and downstream route.

Machine PASS results and assessed clean negatives are evidence rows, not
questions.

## 8.3 Final Plan Approval `[material]`

Print:

```text
Gate N of M — Final Plan Approval
Decision owner: <product/plan authority>
Candidate: docs/plans/.plan-candidate-<slug>-<run-id>/
Candidate revision: <n>
Validation: architecture-selection PASS; plan PASS
Binding: <file-hash manifest SHA-256 + registry-delta SHA-256>
Material decisions: <ids or none>
Recommendation: Approve exact candidate for publication
If wrong: <scope/delivery consequence>
```

Offer no more than:

- **Approve exact candidate and publish** — authorize only the displayed,
  linted bytes and registry delta;
- **Adjust** — name the delta and return to its owning stage, then rebuild and
  revalidate;
- **Need evidence / route to owner** — park for the named gap;
- **Park** — stop with resumable scratch and no canonical write.

Approval is explicit and binds the exact validated byte manifest. It does not
grant implementation, release, deployment, destructive-operation,
security-acceptance, or shared-history authority. A changed candidate requires
new PASS receipts and a new Final Plan Approval.

For `not-required`, this approval binds the plan's `not-applicable`
architecture disposition; there is no earlier negative-attestation gate. For
an explored route, it does not replace the earlier human-selected architecture
option.

## 9. Publish the approved bytes

After approval, re-read scratch and require every hash to match the approved
manifest. Publish those exact bytes under `docs/plans/<slug>/` without
regeneration or semantic edits. If that target unexpectedly exists or changed,
stop and route to Stage R; never merge candidate bytes by guesswork.

Honor `docs/plans/vc-policy.md` when present; planning does not invent a
version-control policy. Apply the approved registry delta last, only after all
plan files are in their final paths.

Recompute final hashes and require exact equality with the approved candidate.
Then rerun:

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/architecture-selection-lint.py" \
  docs/plans/<slug>/architecture-selection.json \
  --repo-root . --require-current-schema --json
python3 "${CLAUDE_SKILL_DIR}/scripts/plan-lint.py" \
  docs/plans/<slug>/ --require-architecture-direction --json
```

These post-publication runs are drift checks, not the first validation:

- exit 0: publication is valid;
- exit 1: stop and report a publication-integrity failure; do not silently
  repair approved meaning;
- exit 2 or invalid output: stop and report could-not-validate.

Never claim a valid written plan unless pre-approval and post-publication runs
both passed and the final byte manifest matches.

Delete only the exact candidate scratch after all checks pass. If cleanup
fails, report the residual path without invalidating the already-verified
canonical bytes.

## 9.1 Handoff

Report:

- written files and `plan_revision`;
- selected direction/disposition and comparison artifact path;
- feature order and specification routes;
- pre-approval and post-publication validator results;
- approved/final hash equality;
- assumptions, coverage gaps, and remaining risks; and
- next command.

Route:

- selected required/recommended direction without a current accepted
  architecture package → `/core-engineering:ce-architecture <slug>`;
- explicit specification feature → `/core-engineering:ce-spec <slug>/<id>`;
- compact specification feature → `/core-engineering:ce-implement <slug>/<id>`
  (implementation composes and lints the compact spec before code);
- plan-quality review when requested → `/core-engineering:ce-plan-audit <slug>`.

Do not invoke the next write-capable workflow implicitly.
