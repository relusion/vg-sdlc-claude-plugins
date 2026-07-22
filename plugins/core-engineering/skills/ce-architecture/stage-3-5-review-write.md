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

- component, relationship, node, flow, and quality ids are unique;
- all relationship/flow endpoints resolve;
- every plan feature has exactly one mapping entry;
- every feature/`TZ-NNN`/`IC-NNN`/ADR reference resolves, and complete coverage
  re-projects every plan-owned durable noun and TZ/IC id;
- deployment mappings reference known components and nodes;
- every deployment node has exact evidence selectors and a reviewed normalized
  derivation for its name and environment;
- each numeric quality target occurs in its cited source;
- every required coverage dimension is dispositioned; and
- every model row and its required references appear together in the
  appropriate authoritative Markdown table, not only in prose or Mermaid.

### 3.3 Classify decisions and gaps

Classify each unresolved item:

- **material architecture decision:** technology/platform choice, one-way data
  choice, cross-feature protocol, security boundary, deployment topology, or a
  choice with wide blast radius;
- **routine synthesis:** naming, diagram layout, or a direct re-projection of an
  accepted source; or
- **coverage gap:** evidence is unavailable. Mark material vs non-material and
  explain the cost of being wrong.

### 3.4 Material Architecture Decisions `[material, conditional]`

One named gate fires for each material choice that remains but does not change
the plan boundary. Lead with **What needs your decision**. Show the evidence,
options with consequences, recommendation, reversibility, and cost-if-wrong.
Never bundle unrelated choices into one approval; if a candidate splits,
recompute the manifest through Scope Confirmation first.

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
resolved path is outside the repository, and render the five files using
`${CLAUDE_SKILL_DIR}/artifact-template.md`. Retain that exact resolved path and
remove only that owned temporary directory on every terminal exit. Because the
Write/Edit guard rejects out-of-workspace targets, write each rendered file
through `${CLAUDE_SKILL_DIR}/scripts/scratch-write.py`, which accepts content
only on standard input and restricts output to the five canonical names below
the OS temporary directory. Feed it with a single-quoted heredoc delimiter
generated after evidence loading; ensure no rendered line equals that delimiter.
Never splice evidence into shell arguments or executable shell syntax, and do
not loosen the repository write lease. Set:

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/scratch-write.py" \
  "<exact-scratch-dir>" "solution-architecture.md" <<'CE_ARCH_<fresh-128-bit-hex>'
<rendered Markdown; shell metacharacters remain literal in this quoted body>
CE_ARCH_<same-fresh-128-bit-hex>
```

Repeat for each canonical filename with a fresh delimiter that no rendered
line equals. A nonzero writer exit leaves the package unreviewable: show the
error, correct the rendered input/path, and retry before lint. After all writes,
verify the directory contains exactly the five regular non-symlink files.

Set:

- `architecture_revision: 1`, or prior revision + 1;
- `source_plan_revision` from `plan.json` (legacy missing value is `1`);
- `status: proposed` and `approval.decision: pending` /
  `approval.recorded_by: pending` until the final gate; and
- the intended published status (`approved` when coverage is complete,
  otherwise `approved-with-gaps`) in the rendered review summary.

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
2. component/relationship, deployment, data/integration, and quality tables;
3. diagrams as secondary projections;
4. accepted ADRs, assumptions, risks, gaps, and validation routes;
5. plan-feature traceability; and
6. the passing lint result.

## Stage 5 — Final Approval and Publish

### 5.1 Final Architecture Approval `[material]`

Print `Gate N of M — Final Architecture Approval` using the computed gate count.
Restore the deny-only baseline immediately before yielding this gate; no write
authority remains active while the human reviews the package.
Render What needs your decision first: inferred structural rows, non-material
coverage gaps, and any explicit override. Then present the four final options
defined in `SKILL.md`.

`Approve & publish` is permitted only when:

- no material decision or structural conflict remains;
- every accepted material cross-feature decision has an accepted ADR when
  ADR-worthy;
- all non-material gaps are visible and status is `approved-with-gaps`;
- lint passed; and
- the exact five target paths, final status, publisher flags, and bounded hidden
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
  --publish-status <approved|approved-with-gaps> --json
```

The helper revalidates the exact `proposed`/pending review package, snapshots
its bytes, applies only the approved `status` and `approval` JSON transition in
a same-parent stage, lints the stage, swaps it into the canonical path, and
lints again. Markdown bytes must remain identical to review. For a revision it
preserves the prior revision sequence and rolls back a detected final-lint or
filesystem failure.

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
Status:               approved | approved-with-gaps
Plan revision:        <n>
Architecture revision:<n>
Lint:                 PASS
Coverage gaps:        <n>
Next: /core-engineering:ce-spec <slug>/<first-feature-id>
```

The package is architecture context, not permission to implement, release, or
deploy.
