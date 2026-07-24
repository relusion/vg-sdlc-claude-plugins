# Feature-Spec Workflow — Stages 0–1: Frame the Feature and Resolve Unknowns

Stage file for the `spec` skill. The orchestrator is `SKILL.md` — read it first for the Execution Contract, Scope Lock, Tiered HITL, ADR rules, and the Mechanical Lint Gate. Load this file when you begin Stage 0.

**Next:** when Stage 1 is complete, load `${CLAUDE_SKILL_DIR}/stage-2-3-testable-design.md`.

---

## Stage 0 — Frame the Feature

### 0.1 Locate and Load

Resolve the plan directory via `docs/plans/plans.json`. If the feature id is
qualified (`<plan-slug>/<id>`), use the named registry entry. If unqualified,
match canonical `features/<id>.md` paths; if more than one matches, ask the
human which. Load the regular, non-symlink `plan.json`,
`architecture-selection.json`, `shared-context.md`, `feature-plan.md`, and
`features/<id>.md`. Read `relates_to` from `plan.json` and load each related
plan's shared decision ledger for Stage 1.2.

A missing authority, symlink, duplicate identity, or slug/id mismatch is a
planning defect. Stop and route the exact defect to
`/core-engineering:ce-plan`; never guess or manufacture it.

Run the structural gate before interpreting its architecture
disposition or loading any feature design context:

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/plan-lint.py" \
  docs/plans/<slug> --json
```

- **exit 0:** continue with the lint-validated manifest and its human-bound
  architecture direction.
- **exit 1:** stop and route the exact hard defect to
  `/core-engineering:ce-plan` Stage R. A malformed or missing required
  disposition/direction is one such defect.
- **exit 2:** stop and route to Stage R because the full plan cannot be trusted.
  Never replace the deterministic result with an inferred disposition.

Validate the exact selected-direction artifact before loading feature design
context:

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/architecture-selection-lint.py" \
  docs/plans/<slug>/architecture-selection.json \
  --json
```

Exit 1 or 2 routes to `/core-engineering:ce-plan` Stage R. A scorecard, option
hash, hard-constraint verdict, file hash, or human-selection mismatch is never
reconstructed from prose and never treated as an architecture pass.

Read the validated `architecture_disposition` before checking the package. It
has `decision: required | recommended | not-required`, a `triggers`
array, non-empty `rationale`, `decided_by: human`, and `convergence` with
`status`, non-negative `iteration_count`, `summary`, and accepted-ADR
`decision_refs`. Require every reference to resolve inside the repository to a
readable ADR recorded as accepted; otherwise stop and route the exact reference
defect to Stage R. Load the validated ADRs as binding design context. If
`decision: required` does not carry `convergence.status: converged`, stop and
route to Stage R: the plan froze without completing its required shaping pass.
The only valid combinations are required with a selected direction and
`converged`; recommended with a selected direction and `converged`, or with
both direction and convergence explicitly `deferred`; and not-required with
both direction and convergence `not-applicable`.

Before treating `architecture/` as present or absent, inventory direct children
of the plan directory whose names start with `.architecture-publish-`, without
following symlinks. Any lock, stage, backup, or rejected path means publication
may be live or may have crashed while the canonical target was temporarily
absent. Stop, list every exact path, and route to
`/core-engineering:ce-architecture <slug>` for explicit human recovery. Never
delete or consume a transaction path, and never record architecture as absent
while one remains.

Use an lstat-style namespace check: if any entry named
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
  feature-local implementation delta stays in this spec. If `baseline_status`
  is `accepted-for-specification-with-gaps`, surface every gap relevant to this
  feature and keep it unknown; never silently complete it in the spec. The package is design
  context; accepted ADRs remain the binding technical decisions.
- **exit 1:** the package is invalid or stale against the current plan. Stop
  and run `/core-engineering:ce-architecture <slug>` to revise it; never
  silently design against stale architecture.
- **exit 2:** the package could not be validated. Stop with the error and route
  to `/core-engineering:ce-architecture <slug>`; a present package is never
  silently ignored.

After that clean transaction-state scan, only lstat-confirmed
namespace absence (no entry named `architecture`) uses the disposition matrix:

| Plan decision | Missing-package disposition |
|---|---|
| `required` + convergence `converged` | Stop and route to `/core-engineering:ce-architecture <slug>`. Architecture shaping converged, but the governed current package required before specification has not been published. |
| `recommended` + selected direction + convergence `converged` | Stop and route to `/core-engineering:ce-architecture <slug>`; a selected and converged direction requires its governed package. |
| `recommended` + direction/convergence `deferred` | Continue only with `Architecture: coverage gap — recommended package explicitly deferred`, plus the exact triggers, rationale, convergence summary, and decision refs. Keep cross-feature design unknown rather than filling the gap locally. |
| `not-required` | Record `Architecture: N/A — plan disposition not-required`, plus the rationale. |

Any unknown combination is a planning defect: route to Stage R and stop. These
absence rules never bypass validation of a namespace that is actually present.

If `specs/<id>/ce-spec.md` already exists, this is a **revision**: load it, note
what changed in `features/<id>.md` since, and revise rather than overwrite.
Increment `spec_revision` at write time.

### 0.2 Enforce Dependency Order

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

Restate the bounded feature from `features/<id>.md`:

- id, title, type, description
- **Scope** and **Excluded** — the frozen boundary
- **Validation Target**
- **Open Unknowns** to resolve
- reviewer-triggers
- hard dependencies (specced/built) and soft dependencies (+ bridges)
- any bridge this feature owns
- accepted architecture mapping (components, data entities/lifecycle, flows,
  and quality scenarios), including any repository-evidence drift advisory; or
  the exact disposition-derived explicitly deferred `recommended` coverage gap
  or `not-required` N/A. Include the disposition triggers, rationale,
  convergence summary/iteration count, and decision refs

### 0.4 Frame Check

Present the Feature Frame with its evidence. If the qualified target and frozen
boundary resolve unambiguously, record them and continue without a confirmation
gate.

Ask only when identity has multiple valid matches or repository evidence makes
the boundary materially ambiguous. Print `Gate N of M — Feature boundary` and
offer the concrete candidates, **Revise in planning**, or **Abort**. Compact
composition cannot make this choice; return the evidence to an explicit spec
run.

---

## Stage 1 — Resolve Unknowns  *(Gap 1)*

### 1.1 Collect

Take every entry in the feature's `open_unknowns`. If there are none, record
"No open unknowns" and go to Stage 2.

### 1.2 Research

For a full plan, first check the **Resolved Project Decisions** ledger — both
this plan's and every `relates_to` plan's. If a resolution has the same scope
and constraints, carry it forward with its source; do not ask the human to
re-confirm it. A scope or constraint mismatch makes it a fresh decision.

For every remaining unknown, use the codebase, `shared-context.md`, and
applicable hard-dependency specs to inform a resolution. Research is autonomous
— do not present a guess as fact.

### 1.3 Draft Resolutions

For each unresolved unknown, draft 2–4 concrete options with consequences and a
recommended option. Mark it **material** only when the evidence leaves a
substantive product, boundary, adequacy, security, architecture, external-
contract, or irreversible choice. Otherwise select the dominant reversible
engineering default and cite its evidence.

### 1.4 Resolve  [tiered]

Present each material unknown as an explicit decision prompt. Resolve dominant,
reversible engineering defaults autonomously and report them in the final
decision delta; do not create a bulk approval gate.

- An applicable ledger resolution is inherited, not re-approved. Conflicting
  scope or newer evidence makes it a fresh material decision.
- A resolution that would expand Scope is a **Boundary Conflict** — handle per the Scope Lock (Stage 3.3).
- A **blocking** unknown must be resolved here. A **non-blocking** one may be deferred as a labeled **Assumption** only with explicit human sign-off.
- Compact composition stops on any material or signed-off-assumption decision.

### 1.5 Record

Log each resolution as a Resolved Decision. If a resolution is architecturally
significant and cross-feature, promote it to an ADR (see *Architecture Decision
Records* in `SKILL.md`). New unknowns surfaced later (Stage 3) return here.
