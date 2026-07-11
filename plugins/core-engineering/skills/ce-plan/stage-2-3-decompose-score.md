# Feature-Plan Workflow — Stages 2–3: Decompose and Score

Stage file for the `plan` skill (orchestrator: `SKILL.md`). Load this file after Stage 1 is complete.

**Next:** when Stage 3 is complete, load `${CLAUDE_SKILL_DIR}/stage-4-7-gates.md`.

---

## Stage 2 — Draft Candidate Plan

Stage 2 creates a candidate feature plan.

The candidate plan is not final and must not be written yet.

---

### 2.1 Choose Primary Slicing Method

Choose one primary slicing method based on the project type.

Then validate the candidate features against the other methods to detect missing foundations, duplicated scope, and unreachable journeys.

| Project Type | Primary Slicing Method | Secondary Validation |
|---|---|---|
| User-facing application | Journey-based | Capability, component, infrastructure |
| Backend API | Capability-based | Integration, consumer journey, data surface |
| CLI tool | Journey-based | Command surface, capability |
| SDK/library | Capability-based | Public API surface, consumer journey |
| Infrastructure/IaC | Infrastructure-based | Deployment lifecycle, operational journey |
| Brownfield refactor | Component-based | Risk, user impact, dependency graph |
| Integration-heavy feature | Integration-based | Capability, failure modes, data contracts |

---

### 2.2 Extract Candidate Features

Draft candidate features from the project model.

A candidate feature may come from:

- user journey
- business capability
- architectural component
- integration boundary
- technical foundation
- data lifecycle
- operational requirement
- migration step

---

### 2.3 Apply Feature Boundary Principles

Each feature must satisfy these principles.

#### Right-Sized

A feature should fit into one downstream implementation session without forcing context compaction.

If it cannot honestly fit, split it before presenting. *(Exception: a consented
Stage-5.5 **Coarsening Lease** suspends this split for the named feature — see the
Coarsening Lease override in §3.5.)*

---

#### Clear Boundaries

Feature scope should not heavily overlap.

If two features share more than approximately 50% of their implementation scope, merge or re-slice them.

---

#### Independently Valuable or Verifiable

Each feature must either:

- deliver user-visible or stakeholder-visible value, or
- create a technical foundation that can be validated independently and consumed later.

---

#### Dependency-Ordered

Foundation and enabling features should come before dependent features.

Hard dependencies must point backward in final ship order.

---

#### Explicit Exclusions

Every feature should state important non-goals when they prevent scope creep.

Examples:

```text
Excluded:
- Full audit dashboard
- Multi-tenant permissions
- Bulk import
- Production payment capture
```

---

### 2.4 Normalize Candidate Features

Before scoring, normalize the feature set.

Check for:

- duplicate features
- overlapping scope
- hidden mega-features
- missing foundation features
- missing design-foundation feature (a user-facing app with no existing design system needs one — see the Interface Foundation Gate, Stage 7.8)
- missing integration wrapper features
- missing persistence or migration features
- features that only exist because of artifact overhead
- features that cannot be tested independently
- features that are only implementation tasks, not feature-level slices

If a candidate is too small, merge it.

If a candidate is too large, split it.

If a candidate is vague, clarify or convert it into open unknowns.

---

## Stage 3 — Score Candidate Features

Stage 3 scores each candidate feature using independent signals.

---

### 3.1 Complexity Rubric

Complexity measures implementation scope.

A feature's intrinsic Complexity is the highest tier matched by any sizing dimension.

#### Sizing Dimensions

| Dimension | Simple | Moderate | Complex |
|---|---:|---:|---:|
| Public interaction surfaces | ≤ 2 | ≤ 5 | ≤ 10 |
| Data surfaces | 0–1 | ≤ 3 | ≤ 6 |
| Integration boundaries | 0 | ≤ 2 | ≤ 4 |
| Cross-cutting concerns | 0 | ≤ 1 | ≥ 2 |
| Fits in one implementation session | yes | yes | yes |

Examples:

| Dimension | Examples |
|---|---|
| Public interaction surfaces | UI screen, route, endpoint, CLI command, exported SDK function, webhook handler |
| Data surfaces | table, collection, migration, event schema, message contract, search index |
| Integration boundaries | auth provider, external API, queue, filesystem, database, object storage, runtime hook |
| Cross-cutting concerns | security, persistence, observability, i18n, accessibility, design system, performance, caching |

If a feature exceeds the Complex column on any dimension, split it before presenting.

If a feature cannot fit in one implementation session, split it before presenting.

---

### 3.2 Brownfield Bump Rule

The project-level Brownfield friction tier can adjust feature complexity.

Rule:

```text
If Brownfield friction is High, floor Simple features to Moderate.
Low and Medium Brownfield friction impose no floor.
```

Record both values:

```yaml
intrinsic_complexity: Simple
brownfield_adjusted_complexity: Moderate
brownfield_reason: "High Brownfield friction due to hot files and unclear baseline tests."
```

---

### 3.3 Reviewer-Trigger Pressure

Reviewer-trigger pressure measures how many downstream review concerns a feature is likely to activate.

Reviewer triggers:

```text
auth
authorization
secrets
persistence
framework wiring
runtime hooks
user-facing UI
accessibility
security-sensitive data
migration
deployment/runtime behavior
```

Rules:

```text
If reviewer_trigger_count >= 2:
    bump complexity by one tier, subject to the Cascade Cap.

If reviewer_trigger_count >= 4 and intrinsic_complexity == Complex:
    split the feature before presenting.
```

---

### 3.4 Cascade Cap

Brownfield pressure and reviewer-trigger pressure may raise final Complexity by at most one tier above intrinsic Complexity.

The cap prevents independent pressures from compounding too aggressively.

The cap does not force a Complex feature lower.

Examples:

| Intrinsic | Brownfield | Reviewer Pressure | Final |
|---|---|---|---|
| Simple | Low | none | Simple |
| Simple | High | none | Moderate |
| Simple | High | yes | Moderate |
| Moderate | High | yes | Complex |
| Complex | any | any | Complex or split if too broad |

---

### 3.5 Deterministic Complexity Algorithm

Use this algorithm to calculate final Complexity.

```pseudo
for each feature:
    intrinsic = max(
        score_public_interaction_surfaces(feature),
        score_data_surfaces(feature),
        score_integration_boundaries(feature),
        score_cross_cutting_concerns(feature)
    )

    if exceeds_complex_threshold(feature):
        split_feature_before_presenting()

    if cannot_fit_in_one_impl_session(feature):
        split_feature_before_presenting()

    brownfield_adjusted = intrinsic

    if brownfield_friction == High and intrinsic == Simple:
        brownfield_adjusted = Moderate

    reviewer_adjusted = brownfield_adjusted

    if reviewer_trigger_count(feature) >= 2:
        reviewer_adjusted = bump_one_tier(reviewer_adjusted)

    if intrinsic == Complex and reviewer_trigger_count(feature) >= 4:
        split_feature_before_presenting()

    final_complexity = min(
        reviewer_adjusted,
        bump_one_tier(intrinsic)
    )

    record:
        intrinsic_complexity
        brownfield_adjusted_complexity
        reviewer_trigger_count
        final_complexity
```

**Coarsening Lease override (consented).** When a Stage-5.5 *Coarsening Lease* names a
feature (or requests "coarsest viable"), the `cannot_fit_in_one_impl_session` and
`exceeds_complex_threshold` **splits are suspended for that feature** — keep it merged
and record `session_fit: consented-coarsened` on its sizing block instead of splitting.
This stays **deterministic**: the lease is an explicit recorded input, so final
Complexity remains a pure function of *(feature + lease)* — the artifact is still
reproducible given the same inputs. Every other rule (Brownfield floor, reviewer-trigger
bump, the Cascade Cap, Risk-Profile) applies unchanged, and the oversize is **flagged,
never silent**. Absent a lease, the splits apply exactly as written above.

---

### 3.6 Risk-Profile

Risk-Profile measures uncertainty, not size.

Assign `low`, `medium`, or `high`.

Use the highest matched value across these dimensions.

| Dimension | Low | Medium | High |
|---|---|---|---|
| Unknown-resolution-cost | none | hour-scale spike to resolve | investigation required before meaningful spec exists |
| Failure-blast-radius | this feature only | one or two downstream features | cascades across the chain; re-specs needed |
| Dependency-volatility | none external | one external behavior | multiple external behaviors the team cannot control |

Risk-Profile does not count toward the Cascade Cap.

By default, at most one feature per plan should carry `Risk-Profile: high`.

If more than one feature is genuinely high-risk, each high-risk feature must include a one-sentence justification under Notes, and the plan must explain why re-slicing did not concentrate or reduce the risk.

---

### 3.7 Boundary-Owner

Assign `Boundary-Owner` only when a feature is the single chokepoint for a project-wide concern.

**Allowed categories:** the two families defined in `SKILL.md` → Core Concepts → *Boundary-Owner* — cross-cutting concern owners (`security` · `secrets` · `persistence` · `i18n` · `accessibility`) and interface-foundation owners (`design-system`, the family extends on demand). Each is required only when the concern or surface is present; the `design-system` owner is enforced by the Interface Foundation Gate (Stage 7.8). Do not pre-add unused categories.

Rules:

- A feature may own zero, one, or multiple boundary categories only when justified.
- A category may appear in at most one feature.
- If two features claim the same category, the plan is mis-sliced.
- A feature that merely touches a concern does not automatically own it.

---

### 3.8 Open-Unknowns

Open-Unknowns are plan-time questions the workflow cannot answer.

Rules:

- Maximum 5 per feature.
- Each entry must be a one-line question.
- Each question must be forwarded to the downstream specification stage.
- More than 5 Open-Unknowns means the feature is probably mis-scoped and must be re-cut or clarified.

Good examples:

```text
- Which identity provider should be used for admin login?
- Should failed imports be retryable or manually corrected?
- What is the canonical source of customer status?
```

Bad examples:

```text
- Auth is unclear.
- Import might be risky.
- Need to think about customer status.
```

---

