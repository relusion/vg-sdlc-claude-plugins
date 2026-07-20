# Feature-Spec Workflow — Stages 0–1: Frame the Feature and Resolve Unknowns

Stage file for the `spec` skill. The orchestrator is `SKILL.md` — read it first for the Execution Contract, Scope Lock, Tiered HITL, ADR rules, and the Mechanical Lint Gate. Load this file when you begin Stage 0.

**Next:** when Stage 1 is complete, load `${CLAUDE_SKILL_DIR}/stage-2-3-testable-design.md`.

---

## Stage 0 — Frame the Feature

### 0.1 Locate and Load

Resolve the plan directory via `docs/plans/plans.json`. If the feature id is
qualified (`<plan-slug>/<id>`), use the named plan; if unqualified, find the
plan whose `features/<id>.md` exists — if more than one matches, ask the human
which. Load `features/<id>.md`, `shared-context.md`, `feature-plan.md`,
`plan.json`, and the project docs listed in `shared-context.md`.

Read this plan's `relates_to` (from `plan.json`). For every related sibling
plan, also load its `shared-context.md` — its Resolved Project Decisions ledger
becomes part of the input set for Stage 1.2.

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

First check the **Resolved Project Decisions** ledger — both this plan's (in its
`shared-context.md`) **and** the ledgers of every plan in `relates_to`. If an
unknown is already resolved in any of them, do not re-research it — carry that
resolution forward and present it in Stage 1.4 as a pre-resolved default for the
human to confirm it applies here (a later feature may have a nuance, or a
sibling plan's decision may not transfer).

For every remaining unknown, use the codebase, `shared-context.md` (codebase
profile, pitfalls, project docs), and hard-dependency specs to inform a
resolution. Research is autonomous — do not present a guess as fact.

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
Records* in `SKILL.md`). New unknowns surfaced later (Stage 3) return here.
