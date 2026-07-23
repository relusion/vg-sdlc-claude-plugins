# Stage 4–7 — Validate the candidate and surface exceptions

These stages validate one candidate plan. Clean checks are recorded, not turned
into confirmation prompts. Only a material exception or missing authority opens
a gate.

## Stage 4 — Derive plan tier

Use one canonical plan-directory artifact for every feature count. Do not create
a special one-file plan mode.

Set `plan_tier`:

- `light` when scope is small, boundaries and verification are unambiguous, no
  feature is high risk, and architecture is not required;
- `standard` otherwise.

Tier changes presentation depth, not artifact integrity, architecture authority,
security handling, or deterministic linting. Record the evidence for the
derived tier. Do not ask the human to approve a mechanical size label.

## Stage 5 — Candidate integrity

Render a compact candidate summary:

| Order | Feature | Value/observable | Hard dependencies | Risk | Complexity | Specification route |
|---|---|---|---|---|---|---|

Then validate:

1. Scope Lock coverage and non-goals;
2. capability and journey coverage;
3. unique feature ids, boundary owners, and ship order;
4. dependency resolution, direction, and cycles;
5. explicit public/data/integration/operational surfaces;
6. concrete validation targets and specification-route eligibility;
7. assumptions, unknowns, and accepted decisions;
8. consistency with the selected architecture direction or recorded
   disposition.

Repair local inconsistencies that do not change a human-owned decision. Do not
open a generic Candidate Review gate.

When architecture was selected, load
`${CLAUDE_SKILL_DIR}/stage-5a-architecture-convergence.md` now and run its
read-only shape pass before Stage 6. A clean result returns here without a
consent gate.

## Stage 6 — Reachability and lifecycle closure

### 6.1 Journey and surface trace

For every user, consumer, migration, and operational journey, trace:

- entry point and actor;
- feature-by-feature path in ship order;
- public/data/integration surface at each crossing;
- observable success and failure behavior;
- temporary bridge and the named later feature that removes it;
- shipped value at every intermediate release cut.

Every public interaction surface is either delivered and exercised by a
journey, explicitly internal with evidence, or excluded with a human-owned
reason. A navigation shell, schema, endpoint, event, CLI, job, or library API
that no consumer can reach is not complete merely because it exists.

### 6.2 Durable-State Closure

Inventory every durable noun created, imported, or materially changed. For each
noun record:

- owner feature and storage/source of truth;
- access mode `user-owned-mutable` or `system-or-append-only`;
- data class `personal`, `sensitive`, or `operational`;
- creating and consuming journeys;
- lifecycle dispositions for `revisit`, `amend`, and `retire`;
- governance dispositions for `retain`, `export`, and `erase`;
- one disposition per applicable reciprocal:
  `owned-by:<feature>`, `bridge:<description>; replaced-by:<later-feature>`, or
  `excluded:<evidence-backed reason>`.

`revisit` is mandatory for a user-owned mutable noun. `amend` is mandatory when
the product permits change. `retire` is mandatory unless policy or semantics
prohibit it. `retain`, `export`, and `erase` are mandatory for personal or
sensitive data unless an authorized policy supplies the explicit exclusion.
Operational classification must be evidenced; it is not a shortcut around data
obligations.

A select-to-continue screen does not satisfy revisit. A retention statement
without an enforcing mechanism, export without a consumer path, or erase that
only hides data remains unresolved.

### 6.3 Surface-Removal Closure

For every public or externally consumed surface replaced, renamed, or removed,
record:

- current consumers and blast radius;
- break class `contract-break` or `internal-only`;
- replacement owner;
- continuity disposition:
  `deprecate:<window>; removed-by:<feature>`,
  `shim:<description>; owned-by:<feature>`, or
  `hard-break:<authorized reason>`.

An undocumented removal is not a valid continuity plan. `hard-break` is a
material compatibility decision, never an inferred default.

### 6.4 Security and interaction projections

Derive `threat-model.md` from the actual trust/data/exposure surfaces and
`interaction-contract.md` from cross-feature durable/async edges, shared
protocols, multi-toucher state, and architecture-determining NFRs.

- Assign `TZ-NNN` only for a real security-review obligation.
- Assign `IC-NNN` only for a real cross-feature behavioral or NFR obligation.
- Map every id to owning feature acceptance criteria.
- When no qualifying surface exists, write the template's assessed negative
  section with the evidence used. A clean negative is not a separate human
  attestation.
- A security exception, hard break, policy waiver, or unresolved ownership
  remains human-owned.

### 6.5 Architecture re-screen

Re-run the architecture driver screen over the completed journey, durable-state,
surface-removal, threat, and interaction evidence.

- A new driver or changed decision frame returns to Stage 1A.
- A candidate-only mismatch with the selected direction returns to Stage 5A.
- Otherwise record that the direction/disposition remains current.

## 6.6 Material Exceptions gate `[material]`

Collect only unresolved rows whose resolution changes scope, feature ownership,
architecture, security/risk acceptance, compatibility, or delivery order.
Auto-resolve evidenced non-material rows and show them in the final summary.

Before asking, print the relevant terms from this **Legend**:

| Term | Gloss |
|---|---|
| `owned-by: <feature>` | A feature in this plan provides this — **no action needed**. |
| `bridge: <desc>` | A temporary stand-in ships now; a **named later feature replaces it**. |
| `excluded: <reason>` | You're deciding this is **intentionally never built** — ship without it. |
| `deprecate: <window>` | The old surface keeps working for a **stated window**; a later feature removes it. |
| `shim: <desc>` | An **adapter** carries old callers onto the new surface. |
| `hard-break: <reason>` | The old surface **breaks immediately** — existing callers must change now. |
| durable noun | Something the app **saves and a user expects to return to**. |
| reciprocal | The matching ability a saved thing needs: if you can **create** it, can you **find / change / delete** it? |
| `revisit` / `amend` / `retire` | **find it again** / **change it** / **delete-or-archive it**. |
| `retain` / `export` / `erase` | **how long it's kept** / **get a copy of it** / **permanently delete it**. |
| access-mode: `user-owned-mutable` / `system-or-append-only` | **a thing users create and edit** / **a log or record nobody edits after the fact**. |
| data-class: `personal` / `sensitive` / `operational` | **tied to a person (safe default)** / **regulated, high-harm** / **no person behind it**. Downgrading to `operational` is the **material move**. |
| select-to-continue exclusion | A screen that **lists things only to pick one and move forward** does not count as revisit. |
| break-class: `contract-break` / `internal-only` | **An outside caller depends on this surface (default)** / only this plan's code uses it. |
| Scope Lock | The boundary is **frozen for this run; widening goes up a layer, never through it**. |

5. **Full Journey Map:** show the affected journey and release cut, not only the
isolated unresolved cell.

For each exception render:

```text
Decision [D-n] — <short title>
Gate N of M — Material Exceptions
Decision owner: <role and authority>
Evidence: <demonstrated/read/inferred/unknown paths>
Assumptions and unknowns: <material gaps>
Options: <2–4 distinct outcomes with consequences>
Recommendation: <option and reasoning>
If wrong: <blast radius>
```

Ask at most four questions in one call. Additional questions resume under the
same locator. Always offer **Need evidence / route to owner** and **Park** where
appropriate. An `excluded`, `hard-break`, sensitive-data downgrade, security
waiver, or oversized feature needs explicit authorized acceptance.

Record accepted decisions with owner, authority, rationale, affected ids, and
candidate revision. Loop back to the owning check, not to every earlier stage.

If there are no material exceptions, do not fire this gate.

## Stage 7 — Session fit and final candidate

For each feature, verify that one implementation session can reasonably:

- load its bounded context;
- implement its ordered tasks without a second product/architecture decision;
- run the required tests and checks;
- leave a reviewable coherent change.

Split an oversized feature automatically when the split preserves value,
ownership, interfaces, and verification. If no safe split exists, present the
specific trade-off at the Material Exceptions gate; do not silently coarsen.

After a split or other material delta, increment `candidate_revision` and rerun
only affected dependency, reachability, security/interaction, architecture, and
specification-route checks. A stale Stage 5A result must be rerun.

Checkpoint:

- final feature order and routes;
- closure matrices and projections;
- architecture convergence/disposition;
- auto-resolved rows;
- human decisions and remaining gaps;
- exact source hashes and candidate revision.

**Next:** load `${CLAUDE_SKILL_DIR}/stage-8-9-write.md`.
