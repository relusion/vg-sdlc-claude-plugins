# Feature Plan — Artifact Template

Output structure, section templates, manifest schema, and tooling mapping for the
plan directory the plan skill writes, **plus the repo-level layer** every
plan in the repo shares. The skill loads this file at write time after Final
Plan Approval.

---

## Repo-Level Layer

Some concerns are repo-wide, not plan-specific. They live outside any plan
directory so a second plan honors the same policy and sees the same decisions:

```text
docs/
├── adr/                  # repo-wide architectural decisions
└── plans/
    ├── plans.json        # registry of plans in this repo
    ├── vc-policy.md      # branching model, branch pattern, commit granularity
    ├── patterns.md       # repo-wide known pitfalls
    └── <slug>/           # per-plan directory (see Plan Directory Structure)
```

### `vc-policy.md`

The repo's version-control policy. Established once on the first
`/core-engineering:ce-implement` and honored by every plan thereafter. Shape:

```markdown
## VC Policy

| Field | Value |
|---|---|
| Repository | git |
| Branching model | feature-branch / trunk-based / manual |
| Branch pattern | feature/<plan-slug>/<id>  (default — multi-plan-safe) |
| Commit granularity | per-task / per-feature / none |
```

The default branch pattern includes `<plan-slug>` so two plans' `01-…` features
cannot collide. Users may pick `feature/<id>` at policy-establishment if they
prefer the simpler form on a single-plan repo.

### `plans.json` — plan registry

A slim index of every plan in this repo. Read by `/core-engineering:ce-spec` and `/core-engineering:ce-implement` to
resolve feature ids and disambiguate cross-plan matches; consulted by `/core-engineering:ce-plan` at
start to surface sibling plans for the related/unrelated decision.

```json
{
  "plans": [
    {
      "slug": "customer-portal",
      "description": "Customer support portal",
      "relates_to": []
    },
    {
      "slug": "admin-dashboard",
      "description": "Ops admin panel",
      "relates_to": ["customer-portal"]
    }
  ]
}
```

`relates_to` is one-directional, declared by the newer plan: this plan's specs
may read the named plans' Resolved Project Decisions ledger entries (presented
for human confirmation, never silently). Unrelated plans stay isolated. ADRs and
`patterns.md` are always shared across all plans, regardless of `relates_to`.

### Qualified feature ids — cross-plan references

In any **repo-level** artifact (ADR origin citations, ledger `Origin` cells,
`patterns.md` origin lines, cross-plan dependencies), refer to features in
their **qualified** form `<plan-slug>/<feature-id>` — e.g.
`customer-portal/03-user-profile`. Within a plan's own files (its `features/`,
`specs/`, `plan.json`), the unqualified id is fine.

A feature may declare a **cross-plan hard dependency** by listing a qualified
id in its `dependencies.hard`:

```yaml
dependencies:
  hard:
    - id: customer-portal/01-auth-foundation
      reason: …
```

`spec` Stage 0.2 (enforce dependency order) resolves qualified ids
against the referenced plan's `specs/` or its built code, and stops if the
dependency is neither specced nor built.

---

## Plan Directory Structure

Every plan is written as a **directory**, including a one-feature plan, so a
downstream skill can load one feature without reading the whole plan:

```text
docs/plans/[project-slug]/
├── feature-plan.md       # index — orientation and human review
├── shared-context.md     # context every downstream feature spec needs
├── architecture-selection.json  # reviewed pre-decomposition option set + human-selected direction
├── architecture-options.md  # readable comparison; present when directions were explored
├── threat-model.md       # trust boundaries + data-classes + per-feature security obligations
├── interaction-contract.md  # cross-feature protocol invariants + architecture-determining NFRs (read-only re-projection)
├── features/
│   ├── 01-<slug>.md      # one full feature block per feature
│   ├── 02-<slug>.md
│   └── …
└── plan.json             # machine-readable manifest
```

Each section template in **Section Details** below belongs to exactly one file.
Place it per this map:

| File | What it contains |
|---|---|
| `feature-plan.md` | 1 Overview · 2 Project Context · 4 Material Decisions and Assumptions · 5 Why This Split · 8 Journey Map / Consumability Trace · 9 Journey Bridges by Feature · 10 Dependency Flow · Feature Table · 12 Execution Checklist · 13 Notes · 14 Tooling Mapping |
| `shared-context.md` | 3 Codebase Profile · 6 Project Docs · 7 Known Pitfalls · Selected Architecture Direction · Architecture Disposition · Resolved Project Decisions |
| `architecture-selection.json` | Exact capability-level evaluation frame, source/evidence fingerprints, eligible/eliminated solution directions, constraint verdicts, score vectors, sensitivity/confidence, recommendation, and human selection |
| `architecture-options.md` | Immutable human-readable pre-approval comparison of explored and eliminated directions, constraints, score vectors, confidence/sensitivity, evidence, assumptions, reasoning, consequences, and recommendation; the later human selection remains in `architecture-selection.json`; omitted when no comparison ran |
| `threat-model.md` | Threat Model (Trust Boundaries · Secrets & Data-Classes · Exposure Surface · Per-Feature Security Obligations) — a read-only re-projection of §3 / §6.3 / §7.5; see *Threat Model* below |
| `interaction-contract.md` | Interaction Contract (Behavioural-Protocol Invariants · Architecture-Determining NFRs · Per-Feature Interaction Obligations) — a read-only re-projection of §3 / §8 Journey Map / §10 Dependency Flow / §6.3 durable nouns (multi-toucher set derived via §8 / §10) / §2–§4 cited NFRs; see *Interaction Contract* below |
| `features/<id>.md` | one copy of the 11 Features block, per feature |
| `plan.json` | the manifest (see Plan Manifest below) |

`feature-plan.md` must **not** inline the per-feature blocks — it carries only the
compact Feature Table and links to `features/<id>.md`.

---

## Architecture Selection (`architecture-selection.json`)

This file is the durable, machine-validated record of the capability-level
evaluation performed before feature decomposition. It preserves decision
support and human authority; it is not a final architecture baseline or an ADR.
When directions were explored, `architecture-options.md` is the readable view
that the human reviewed before choosing; this JSON remains authoritative.
Use this exact top-level shape:

```json
{
  "schema_version": 2,
  "project_slug": "customer-support-portal",
  "exploration_id": "AEX-0123456789ab",
  "source_capability_revision": 1,
  "source_exploration_attempt": 1,
  "source_input_sha256": "<64 lowercase hex>",
  "evaluation_frame": {
    "project_intent": "Enable customers to complete the support journey.",
    "non_goals": ["Replace the existing identity platform."],
    "decision_owner": {
      "identity_or_role": "Solution Architecture Council",
      "authority_basis": "Repository governance assigns whole-solution direction approval to this council."
    },
    "architecture_applicability": "required",
    "driver_screen": [
      {"id": "explicit-architecture-deliverable", "verdict": "positive", "basis": "The brief requests a solution baseline.", "evidence": ["docs/briefs/customer-support-portal.md"]},
      {"id": "multi-runtime-or-deployment-boundary", "verdict": "negative", "basis": "No new deployable is required.", "evidence": ["README.md"]},
      {"id": "cross-feature-durable-or-async-flow", "verdict": "negative", "basis": "No durable handoff is required.", "evidence": ["docs/briefs/customer-support-portal.md"]},
      {"id": "shared-data-ownership-or-migration", "verdict": "negative", "basis": "No shared-state migration is in scope.", "evidence": ["docs/briefs/customer-support-portal.md"]},
      {"id": "trust-residency-or-sensitive-boundary", "verdict": "negative", "basis": "No new trust or residency crossing is in scope.", "evidence": ["docs/briefs/customer-support-portal.md"]},
      {"id": "shared-protocol-or-schema", "verdict": "negative", "basis": "No shared protocol changes are required.", "evidence": ["docs/briefs/customer-support-portal.md"]},
      {"id": "platform-or-topology-choice", "verdict": "negative", "basis": "The current platform remains fixed.", "evidence": ["README.md"]},
      {"id": "architecture-determining-nfr", "verdict": "negative", "basis": "No literal NFR changes the topology.", "evidence": ["docs/briefs/customer-support-portal.md"]},
      {"id": "contested-cross-feature-owner", "verdict": "negative", "basis": "No contested owner is known before decomposition.", "evidence": ["README.md"]},
      {"id": "team-policy-recommendation", "verdict": "negative", "basis": "No separate team recommendation applies.", "evidence": ["README.md"]},
      {"id": "planned-reuse-recommendation", "verdict": "negative", "basis": "No additional consumer is planned.", "evidence": ["docs/briefs/customer-support-portal.md"]},
      {"id": "baseline-preference", "verdict": "negative", "basis": "The explicit deliverable already makes the route required.", "evidence": ["docs/briefs/customer-support-portal.md"]}
    ],
    "accepted_decisions": [],
    "material_gaps": [],
    "capabilities": [
      {"id": "C01", "outcome": "A customer can complete a support request.", "actors": ["customer"], "data": ["support request"], "integrations": ["existing identity platform"], "observable": "The request is accepted and visible."}
    ],
    "journeys": [
      {"id": "J01", "outcome": "A support request reaches an actionable state.", "actors": ["customer", "support agent"], "capability_refs": ["C01"], "steps": ["Submit and observe the request."], "observable": "The support agent can act on it."}
    ],
    "quality_attribute_scenarios": []
  },
  "blocking_decision": null,
  "sources": [
    {"path": "README.md", "sha256": "<64 lowercase hex>", "kind": "repository"},
    {"path": "docs/briefs/customer-support-portal.md", "sha256": "<64 lowercase hex>", "kind": "brief"}
  ],
  "evidence_fingerprint": "<64 lowercase hex>",
  "criteria": [
    {"id": "requirements-fit", "weight": 0.25, "basis": "<source-backed basis>"},
    {"id": "quality-attribute-fit", "weight": 0.20, "basis": "<source-backed basis>"},
    {"id": "repository-fit", "weight": 0.15, "basis": "<source-backed basis>"},
    {"id": "evolvability", "weight": 0.15, "basis": "<source-backed basis>"},
    {"id": "operability", "weight": 0.15, "basis": "<source-backed basis>"},
    {"id": "delivery-feasibility", "weight": 0.10, "basis": "<source-backed basis>"}
  ],
  "hard_constraints": [
    {"id": "HC01", "statement": "<non-negotiable constraint>", "basis": "<why it is hard>", "authority": "<human, accepted ADR, or policy>"}
  ],
  "options": [
    {
      "option_id": "A01",
      "title": "<direction title>",
      "summary": "<complete solution direction>",
      "responsibilities_and_boundaries": ["<responsibility or boundary>"],
      "runtime_and_deployment": ["<runtime or placement>"],
      "data_ownership": ["<source of truth and ownership>"],
      "integrations_and_failure": ["<flow and failure behavior>"],
      "trust_residency_and_security": ["<trust, residency, and security treatment>"],
      "quality_tactics": ["<quality-scenario tactic>"],
      "migration_and_evolution": ["<migration and evolution path>"],
      "capability_implications": ["C01 — <realization implication>"],
      "assumptions": ["<assumption or explicit none with basis>"],
      "irreversible_commitments": ["<commitment or explicit none with basis>"],
      "constraint_verdicts": [
        {"constraint_id": "HC01", "verdict": "pass", "basis": "<specific basis>"}
      ],
      "scores": [
        {"criterion_id": "requirements-fit", "score": 5, "basis": "A01 realizes C01 and J01 without adding product scope.", "evidence_state": "inferred", "evidence": ["docs/briefs/customer-support-portal.md"]},
        {"criterion_id": "quality-attribute-fit", "score": 4, "basis": "A01 addresses the recorded quality scenarios with one remaining inference.", "evidence_state": "inferred", "evidence": ["docs/briefs/customer-support-portal.md"]},
        {"criterion_id": "repository-fit", "score": 4, "basis": "A01 uses the observed repository runtime and boundaries.", "evidence_state": "observed", "evidence": ["README.md"]},
        {"criterion_id": "evolvability", "score": 3, "basis": "A01 preserves an additive migration path but retains some coupling.", "evidence_state": "inferred", "evidence": ["docs/briefs/customer-support-portal.md"]},
        {"criterion_id": "operability", "score": 4, "basis": "A01 reuses observed operational conventions with explicit failure handling.", "evidence_state": "inferred", "evidence": ["README.md"]},
        {"criterion_id": "delivery-feasibility", "score": 4, "basis": "A01 fits the current delivery environment with a reversible cutover.", "evidence_state": "inferred", "evidence": ["README.md"]}
      ],
      "weighted_score": 4.1,
      "confidence": "medium",
      "option_sha256": "<64 lowercase hex>"
    }
  ],
  "eliminated_options": [],
  "option_set_sha256": "<64 lowercase hex>",
  "architecture_options_report": {
    "schema_version": 1,
    "status": "present",
    "path": "architecture-options.md",
    "sha256": "<SHA-256 of the immutable pre-approval report bytes>",
    "reason": null
  },
  "recommendation": {
    "option_id": "A01",
    "confidence": "medium",
    "sensitivity": "stable",
    "sensitivity_witness": null,
    "basis": "<fit, trade-off, and leader-changing condition>"
  },
  "selection": {
    "status": "direction-selected",
    "option_id": "A01",
    "option_sha256": "<same option hash>",
    "decided_by": "human",
    "approved_by": "Solution Architecture Council",
    "rationale": "<human rationale>"
  },
  "next_owner": "ce-plan"
}
```

Every eligible option carries all six score rows in the canonical criterion
order. Each row includes a non-empty option-specific `basis`, which is covered
by the option hash and rendered in the readable weighted comparison. Each
option also carries one verdict per hard constraint. A failed or unknown
constraint makes the option ineligible, with `scores: []`,
`weighted_score: null`, and `confidence: not-applicable`;
`eliminated_options` exactly lists failed options.
A fresh `direction-selected` exploration retains two to four complete
directions, even when constraint gating leaves one eligible.
For a `stable` or `not-applicable` recommendation, set
`sensitivity_witness: null`. An `unstable` recommendation instead records the
first deterministic leader-changing scenario as exactly `{scenario,
criterion_id, challenger_option_id, evidence_bounds, condition}`. `scenario`
is one of `base-score`, `evidence-range`, `weight-minus-25`, or
`weight-plus-25`; `criterion_id` is the affected canonical criterion for a
weight scenario and `null` otherwise; and `challenger_option_id` identifies the
competing retained option. `evidence_bounds` is exactly
`{recommended: exact, challenger: exact}` when the weight change alone ties or
flips, otherwise `{recommended: lower, challenger: upper}` to expose the
combined evidence-range condition. `condition` uses the canonical sentence
template defined by exploration mode. The validator recomputes and pins every
field, so generic or false sensitivity prose cannot authorize a selection.
For `not-applicable` or `deferred`, keep
the same top-level keys, use null selected-option fields, empty option arrays
when no exploration ran, and record `decided_by: human`, `approved_by: null`,
plus a non-empty basis. For a selected direction, `approved_by` exactly matches
`evaluation_frame.decision_owner.identity_or_role`; delegation requires a
decision-frame revision before selection.
Every durable status retains the exact `evaluation_frame` and all six confirmed
criteria/weights; an explicit N/A or defer is not an incomplete frame. Only a transient
`requires-decision` carries a non-null `blocking_decision`, with two to four
supplied bounded options for `/core-engineering:ce-decide`; every durable status
sets it to `null`.

Schema v2 is mandatory. A freshly
explored `direction-selected` result uses the `present` report binding shown
above. A new `not-applicable` or `deferred` disposition instead writes
`{"schema_version":1,"status":"not-produced","path":null,"sha256":null,
"reason":"<why no multi-option comparison ran>"}`. Do not fabricate a report or
retroactively imply review.

Hash canonicalization is UTF-8 JSON with sorted object keys, compact separators,
Unicode preserved, and finite numbers. `evidence_fingerprint` hashes the
path-sorted complete `sources` array. An option hash covers that option with
`option_sha256` omitted. The option-set hash covers ordered option id/hash pairs
plus the complete ordered eliminated ledger. For a selected exploration,
`exploration_id` is `AEX-` plus the first 12 characters of the option-set hash.
`source_input_sha256` hashes the canonical decision-relevant projection of the
confirmed input: revisions, evaluation frame, hard constraints, criteria, and
complete source inventory; only the caller's parent-gate locator is excluded.
The selection result version does not change that input canonicalization.
Run `architecture-selection-lint.py` before publishing the plan.

---

## Section Details

### 1. Overview

Write a 2–3 sentence project summary.

Include:

- what is being built or changed
- who it is for
- what the decomposition is optimized for

---

### 2. Project Context

Include the original project description verbatim.

```markdown
## Project Context

### Original Project Description

> [verbatim project description]
```

---

### 3. Codebase Profile

Include the structured profile from Stage 1.2.

Recommended format:

```yaml
codebase_profile:
  stack:
    language:
    framework:
    package_manager:
    manifest_path:              # where new deps are declared (package.json / pyproject.toml / requirements.txt)
    registry_query_command:     # confirms a package exists (e.g. `npm view {pkg}` / `pip index versions {pkg}`) — dep-existence check
    build_system:
  public_interaction_surfaces:
    ui_routes:
    api_endpoints:
    cli_commands:
    exported_functions:
    webhook_handlers:
  data_surfaces:
    persistence_style:
    tables_or_collections:
    migration_mechanism:
    event_schemas:
  integration_boundaries:
    - 
  cross_cutting_layers:
    - 
  convention_density:
  hot_files:
    - 
  baseline_delivery_health:
    working_tree:
    build_command:
    test_command:
    lint_or_typecheck_command:
    ci_configured:
    deployment_target:
  brownfield_friction:
    tier:
    reason:
```

---

### Threat Model — `threat-model.md`

A per-plan, **read-only re-projection** assembled at write time from the **§3
Codebase Profile** (artifact section — trust boundaries / exposure), the **plan
Stage-6.2 Durable-State Closure** (data-classes), and the **plan Stage-6.4**
security projection. (The `§6.2` / `§6.4` are *plan stage* numbers,
distinct from this artifact's own §1–§14 sections.) It is the
security context `/core-engineering:ce-spec` derives `[SECURITY]` criteria from, and `/core-engineering:ce-review`,
`/core-engineering:ce-probe-sec`, and `/core-engineering:ce-verify` read. **It never re-assigns a data-class** — the §6.3
closure owns that (assigned once from evidence and any material human
decision); the threat model only re-projects it, so the two can never drift.

**Threat-id assignment is *surface, don't force*:** a feature earns a `TZ-NNN`
(zero-padded, house style) when it **crosses a trust boundary** — owns / exposes a
public interaction surface, or integrates across an auth / external-API / payment /
object-store boundary — **or is the security / secrets Boundary-Owner**. A feature
that *only owns* a `sensitive` / `personal` noun with no boundary of its own carries
an **advisory note**, never a forced threat id. Assignment is evidence-derived
and included in Final Plan Approval; only an exception or acceptance decision
requires its own material decision.

````markdown
# Threat Model: <plan-slug>

> Generated by /core-engineering:ce-plan — a READ-ONLY re-projection of §3 Codebase
> Profile + §6.2 Durable-State Closure (data-classes) + §6.4 security projection.
> Consumed by /core-engineering:ce-spec (derives [SECURITY: TZ-NNN] criteria), /core-engineering:ce-review, /core-engineering:ce-probe-sec, /core-engineering:ce-verify.
> Data-classes are owned by the §6.3 closure and never re-assigned here.

## Trust Boundaries
| Boundary | Entry point / surface | Untrusted input | Auth required | Source |
|---|---|---|---|---|
| public HTTP API | `POST /orders` | client body | bearer token | profile.public_interaction_surfaces |
| payment gateway | Stripe API (outbound) | — | API key (secret) | profile.integration_boundaries |

## Secrets & Data-Classes   *(read-only re-projection of §6.3 — never re-assigned here)*
| Durable noun | Data-class | Owning feature | Governance dispositions |
|---|---|---|---|
| `credential` | sensitive | 02-auth | retain owned-by:02-auth · export excluded · erase owned-by:09-account |

## Exposure Surface
| Surface | Externally reachable | Notes |
|---|---|---|
| `POST /orders` | yes | authenticated |

## Per-Feature Security Obligations
The machine-readable block `/core-engineering:ce-spec`'s Security Criteria (and a later spec-lint H5
check) read. One entry per feature; `threat_ids` empty ⇒ no obligation (an
`advisory` may still note a sensitive noun with no boundary).

```yaml
security_obligations:
  - feature: 03-checkout
    threat_ids: [TZ-001, TZ-002]
    surface_kinds: [authz, validation]   # injection | authz | secrets | validation
  - feature: 05-profile
    threat_ids: []
    advisory: "owns `sensitive` noun `credential` with no boundary of its own — consider a security criterion"
```
````

**No-Security-Surface negative.** When **none** of the four detection conditions
hold across the plan, write `threat-model.md` with the section below *in place of*
the four above — an explicit assessed negative with evidence, never a silent
skip:

````markdown
## No Security Surface

This plan has no detected security surface. All four conditions checked, each absent:
- no auth/authz or secrets-management cross-cutting layer (§3 profile.cross_cutting_layers)
- no auth-provider / external-API / payment / object-store integration boundary (§3 profile.integration_boundaries)
- no `personal` / `sensitive` durable noun (§6.3 closure)
- no security / secrets Boundary-Owner assigned (§7.5)

```yaml
security_obligations: []
```
````

---

### Interaction Contract — `interaction-contract.md`

A per-plan, **read-only re-projection** assembled at write time from the **§3
Codebase Profile** (`integration_boundaries` / `data_surfaces` /
`public_interaction_surfaces` / `cross_cutting_layers` — the protocol *substrate*),
the **§8 Journey Map / Consumability Trace (plan Stage 6) + §10 Dependency Flow** (the
producer→consumer *edges*), and the **plan Stage-6.3 Durable-State Closure** (the
durable nouns *touched by more than one feature*). (The `§6.3` is a *plan stage*
number, distinct from this artifact's own §1–§14 sections.) It is the cross-feature
behavioural context `/core-engineering:ce-spec` derives `[CONTRACT: IC-NNN]` criteria from, and `/core-engineering:ce-review`
and `/core-engineering:ce-verify` read. It pins the **protocol guarantees of an edge the plan already
traced** so a producer and consumer cannot silently disagree (delivery / ordering /
idempotency / retry / concurrency), and the **numbers that shaped the decomposition**
(architecture-determining NFRs).

**It owns nothing the layers below own.** It is **keyed on an edge it does not own** —
the Journey Map (§8) and Dependency Flow (§10) own the edge set; this contract only
attaches the protocol *values* to an edge they already trace, never enumerating or
re-deciding an edge. It **never re-assigns a data-class** (the §6.3 closure owns
that) and **never re-cuts a feature boundary** (the
decomposition owns that); it only adds the multi-toucher concurrency/idempotency
posture §6.3 does not capture and the protocol residue of an async edge — so the two
can never drift.

**Surface, don't force.** A **Behavioural-Protocol Invariant** row exists only for an
already-traced cross-feature edge crossing an **async / durable medium** (event-bus /
queue / external-API / shared-store — a synchronous in-process call has no protocol
residue and earns no row), or for a §6.3 durable noun **touched by >1 feature**. An
**Architecture-NFR** row exists only for a numeric target the plan **literally cited**
in §2 / §3 / §4 (Decomposition Q&A — incl. a brief's success criteria / constraints) *and* that **demonstrably shaped the cut** (forced a split, a boundary, an
async edge, a separate worker) — never a general perf target, never a number the plan
never stated. The `IC-NNN` ids (zero-padded, house style; **one shared id space across
both tables**) are evidence-derived and included in Final Plan Approval. A
material protocol exception remains a separate human-owned decision.

````markdown
# Interaction Contract: <plan-slug>

> Generated by /core-engineering:ce-plan — a READ-ONLY re-projection of §3 Codebase
> Profile + §8/§10 cross-feature edges + §6.3 durable nouns (multi-toucher via §8/§10) + §2/§3/§4 cited NFRs.
> Consumed by /core-engineering:ce-spec (derives [CONTRACT: IC-NNN] criteria), /core-engineering:ce-review, /core-engineering:ce-verify.
> Edges are owned by the §8 Journey Map / §10 Dependency Flow; data-classes by the §6.3
> closure; feature boundaries by the decomposition — none re-assigned here.

## Behavioural-Protocol Invariants
One row per already-traced cross-feature producer→consumer EDGE on an async/durable
medium, or per §6.3 durable noun touched by >1 feature. The edge is owned upstream;
this table only pins its protocol guarantees.

| IC-NNN | Edge / shared noun | Medium | Idempotency | Delivery | Ordering | Retry/Timeout | Concurrency | Producer / Consumer |
|---|---|---|---|---|---|---|---|---|
| IC-001 | 02-orders → 05-fulfilment (`order.placed`) | event-bus | consumer dedupes on `order_id` | at-least-once | per-`order_id` ordered | producer retries 3× backoff; consumer tolerates replay | — | 02-orders / 05-fulfilment |
| IC-002 | shared noun: `inventory_row` | shared-store | decrement idempotent per `reservation_id` | — | — | — | optimistic-lock on `version` | 04-cart (write) / 05-fulfilment (write) |

## Architecture-Determining NFRs
One row only for a numeric target the plan cited (§2 / §3 / §4) AND that shaped the cut.
`Source` must point at the literal text; an unstated number is not invented here.

| IC-NNN | NFR | Target | Source | Shapes (the decomposition consequence) | Owning feature(s) |
|---|---|---|---|---|---|
| IC-003 | throughput | 10k msg/s | §2 project description | forced async order pipeline → 05-fulfilment split from 02-orders | 02-orders, 05-fulfilment |

## Per-Feature Interaction Obligations
The machine-readable block `/core-engineering:ce-spec`'s Interaction-Contract Criteria read. One entry per
feature; `ic_ids` empty ⇒ no obligation (an `advisory` may still note a single-toucher
shared noun or a stated-but-non-shaping NFR).

```yaml
interaction_obligations:
  - feature: 05-fulfilment
    ic_ids: [IC-001, IC-003]
    kinds: [idempotency, ordering, throughput]   # idempotency | delivery | ordering | retry | concurrency | latency | throughput | tick-rate
  - feature: 09-reporting
    ic_ids: []
    advisory: "reads `inventory_row` but is the only toucher — no cross-feature concurrency obligation"
```
````

**No-Cross-Feature-Protocol negative.** When **none** of the four detection conditions
hold across the plan, write `interaction-contract.md` with the section below *in place
of* the tables above — an explicit assessed negative with evidence, never a
silent skip:

````markdown
## No Cross-Feature Protocol

This plan has no detected cross-feature protocol or architecture-determining NFR. All
four conditions checked, each absent:
- no event / queue / external-API integration boundary carrying a cross-feature edge (§3 profile.integration_boundaries / data_surfaces.event_schemas)
- no §8 Journey-Map / §10 Dependency-Flow edge that crosses between two features over a durable/async medium
- no §6.3 durable noun touched by >1 feature
- no architecture-determining numeric target (latency / throughput / concurrency / tick-rate) cited in §2 / §3 / §4 as a decomposition driver

```yaml
interaction_obligations: []
```
````

---

### 4. Material Decisions and Assumptions

Record only questions actually asked, human-owned decisions, and material
assumptions. Do not manufacture a Q&A transcript for repository facts.

```markdown
| # | Question | Answer |
|---:|---|---|
| 1 | ... | ... |
```

---

### 5. Why This Split

Explain why these feature boundaries were chosen.

Include:

- primary slicing method
- validation methods used
- why alternatives were rejected
- how foundation features unlock later work
- how reachability/consumability is preserved

---

### 6. Project Docs

List project-wide reference docs.

If none:

```markdown
None
```

If docs exist:

```markdown
- `docs/architecture.md`
- `docs/api-contract.md`
- `design/system.md`
```

---

### 7. Known Pitfalls

List seeded pitfalls or write:

```markdown
None supplied.
```

If pitfalls were added to `patterns.md`, mention the path.

---

### Selected Architecture Direction

First summarize the pre-decomposition direction without replacing its
machine-readable authority. When exploration ran, link the report the human
reviewed before selection:

```markdown
## Selected Architecture Direction

| Status | Exploration | Selected option | Recommendation | Confidence / sensitivity | Binding | Human rationale |
|---|---|---|---|---|---|---|
| direction-selected | AEX-customer-support-1 | A02 — modular API + worker | A02 | medium / stable | `architecture-selection.json` (`<sha256>`) | Best fit for migration isolation while preserving the latency target. |
```

Readable option comparison: [`architecture-options.md`](architecture-options.md)

For `not-applicable` or `deferred`, render the explicit status and basis with
no invented selected option. This table is a projection;
`architecture-selection.json` and its manifest hash are authoritative.

### Architecture Disposition

Write the Final Plan Approval result into `shared-context.md` so every human and
downstream skill sees the same routing decision as `plan.json`:

```markdown
## Architecture Disposition

| Decision | Triggers | Convergence | Iterations | Basis | Accepted decisions | Downstream consequence |
|---|---|---|---:|---|---|---|
| required | shared-data-ownership-or-migration | converged | 2 | The source-of-truth and migration boundary shape P02/P03. | `docs/adr/0007-order-source.md` | Publish a current approved `/core-engineering:ce-architecture` package before spec or auto-build. |
```

Use `recommended` or `not-required` exactly as recorded in the manifest.
`recommended` is either selected and converged or explicitly deferred;
`not-required` is not-applicable.

---

### Resolved Project Decisions

A ledger of cross-feature decisions resolved during architecture shaping or
later by `/core-engineering:ce-spec`. It is empty at plan write only when no
plan-time decision was required. Specs append to it as they resolve unknowns
that affect more than one feature, so every later spec reads it before
re-deciding anything.

When no plan-time decision exists, write this placeholder:

```markdown
## Resolved Project Decisions

_None yet — populated by architecture shaping or `/core-engineering:ce-spec` as cross-feature unknowns are resolved._
```

Architecture shaping writes accepted decisions with origin `plan architecture
shaping`; specs append rows in the same shape:

```markdown
| # | Decision | Resolution | Origin | Detail |
|---|---|---|---|---|
| RPD-1 | Which identity provider for admin login? | Okta | spec customer-portal/03-user-profile | ADR-0007 |
| RPD-2 | Are failed imports retryable? | Yes — retryable with backoff | spec customer-portal/05-bulk-import | (inline) |
| RPD-3 | Which service owns order writes during migration? | Existing order service until cutover | plan architecture shaping | `docs/adr/0012-order-cutover.md` |
```

Architecturally-significant decisions cite their ADR in **Detail**;
non-architectural ones state the full resolution and mark **Detail** `(inline)`.

---

### 8. Journey Map or Consumability Trace

Use UI Journey Map for UI projects; Consumability Trace for backend/API/CLI/SDK/worker/infrastructure.

Each journey is **testable-by-design**. Record, per journey, a **primary verification modality** (the dominant tool class), and per step the `Step | Surface | Owned By | Reachability | Modality | Expected observable` columns (see plan Stage 6) — a step names its own modality when it crosses to another surface. The expected observable is outcome-level (what the user/consumer sees — rendered confirmation, status code, exit code, persisted row, emitted event), not test mechanics; `spec` derives the concrete test cases from it and carries each step's modality onto them. Modality vocabulary: `browser · http · cli · sdk · event · iac · db · manual` (extend as needed).

```markdown
**Journey: <name>**  ·  primary modality: <browser | http | cli | sdk | event | iac | db | manual>

| Step | Surface | Owned By | Reachability | Modality | Expected observable |
|---|---|---|---|---|---|
| … | … | … | … | … | … |
```

**Durable-State Closure (plan Stage 6.3).** For each durable noun any journey writes
(a step with modality `db`, or `event` / `iac` against a persisted target — see gate §6.3.1),
record its access-mode and the disposition of its three reciprocals:

| Noun | Access-mode | Data-class | revisit | amend | retire | retain | export | erase |
|---|---|---|---|---|---|---|---|---|
| <noun> | user-owned-mutable / system-or-append-only | personal / sensitive / operational | owned-by:<id> / bridge:… / excluded:<reason> | … | … | … | … | … |

Reciprocals dispositioned `excluded` are recorded in Notes (§13) with their reason.

**Surface-Removal Closure (plan Stage 6.4 — brownfield only).** For each existing
shipped public surface (from the Stage 1.2 codebase profile) any feature's scope
removes, renames, or incompatibly changes, record its break-class and the
disposition of its continuity obligation:

| Surface | Break-class | continuity |
|---|---|---|
| <route / signature / event / flag / config key> | contract-break / internal-only | deprecate:<window>,removed_by:<id> / shim:<desc>,owned-by:<id> / hard-break:<reason> |

Surfaces dispositioned `hard-break` are recorded in Notes (§13) with their reason
and blast radius. A greenfield plan records this `N/A`.

If a journey is deferred, record it in Notes.

---

### 9. Journey Bridges by Feature

List only features that ship bridges.

If no bridges:

```markdown
N/A
```

Bridge block format:

```yaml
feature: 02-create-order
bridges:
  - type: exit
    description: "Show temporary order-submitted page until order history exists."
    replaces: "Missing order history return surface"
    replaced_by: "04-order-history"
```

---

### 10. Dependency Flow

Use ASCII or Mermaid.

ASCII example:

```text
01-auth-foundation
   |
   v
02-dashboard-shell
   |
   +--> 03-create-order
   |        |
   |        v
   |    04-order-history
   |
   +--> 05-user-profile
```

Mermaid example:

```mermaid
flowchart TD
    F01[01-auth-foundation] --> F02[02-dashboard-shell]
    F02 --> F03[03-create-order]
    F03 --> F04[04-order-history]
    F02 --> F05[05-user-profile]
```

---

### 11. Features

Write **one file per feature** at `features/<id>.md`, where `<id>` is the stable
feature slug. Each file contains exactly this block:

````markdown
## 01-feature-slug

**Title:** Human-readable feature title  
**Type:** foundation | user-facing | integration | infrastructure | refactor | enabling  
**Description:** Short explanation of what this feature delivers.
**Specification route:** compact | explicit

### Structured Metadata

```yaml
id: 01-feature-slug
title:
type:
status: planned
priority:
owner:
intrinsic_complexity:
brownfield_adjusted_complexity:
final_complexity:
risk_profile:
boundary_owner:
reviewer_triggers:
dependencies:
  hard:
    - id:
      reason:
  soft:
    - id:
      reason:
      bridge_required:
open_unknowns:
  - 
```

### Sizing

| Signal | Value |
|---|---|
| Public interaction surfaces | |
| Data surfaces | |
| Integration boundaries | |
| Cross-cutting concerns | |
| Fits one implementation session | yes/no |
| Session-fit disposition | standard / consented-coarsened |
| Brownfield friction applied | yes/no |
| Reviewer trigger count | |
| Final Complexity | |

### Scope

- 

### Excluded

- 

### Public / Data / Integration Surfaces

Public interaction surfaces:

- 

Data surfaces:  *(tag each persisted noun `[user-owned-mutable]` or `[system-or-append-only]` **and** `[personal]` / `[sensitive]` / `[operational]` — the access-mode + data-class that drive Stage 6.3 closure)*

- 

Integration boundaries:

- 

### Dependencies

Hard dependencies:

- 

Soft dependencies:

- 

### Unlocks

- 

### Journey / Consumability Impact

- 

### Open Unknowns

- 

### Validation Target

This feature is ready for downstream specification when the spec can define how to verify:

- 

### Run

For `explicit`:

```bash
/core-engineering:ce-spec <plan-slug>/01-feature-slug
```

For `compact` (implementation composes and lints the canonical compact spec
before code):

```bash
/core-engineering:ce-implement <plan-slug>/01-feature-slug
```
````

---

### Feature Table

`feature-plan.md` lists every feature in one compact table — no full blocks. The
full detail lives in each `features/<id>.md`.

```markdown
| # | Feature | Type | Spec route | Final Complexity | Risk | Hard Deps | File |
|---:|---|---|---|---|---|---|---|
| 1 | 01-auth-foundation | foundation | compact | Moderate | low | — | `features/01-auth-foundation.md` |
| 2 | 02-dashboard-shell | user-facing | explicit | Simple | low | 01-auth-foundation | `features/02-dashboard-shell.md` |
```

---

### 12. Execution Checklist

One checkbox per feature in ship order.

```markdown
- [ ] 01-auth-foundation
- [ ] 02-dashboard-shell
- [ ] 03-create-order
```

---

### 13. Notes

Include:

- deferred journeys
- high-risk feature justifications
- accepted bridge trade-offs
- explicit user overrides
- architecture disposition, shaping iteration count, and any human-owned
  exception with its residual rework risk
- known limitations
- assumptions made during planning
- durable-noun reciprocals excluded by design (with reason) — usability (revisit / amend / retire) **and** governance (retain / export / erase), each named
- any durable-noun data-class downgrade (`personal` → `operational`) or upgrade (`personal` → `sensitive`), with reason
- existing surfaces hard-broken by design (with reason and blast radius)
- the light plan tier when `plan_tier: light`, including why the feature
  boundaries and verification were unambiguous

---

### 14. Tooling Mapping

Only when the user named a target tool: emit a short `## Tooling Mapping` section naming the tool, mapping each plan field — Feature ID, Type, Final Complexity, Risk-Profile, Boundary-Owner, Dependencies, Open-Unknowns, Validation Target — to its counterpart in that tool (Azure DevOps, Jira, GitHub Issues, Linear, …). Omit the section when no target tool is named.

---

## Machine-Readable Feature Schema

Use this schema as the canonical feature metadata shape inside the Markdown artifact.

```yaml
id: string
title: string
type: foundation | user-facing | integration | infrastructure | refactor | enabling
status: planned
priority: low | medium | high | critical | unknown
owner: string | unassigned
description: string

sizing:
  public_interaction_surfaces:
    count: number
    examples:
      - string
  data_surfaces:
    count: number
    examples:
      - string
  integration_boundaries:
    count: number
    examples:
      - string
  cross_cutting_concerns:
    count: number
    examples:
      - string
  fits_one_implementation_session: true | false
  session_fit: standard | approved-exception
  intrinsic_complexity: Simple | Moderate | Complex
  brownfield_adjusted_complexity: Simple | Moderate | Complex
  reviewer_trigger_count: number
  final_complexity: Simple | Moderate | Complex

risk:
  profile: low | medium | high
  reason: string
  high_risk_justification: string | null

boundary_owner:
  categories:
    - security | secrets | persistence | i18n | accessibility | design-system   # + interface-foundation categories on demand (e.g. api-contract for http)
  reason: string | null

scope:
  in:
    - string
  out:
    - string

dependencies:
  hard:
    - id: string
      reason: string
  soft:
    - id: string
      reason: string
      bridge_required: true | false

bridges:
  - type: entry | exit | consumer | operational
    description: string
    replaces: string
    replaced_by: string

unlocks:
  - id: string
    reason: string

open_unknowns:
  - string

validation_target:
  - string

run:
  command: string
```

---

## Plan Manifest (`plan.json`)

`plan.json` is the machine-readable index of the plan. It lets a downstream
skill resolve feature files, ship order, and the dependency graph without
parsing Markdown.

```json
{
  "project_slug": "customer-support-portal",
  "status": "planned",
  "plan_revision": 1,
  "plan_tier": "standard",
  "architecture_disposition": {
    "decision": "required",
    "triggers": ["shared-data-ownership-or-migration"],
    "rationale": "The source-of-truth and migration boundary shape the feature cut.",
    "decided_by": "human",
    "direction": {
      "status": "direction-selected",
      "artifact": "architecture-selection.json",
      "artifact_sha256": "<64 lowercase hex over exact file bytes>",
      "exploration_id": "AEX-0123456789ab",
      "selected_option_id": "A01",
      "selected_option_sha256": "<64 lowercase hex>",
      "decided_by": "human",
      "summary": "The selected direction keeps one write owner and an explicit migration boundary."
    },
    "convergence": {
      "status": "converged",
      "iteration_count": 1,
      "summary": "The shaping pass confirmed one write owner and an ordered cutover feature.",
      "decision_refs": ["docs/adr/0012-order-cutover.md"]
    }
  },
  "relates_to": [],
  "features": [
    {
      "id": "01-auth-foundation",
      "title": "Authentication foundation",
      "type": "foundation",
      "specification_route": "explicit",
      "final_complexity": "Moderate",
      "risk_profile": "low",
      "ship_order": 1,
      "file": "features/01-auth-foundation.md",
      "dependencies": { "hard": [], "soft": [] }
    }
  ]
}
```

The `features` array is in ship order. Every `file` path is relative to the plan
directory and must point to an existing `features/<id>.md`.
`features[].specification_route` is the machine authority and is exactly
`compact` or `explicit`. Each feature Markdown file contains one matching
`**Specification route:** ...` projection and does not repeat the field in its
YAML metadata.

### `architecture_disposition` — architecture admission and convergence

Every plan carries this object and its `direction` binding. Specification,
implementation, auto-build, and baseline architecture validate it rather than
assuming architecture is optional.

Consistency rules:

| `decision` | Direction status | Required convergence | Other invariants |
|---|---|---|---|
| `required` | `direction-selected` | `converged` | at least one load-bearing trigger; `iteration_count >= 1`; a current accepted-for-specification architecture package is required before spec |
| `recommended` | `direction-selected` or `deferred` | `converged` or `deferred` | at least one recommendation trigger; selected plus `converged` has `iteration_count >= 1`; `deferred` has `iteration_count: 0`; residual uncertainty stays visible |
| `not-required` | `not-applicable` | `not-applicable` | no positive triggers; `iteration_count: 0`; the complete negative screen and Final Plan Approval supply the basis |

`decided_by` is `human`. `decision_refs` contains repository-relative paths to
accepted ADRs and may be empty. Shaping convergence is not final architecture
approval: the architecture package is written afterward so it can bind stable
feature ids, `plan_revision`, and source hashes without a circular manifest
dependency.

For `recommended`, direction status and shaping convergence remain independent:
direction `deferred` means the human deferred the recommendation at the
architecture workbench. Write time never infers defer from an absent result.

`direction.artifact` is exactly `architecture-selection.json`; its SHA-256 is
over the exact file bytes. The exploration id and selected option id/hash must
equal the selection artifact, with null selected fields for
an artifact whose direction status is `not-applicable` or `deferred`.
Both the disposition and direction record
`decided_by: human`; prose summaries never override the bound artifact.

`triggers` contains only Stage 3.9 stable ids. Required routes use the nine
load-bearing driver ids; recommended routes use only
`team-policy-recommendation`, `planned-reuse-recommendation`, or
`baseline-preference`. Duplicate, prose, or unknown trigger values are invalid.

### `plan_revision` — the revision counter

`plan_revision` is a monotonically increasing integer stamped on every write.
The first written plan is revision `1`. Each `/core-engineering:ce-plan` Stage R
revision bumps it by one and appends a
`plan-revision <N>` entry to Notes (§13) recording what changed, which gates re-ran,
and which were held. A touched feature's `features/<id>.md` Structured-Metadata block is
stamped `revised_by: plan-revision <N>` — the signal that its `specs/<id>/` (if any) is
now stale and its `/core-engineering:ce-spec` must be re-run. Untouched features keep no such stamp and
their specs are preserved byte-for-byte.

### `plan_tier` — which gate set ran

`plan_tier` is `standard` or `light`. `light` is derived only when scope,
boundaries, and verification are unambiguous, no feature is high risk, and
architecture is not required. Both tiers use the same directory shape,
reachability/security/interaction checks, final approval, and lint floor.

---


## Practical Tooling Field Mapping

| Workflow Field | Azure DevOps | Jira | GitHub Issues | Linear |
|---|---|---|---|---|
| Feature ID | Title prefix | Issue key/title prefix | Issue title prefix | Issue title prefix |
| Type | Work item type / tag | Issue type / label | Label | Label |
| Scope | Description | Description | Body | Description |
| Excluded | Description section | Description section | Body section | Description section |
| Final Complexity | Story points / custom field | Story points / custom field | Label / project field | Estimate |
| Risk-Profile | Custom field / tag | Custom field / label | Label | Label |
| Boundary-Owner | Tag | Component / label | Label | Label |
| Dependencies | Predecessor/successor links | Issue links | Linked issues | Relations |
| Open-Unknowns | Checklist / comments | Checklist / comments | Task list | Comments / sub-issues |
| Validation Target | Acceptance criteria seed | Acceptance criteria seed | Checklist | Checklist |
| Execution Checklist | Delivery checklist | Epic checklist | Project board | Project milestones |
