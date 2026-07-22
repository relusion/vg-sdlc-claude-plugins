# Feature-Spec Workflow — Stages 0–1: Frame the Feature and Resolve Unknowns

Stage file for the `spec` skill. The orchestrator is `SKILL.md` — read it first for the Execution Contract, Scope Lock, Tiered HITL, ADR rules, and the Mechanical Lint Gate. Load this file when you begin Stage 0.

**Next:** when Stage 1 is complete, load `${CLAUDE_SKILL_DIR}/stage-2-3-testable-design.md`.

---

## Stage 0 — Frame the Feature

### 0.1 Locate and Load

Resolve the plan directory via `docs/plans/plans.json`. If the feature id is
qualified (`<plan-slug>/<id>`), use the named registry entry. If unqualified,
match it against both full-plan `features/<id>.md` paths and the explicit
`Feature ID` in each registry-backed minimal plan; if more than one matches,
ask the human which. Do not infer a feature id from a title or directory name.

Classify the selected registered directory as exactly one shape:

- **Full plan:** `plan.json` and the normal `features/<id>.md`,
  `shared-context.md`, and `feature-plan.md` inputs exist. Load those inputs and
  the project docs listed in `shared-context.md`. Read `relates_to` from
  `plan.json`; for every related sibling plan, also load its
  `shared-context.md` ledger for Stage 1.2.
- **Single-feature minimal plan:** `plan.json`, `architecture-selection.json`, `shared-context.md`,
  `threat-model.md`, `interaction-contract.md`, and `features/` are absent, and
  a regular, non-symlink `feature-plan.md` is the sole plan authority. Require
  exactly one `## 4. Single Feature` block, one `Feature ID: <id>` field, and
  one `Run: /core-engineering:ce-spec <slug>/<id>` line. The two ids must match
  each other, the registered slug, and any invocation id. Set
  `plan_mode: single-feature-minimal` and load Scope, Excluded, Open Unknowns,
  Validation Target, Project Context, Codebase Profile, Notes, and the required
  inline `### Security Projection` from that file. Require exactly one
  `security_obligations` entry for the same feature id and preserve its
  `TZ-NNN` ids/surface kinds or explicit empty assessed negative. A missing,
  malformed, mismatched, or materially stale projection routes to planning.
  It has no sibling ledgers or `relates_to` inputs.

A missing or non-regular authority file, a mixed shape, duplicate identity
fields, or any slug/id mismatch is not a minimal-plan shortcut. Stop and route
the exact defect to `/core-engineering:ce-plan`; never guess or manufacture the
missing full-plan files.

For a full plan, run the structural gate before interpreting its architecture
disposition or loading any feature design context:

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/plan-lint.py" \
  docs/plans/<slug> --require-architecture-direction --json
```

- **exit 0:** continue with the lint-validated manifest and its human-bound
  architecture direction.
- **exit 1:** stop and route the exact hard defect to
  `/core-engineering:ce-plan` Stage R. A malformed *present* disposition is one
  such defect; under the consumer flag, legacy `A12`/`A13` gaps are defects too.
- **exit 2:** stop and route to Stage R because the full plan cannot be trusted.
  Never replace the deterministic result with an inferred disposition.

Validate the exact selected-direction artifact before loading feature design
context:

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/architecture-selection-lint.py" \
  docs/plans/<slug>/architecture-selection.json --json
```

Exit 1 or 2 routes to `/core-engineering:ce-plan` Stage R. A scorecard, option
hash, hard-constraint verdict, file hash, or human-selection mismatch is never
reconstructed from prose and never treated as an architecture pass.

Read the validated `architecture_disposition` before checking the package. It
has `decision: required | recommended | not-required | waived`, a `triggers`
array, non-empty `rationale`, `decided_by: human`, and `convergence` with
`status`, non-negative `iteration_count`, `summary`, and accepted-ADR
`decision_refs`. Require every reference to resolve inside the repository to a
readable ADR recorded as accepted; otherwise stop and route the exact reference
defect to Stage R. Load the validated ADRs as binding design context. If
`decision: required` does not carry `convergence.status: converged`, stop and
route to Stage R: the plan froze without completing its required shaping pass.

Before treating `architecture/` as present or absent, inventory direct children
of the plan directory whose names start with `.architecture-publish-`, without
following symlinks. Any lock, stage, backup, or rejected path means publication
may be live or may have crashed while the canonical target was temporarily
absent. Stop, list every exact path, and route to
`/core-engineering:ce-architecture <slug>` for explicit human recovery. Never
delete or consume a transaction path, and never record architecture as absent
while one remains.

In `single-feature-minimal` mode, the architecture seam is `N/A by
construction`. Use lstat-style namespace occupancy: if any entry named
`architecture` is present (including a broken symlink, symlinked directory, or
non-directory), stop and route to
`/core-engineering:ce-architecture <slug>` for explicit obsolete-package
disposition; never ignore or consume it. Otherwise record
`Architecture: N/A — single-feature minimal plan` and skip package validation.

For a full plan, use an lstat-style namespace check: if any entry named
`architecture` occupies that path — including a broken symlink, a symlinked
directory, a non-directory, or a partial directory lacking
`architecture.json` — send that exact path to the consumer validator before
using or classifying it:

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/architecture-lint.py" \
  docs/plans/<slug>/architecture --repo-root . --consumer --json
```

- **exit 0:** load `architecture.json` and the four Markdown projections. Carry
  this feature's mapped components, data entities/lifecycle dispositions,
  integration flows, and quality scenarios into the Feature Frame and Stage 3
  design. Surface every `repository evidence drift` advisory and re-check its
  affected claim against the current code; expected implementation drift does
  not by itself invalidate the plan-owned baseline. If current code contradicts
  a cross-feature boundary, route to `/core-engineering:ce-architecture`; a
  feature-local implementation delta stays in this spec. If status is
  `approved-with-gaps`, surface every gap relevant to this feature and keep it
  unknown; never silently complete it in the spec. The package is design
  context; accepted ADRs remain the binding technical decisions.
- **exit 1:** the package is invalid or stale against the current plan. Stop
  and run `/core-engineering:ce-architecture <slug>` to revise it; never
  silently design against stale architecture.
- **exit 2:** the package could not be validated. Stop with the error and route
  to `/core-engineering:ce-architecture <slug>`; a present package is never
  silently ignored.

For a full plan, after that clean transaction-state scan, only lstat-confirmed
namespace absence (no entry named `architecture`) uses the disposition matrix:

| Plan decision | Missing-package disposition |
|---|---|
| `required` + convergence `converged` | Stop and route to `/core-engineering:ce-architecture <slug>`. Architecture shaping converged, but the governed current package required before specification has not been published. |
| `recommended` | Continue only with `Architecture: coverage gap — recommended package absent`, plus the exact triggers, rationale, convergence summary, and decision refs. Keep cross-feature design unknown rather than filling the gap locally. |
| `not-required` | Record `Architecture: N/A — plan disposition not-required`, plus the rationale. |
| `waived` | Continue only with `Architecture: waived by human`, the exact rationale, triggers, convergence summary, and residual risk. A waiver is not architecture or authority to invent it. |

Any unknown combination is a planning defect: route to Stage R and stop. These
absence rules never bypass validation of a namespace that is actually present.

If `specs/<id>/ce-spec.md` already exists, this is a **revision**: load it, note
what changed in `features/<id>.md` or the minimal plan's Single Feature block
since, and revise rather than overwrite. Increment `spec_revision` at write
time.

### 0.2 Enforce Dependency Order

For `plan_mode: single-feature-minimal`, record
`Dependency Order: N/A — sizing-attested single feature` and continue to Stage
0.3. Do not invent a dependency check against absent files. If repository
evidence reveals a dependency or another planned feature is required, the
minimal-plan premise is false: route to `/core-engineering:ce-plan` and stop.

For a full plan, enforce the order below.

For each **hard** dependency of this feature, resolve the id first:

- **Unqualified** (e.g. `02-foo`) — refers to a feature in the current plan.
- **Qualified** (e.g. `customer-portal/02-foo`) — refers to a feature in another plan; look the plan up via the registry.

Then check it:

- If `specs/<dep>/ce-spec.md` exists (in the resolved plan's directory) → the dependency is specced. Use it as the real interface.
- Else, check the codebase for the dependency's declared surfaces (from its feature file). If present → treat it as built; design against the real code.
- Else → the dependency is neither specced nor built.

If any hard dependency is neither specced nor built, **stop**:

```text
Cannot spec <id>: hard dependency <dep> is not yet specified or built.
Hard dependencies must be specified first. Run: /core-engineering:ce-spec <dep>
```

If a dependency's build state is genuinely unclear, ask the human (material) — do
not assume. **Soft** dependencies are exempt; they are handled through the plan's
bridges.

### 0.3 Build the Feature Frame

Restate the bounded feature from `features/<id>.md`, or from the sole Single
Feature block when `plan_mode: single-feature-minimal`:

- id, title, type, description
- **Scope** and **Excluded** — the frozen boundary
- **Validation Target**
- **Open Unknowns** to resolve
- reviewer-triggers
- hard dependencies (specced/built) and soft dependencies (+ bridges)
- any bridge this feature owns
- accepted architecture mapping (components, data entities/lifecycle, flows,
  and quality scenarios), including any repository-evidence drift advisory; or
  the exact disposition-derived `recommended` coverage gap, `not-required` N/A,
  or human waiver. Include the disposition triggers, rationale, convergence
  summary/iteration count, and decision refs. In minimal mode record
  architecture, dependencies, bridges, Journey Map, and cross-feature
  obligations as `N/A by construction`

### 0.4 Frame Checkpoint  [material]

Present the Feature Frame. Confirm with the human:

| Option | Result |
|---|---|
| Proceed | Continue to Stage 1 |
| Wrong feature | Re-select the feature |
| Boundary needs revision first | Escalate to `/core-engineering:ce-plan`; stop |
| Abort | Exit without writing |

---

## Stage 1 — Resolve Unknowns  *(Gap 1)*

### 1.1 Collect

Take every entry in the feature's `open_unknowns`. If there are none, record
"No open unknowns" and go to Stage 2.

### 1.2 Research

For a full plan, first check the **Resolved Project Decisions** ledger — both
this plan's (in its `shared-context.md`) **and** the ledgers of every plan in
`relates_to`. If an unknown is already resolved in any of them, do not
re-research it — carry that resolution forward and present it in Stage 1.4 as a
pre-resolved default for the human to confirm it applies here (a later feature
may have a nuance, or a sibling plan's decision may not transfer).

For `plan_mode: single-feature-minimal`, there is no shared ledger. Use only the
Project Context, Codebase Profile, and Notes in `feature-plan.md` as recorded
plan context. Do not create `shared-context.md` from inside this workflow.

For every remaining unknown, use the codebase, the available plan context (the
full plan's `shared-context.md`, or the minimal plan's inline Project Context,
Codebase Profile, and Notes), and any applicable full-plan hard-dependency specs
to inform a resolution. Research is autonomous — do not present a guess as
fact.

### 1.3 Draft Resolutions

For each unknown, draft 2–4 concrete options, each with its consequence, and a
recommended option with reasoning. Tag each **material** or **routine**.

### 1.4 Resolve  [tiered]

Present material unknowns as explicit decision prompts; list routine ones for
bulk approve-with-veto. The human resolves each.

- An unknown already in the ledger is a **routine** confirmation — unless the human flags that this feature differs, in which case treat it as a fresh decision.
- A resolution that would expand Scope is a **Boundary Conflict** — handle per the Scope Lock (Stage 3.3).
- A **blocking** unknown must be resolved here. A **non-blocking** one may be deferred as a labeled **Assumption** only with explicit human sign-off.

### 1.5 Record

Log each resolution as a Resolved Decision. If a resolution is architecturally
significant and cross-feature, promote it to an ADR (see *Architecture Decision
Records* in `SKILL.md`). In minimal mode, any cross-feature resolution first
invalidates the plan shape and routes to planning; do not use ADR propagation to
bypass that boundary. New unknowns surfaced later (Stage 3) return here.
