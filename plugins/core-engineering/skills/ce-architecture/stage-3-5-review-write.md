# Architecture Workflow — Stages 3–5: Reconcile, Approve, and Write

The orchestrator is `SKILL.md`; read it first. Load this file after Stage 2.

**Next:** this is the final stage file.

## Stage 3 — Reconcile and Route

### 3.1 Run the Scope Lock reconciliation

Compare the structural model to the written plan. Stop and route to
`/core-engineering:ce-plan` Stage R if the model requires any of the following:

- a new or re-cut feature, dependency, ship order, journey, or durable noun;
- a cross-feature flow absent from the plan's Journey Map, Dependency Flow, or
  Durable-State Closure;
- a new or changed data-class, trust-boundary obligation, `TZ-NNN`, or
  `IC-NNN`; or
- a numeric NFR that would have changed decomposition but was not owned by the
  plan.

Return a paste-ready delta naming the evidence, affected feature ids, and why
the current package cannot be approved. Restore the baseline and write no final
architecture package.

### 3.2 Check coherence

Before any decision gate, verify:

- every strict schema-v2 collection uses canonical ids and exact keys;
- all context, runtime, deployment, flow, scenario, boundary, realization, and
  transition endpoints resolve;
- every selected option statement has exactly one dimension/ordinal/hash-bound
  `direction_realizations` row and every realization ref resolves;
- every plan feature has exactly one mapping entry and each structural row's
  `feature_ids` equals the reverse feature mapping;
- every durable noun, plan journey, architecture-determining NFR, `TZ-NNN`,
  `IC-NNN`, decision, ADR, and trigger-conditional dimension has exact closure
  or a typed gap;
- transition applicability follows the exact selected
  `migration_and_evolution` commitments, with explicit absence represented by
  `not-applicable` coverage and realizations rather than a no-op transition;
- each trust boundary's crossing flows exactly match the explicitly opposite
  producer/consumer side assignments in canonical flow order;
- deployments include source-backed topology fields and evidence selectors;
- dynamic steps are ordered and their alternate paths resolve;
- each numeric quality target occurs literally in its cited source;
- coverage, typed gaps, and readiness agree, with no material or
  specification-blocking open gap in a reviewable package;
- exactly the four required projection registrations are ordered and hashable;
  and
- deterministic render output equals the registered Markdown/Mermaid bytes.

### 3.3 Classify decisions and gaps

Classify each unresolved item:

- **material architecture decision:** technology/platform choice, one-way data
  choice, cross-feature protocol, security boundary, deployment topology, or a
  choice with wide blast radius;
- **routine synthesis:** naming, diagram layout, or a direct re-projection of an
  accepted source; or
- **typed gap:** evidence or authority is unavailable. Record dimension, type,
  impact, materiality, owner, next action, closure criterion, blocking stage,
  related refs, and evidence.

### 3.4 Material Architecture Decisions `[material, conditional]`

One named gate fires for each material choice that remains but does not change
the plan boundary. Lead with **What needs your decision**. Show the evidence,
options with consequences, recommendation, reversibility, and cost-if-wrong.
Never bundle unrelated choices into one approval; if a candidate splits,
refresh the remaining gate manifest and present each choice separately.

| Option | Consequence |
|---|---|
| **Accept a dominant recommendation** | Record the human choice and continue; an ADR-worthy cross-feature choice must already have or receive an accepted ADR before final approval. |
| **Route the fork to `/core-engineering:ce-decide`** | Stop with the exact option set and resume only from the human decision; the scorecard does not mutate this package. |
| **Adjust the model/evidence** | Return to Stage 1 or 2; no final package is written. |
| **Park** | Restore the baseline and stop until evidence or authority exists. |

Never bundle multiple unrelated material choices under one approval.

## Stage 4 — Assemble and Validate

### 4.1 Assemble in scratch

Create a uniquely named temporary directory with `mktemp -d`, verify that its
resolved path is outside the repository, and assemble schema v2 using
`${CLAUDE_SKILL_DIR}/artifact-template.md`. Retain that exact resolved path and
remove only that owned temporary directory on every terminal exit.

Author only `architecture.json`. Write it through
`${CLAUDE_SKILL_DIR}/scripts/scratch-write.py` with a fresh single-quoted
heredoc delimiter that no JSON line equals. Never splice evidence into shell
arguments or executable shell syntax, and do not loosen the repository write
lease:

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/scratch-write.py" \
  "<exact-scratch-dir>" "architecture.json" <<'CE_ARCH_<fresh-128-bit-hex>'
<semantic schema-v2 JSON; shell metacharacters remain literal in this quoted body>
CE_ARCH_<same-fresh-128-bit-hex>
```

Register the four required projections with pending hashes, then invoke the
bundled renderer to generate the Markdown/Mermaid bytes, populate their hashes,
normalize the pending review posture, and populate
`approval.review_payload_sha256`:

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/architecture-render.py" render \
  "<exact-scratch-dir>/architecture.json" \
  --output-dir "<exact-scratch-dir>" --finalize-review --json
```

A nonzero writer/renderer exit leaves the package unreviewable. Correct the
semantic JSON and rerun from a clean owned scratch directory; never hand-edit a
projection. Verify the directory contains `architecture.json`, the four
required regular non-symlink projections, and no other entry.

Prove the assembled package still equals the deterministic projection before
lint:

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/architecture-render.py" check \
  "<exact-scratch-dir>" --json
```

A nonzero check is a package failure; return to the semantic JSON and rerender.

Set:

- `$schema: urn:vg-sdlc:ce-architecture:architecture:v2`,
  `schema_version: 2`, and the exact generator identity/version;
- `architecture_revision: 1`, or prior revision + 1;
- `source_plan_revision` from the required current `plan.json`;
- `lifecycle_status: proposed`;
- `baseline_status: accepted-for-specification` when no gap remains, otherwise
  `accepted-for-specification-with-gaps` only for non-material,
  non-specification-blocking gaps;
- computed `readiness: ready|ready-with-gaps`; and
- canonical pending approval fields, null receipt, and the renderer-produced
  review payload digest.

The scratch package is review material, not a repository artifact.

When the invalid-package recovery gate approved a reset, also include exactly:

```json
"revision_reset": {
  "reason": "<human-approved non-empty reason>",
  "recorded_by": "human",
  "gate": "Invalid Architecture Package Recovery"
}
```

Do not include `revision_reset` for an absent, valid, stale, or invalid package
whose prior revision remains readable.

### 4.2 Run architecture-lint

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/architecture-lint.py" <scratch-dir> \
  --repo-root . --allow-proposed --json
```

- **exit 0:** mark structural checklist rows machine-verified;
- **exit 1:** render every hard failure, return to its owning stage, rebuild the
  scratch package, and re-run; do not offer final approval;
- **exit 2:** the directory or `architecture.json` is missing, unreadable, or
  unparseable. Treat this as an invalid scratch package, repair it, and re-run;
  do not offer final approval.
- **command unavailable / no result:** state `architecture-lint did not run`,
  use Stage 3.2 only to diagnose the package, restore the baseline, and park.
  The bundled publisher also requires the linter, so manual review cannot turn
  this state into a publishable PASS. Never call this a lint PASS.

### 4.3 Render the review package

Show:

1. architecture purpose, scope, non-goals, and evidence boundary;
2. every selected-direction commitment and its realization refs;
3. context, runtime, deployment, dynamic, transition, data/integration,
   trust/security/contract, quality, and operations tables;
4. deterministic diagrams as secondary projections;
5. accepted decisions/ADRs, questions, assumptions, risks, typed gaps, and
   validation routes;
6. complete plan-feature traceability and coverage/readiness; and
7. the passing lint result, exact review payload digest, and registered
   projection hashes.

## Stage 5 — Final Approval and Publish

### 5.1 Final Architecture Approval `[material]`

Print `Gate N of M — Final Architecture Approval` using the computed gate count.
Restore the deny-only baseline immediately before yielding this gate; no write
authority remains active while the human reviews the package.
Render What needs your decision first: inferred structural rows, non-material
gaps, and any explicit override. Show the proposed human approval authority,
the durable approval reference that will be recorded, the exact
`baseline_status`, the review payload digest, the receipt-hash plan, and all
four projection paths/hashes. Then present the four final options defined
in `SKILL.md`.

`Approve & publish` is permitted only when:

- no material decision or structural conflict remains;
- readiness is `ready` or `ready-with-gaps`, never `blocked`;
- every accepted material cross-feature decision has an accepted ADR when
  ADR-worthy;
- every selected commitment is closed and all non-material gaps are typed,
  actionable, mapped, and reflected by
  `accepted-for-specification-with-gaps`;
- lint passed; and
- the exact five target paths, final lifecycle/baseline status,
  authority/reference, publisher flags, digest plan, and bounded hidden
  transaction scope under `docs/plans/<slug>/.architecture-publish-*` are shown.

### 5.2 Publish transactionally

Do not edit the scratch package or destination after approval. On **Approve &
publish**, revalidate the registered slug/path, rescan
`.architecture-publish-*` siblings, and reacquire the exact ce-architecture
lease from `SKILL.md`. If any of those checks changed, refuse the old approval
and return to the owning recovery/gate path. Then invoke:

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/architecture-publish.py" <scratch-dir> \
  --repo-root . --plan-slug <validated-slug> \
  --publish-status \
  <accepted-for-specification|accepted-for-specification-with-gaps> \
  --recorded-by "<reviewed-human-identity-or-role>" \
  --approval-authority "<reviewed-human-authority>" \
  --approval-reference "<reviewed-durable-reference>" --json
```

The helper revalidates the exact schema-v2 `proposed`/pending review package and
recomputes projection hashes and `review_payload_sha256`. It snapshots the
bytes, changes only `lifecycle_status` to `published` plus the reviewed
approval decision, recorded-by/time, authority, reference, and receipt digest
in a same-parent stage, lints the stage, swaps it into the canonical path, and
lints again. `baseline_status` and all projection bytes remain identical to
review. Markdown bytes must remain identical to review. For a revision it
preserves the prior revision sequence and rolls back a detected final-lint or
filesystem failure.

Use optional `--approval-time <reviewed-RFC3339-UTC>` only when the gate
reviewed that exact time; otherwise the publisher records current UTC. The gate
must show the exact `recorded_by`, authority, and reference values before
approval.

Add `--allow-extra-cleanup` only when the final gate listed every unexpected
existing entry and the human explicitly approved its removal. Add
`--accept-human-approved-reset` only when the separate recovery gate approved
the exact `revision_reset` record. A publisher refusal is not permission to
hand-edit or bypass it:

- exit 0: publication and final lint succeeded. Surface any retained-backup
  cleanup warning and park further architecture publication until an operator
  resolves that exact hidden path;
- exit 1: publication was refused or the prior state was rolled back. Show the
  structured reason and return to the owning stage/gate; and
- exit 2: safe completion or rollback could not be proven. Restore the lease
  baseline, show the transaction paths and rollback state, and park for human
  recovery.

The publisher serializes runs with an exclusive `.architecture-publish-lock`.
The swap uses two same-filesystem renames and is transactional with rollback
for detected failures, but it is not crash-atomic. A process death can leave
the lock or an orphan stage/backup/rejected path. The next run refuses while
any unowned `.architecture-publish-*` sibling exists; inventory it and require
a human recovery decision. Never silently delete an orphan, break a live lock,
or assume a fresh revision history.

### 5.3 Close and hand off

Restore the deny-only write baseline with:

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/write-lease.py" \
  --restore-baseline --root .
```

Then report:

```text
Architecture written: docs/plans/<slug>/architecture/
Lifecycle:            published
Baseline:             accepted-for-specification | accepted-for-specification-with-gaps
Readiness:            ready | ready-with-gaps
Plan revision:        <n>
Architecture revision:<n>
Approval authority:   <human authority>
Approval reference:   <durable reference>
Receipt SHA-256:       <verified digest>
Lint:                 PASS
Coverage gaps:        <n>
Next: /core-engineering:ce-spec <slug>/<first-feature-id>
```

The package is architecture context, not permission to implement, release, or
deploy.
