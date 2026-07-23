# Solution Architecture Options — team-invitations-rbac

> Decision status: awaiting-selection
> Workbench revision: 1

## What Needs Your Decision

- **Decision:** Choose the whole-solution direction that will bind decomposition.
- **Why now:** The direction changes component, migration, and verification work.
- **Recommendation:** A01 — strongest fit
- **Recommendation basis:** A02 fails the authorization-before-persistence constraint, leaving A01 as the sole eligible direction.
- **Confidence / sensitivity:** medium / not-applicable
- **Decision owner / authority:** Repository Architecture Owner — This evaluation fixture assigns architecture applicability and direction approval to the repository architecture owner.
- **Cost if wrong:** Rework boundaries, migration tasks, and operational controls.
- **Material gaps and inferences:** None — the approved evidence covers this comparison.

## Evaluation Frame

```json
{"accepted_decisions": [], "architecture_applicability": "required", "capabilities": [{"actors": ["administrator", "invitee"], "data": ["invitation", "membership"], "id": "C01", "integrations": ["existing application and PostgreSQL"], "observable": "An accepted invitation creates one authorized membership.", "outcome": "Authorized administrators invite users who become team members."}], "decision_owner": {"authority_basis": "This evaluation fixture assigns architecture applicability and direction approval to the repository architecture owner.", "identity_or_role": "Repository Architecture Owner"}, "driver_screen": [{"basis": "The workflow requires a reviewed cross-feature solution baseline.", "evidence": ["docs/briefs/team-invitations-rbac.md"], "id": "explicit-architecture-deliverable", "verdict": "positive"}, {"basis": "The accepted scope retains one application runtime.", "evidence": ["docs/briefs/team-invitations-rbac.md"], "id": "multi-runtime-or-deployment-boundary", "verdict": "negative"}, {"basis": "The bounded fixture has no asynchronous flow.", "evidence": ["docs/briefs/team-invitations-rbac.md"], "id": "cross-feature-durable-or-async-flow", "verdict": "negative"}, {"basis": "Invitation acceptance and membership writes share transactional ownership concerns.", "evidence": ["docs/briefs/team-invitations-rbac.md"], "id": "shared-data-ownership-or-migration", "verdict": "positive"}, {"basis": "Authorization must precede protected membership and invitation writes.", "evidence": ["docs/briefs/team-invitations-rbac.md"], "id": "trust-residency-or-sensitive-boundary", "verdict": "positive"}, {"basis": "No new cross-runtime protocol is required.", "evidence": ["docs/briefs/team-invitations-rbac.md"], "id": "shared-protocol-or-schema", "verdict": "negative"}, {"basis": "The repository topology is retained.", "evidence": ["docs/briefs/team-invitations-rbac.md"], "id": "platform-or-topology-choice", "verdict": "negative"}, {"basis": "The recorded quality targets do not force another topology.", "evidence": ["docs/briefs/team-invitations-rbac.md"], "id": "architecture-determining-nfr", "verdict": "negative"}, {"basis": "Feature ownership is explicit in the plan evidence.", "evidence": ["docs/briefs/team-invitations-rbac.md"], "id": "contested-cross-feature-owner", "verdict": "negative"}, {"basis": "No separate team policy recommendation is needed.", "evidence": ["docs/briefs/team-invitations-rbac.md"], "id": "team-policy-recommendation", "verdict": "negative"}, {"basis": "The capability is bounded to this plan.", "evidence": ["docs/briefs/team-invitations-rbac.md"], "id": "planned-reuse-recommendation", "verdict": "negative"}, {"basis": "Required drivers already determine applicability.", "evidence": ["docs/briefs/team-invitations-rbac.md"], "id": "baseline-preference", "verdict": "negative"}], "journeys": [{"actors": ["administrator", "invitee"], "capability_refs": ["C01"], "id": "J01", "observable": "Repeated acceptance never duplicates membership.", "outcome": "A valid invitation is accepted safely.", "steps": ["Authorize invitation creation", "Persist invitation", "Accept invitation transactionally"]}], "material_gaps": [], "non_goals": ["Email delivery and production deployment topology"], "project_intent": "Add team invitations and role-based authorization without splitting the existing application runtime.", "quality_attribute_scenarios": [{"attribute": "security", "environment": "Normal service operation", "evidence": ["docs/briefs/team-invitations-rbac.md"], "id": "QA01", "priority": "must", "response": "The write is rejected before persistence.", "stimulus": "An unauthorized caller attempts an invitation write.", "target": "No unauthorized invitation or membership record is created."}]}
```

## Hard-Constraint Screen

```json
{"hard_constraints": [{"authority": "human-confirmed requirement", "basis": "The protected-write requirement cannot be traded against delivery convenience.", "id": "HC01", "statement": "Authorization must execute before invitation or membership persistence."}], "option_verdicts": [{"constraint_verdicts": [{"basis": "The authorization component is invoked before all protected persistence.", "constraint_id": "HC01", "verdict": "pass"}], "option_id": "A01"}, {"constraint_verdicts": [{"basis": "Pending invitations are persisted before the required authorization decision.", "constraint_id": "HC01", "verdict": "fail"}], "option_id": "A02"}]}
```

## Weighted Comparison

```json
{"criteria": [{"basis": "Preserve the invitation and RBAC outcomes.", "id": "requirements-fit", "weight": 0.25}, {"basis": "Make authorization and idempotency explicit.", "id": "quality-attribute-fit", "weight": 0.2}, {"basis": "Prefer the established single-runtime repository shape.", "id": "repository-fit", "weight": 0.15}, {"basis": "Keep logical boundaries independently evolvable.", "id": "evolvability", "weight": 0.15}, {"basis": "Retain one application operational boundary.", "id": "operability", "weight": 0.1}, {"basis": "Minimize migration and delivery risk.", "id": "delivery-feasibility", "weight": 0.15}], "option_scores": [{"confidence": "medium", "option_id": "A01", "scores": [{"basis": "Single runtime with explicit authorization and invitation boundaries scores 5/5 for requirements-fit on the cited evidence.", "criterion_id": "requirements-fit", "evidence": ["docs/briefs/team-invitations-rbac.md"], "evidence_state": "recorded", "score": 5}, {"basis": "Single runtime with explicit authorization and invitation boundaries scores 5/5 for quality-attribute-fit on the cited evidence.", "criterion_id": "quality-attribute-fit", "evidence": ["docs/briefs/team-invitations-rbac.md"], "evidence_state": "inferred", "score": 5}, {"basis": "Single runtime with explicit authorization and invitation boundaries scores 5/5 for repository-fit on the cited evidence.", "criterion_id": "repository-fit", "evidence": ["docs/briefs/team-invitations-rbac.md"], "evidence_state": "recorded", "score": 5}, {"basis": "Single runtime with explicit authorization and invitation boundaries scores 4/5 for evolvability on the cited evidence.", "criterion_id": "evolvability", "evidence": ["docs/briefs/team-invitations-rbac.md"], "evidence_state": "inferred", "score": 4}, {"basis": "Single runtime with explicit authorization and invitation boundaries scores 4/5 for operability on the cited evidence.", "criterion_id": "operability", "evidence": ["docs/briefs/team-invitations-rbac.md"], "evidence_state": "inferred", "score": 4}, {"basis": "Single runtime with explicit authorization and invitation boundaries scores 4/5 for delivery-feasibility on the cited evidence.", "criterion_id": "delivery-feasibility", "evidence": ["docs/briefs/team-invitations-rbac.md"], "evidence_state": "inferred", "score": 4}], "weighted_score": 4.6}, {"confidence": "not-applicable", "option_id": "A02", "scores": [], "weighted_score": null}], "recommendation": {"basis": "A02 fails the authorization-before-persistence constraint, leaving A01 as the sole eligible direction.", "confidence": "medium", "option_id": "A01", "sensitivity": "not-applicable", "sensitivity_witness": null}}
```

## Direction A01 — Single runtime with explicit authorization and invitation boundaries

**Option hash:** `5244376e42b49a22815fc86d460a1d826cedbd62b355875e3c15955783c22879`  
**Confidence:** medium  
**Summary:** Keep one deployable application and separate authorization, invitation, and persistence responsibilities logically.  

| Architecture dimension | Complete direction detail |
|---|---|
| Responsibilities and boundaries | Authorization owns capability checks; invitations owns invitation lifecycle. |
| Runtime and deployment | One application runtime with the existing PostgreSQL data store. |
| Data ownership | Invitation and membership writes remain explicit and transactionally coordinated. |
| Integrations and failure behavior | In-process authorization failure stops before persistence. |
| Trust, residency, and security | Every protected write crosses the authorization boundary first. |
| Quality tactics | Transactional acceptance provides idempotent membership creation. |
| Migration and evolution | No runtime migration; logical boundaries can later be extracted if evidence requires it. |
| Capability implications | C01 decomposes into authorization foundation followed by invitation delivery. |
| Assumptions | The existing runtime and database remain adequate for the recorded load. |
| Irreversible commitments | No irreversible infrastructure commitment is introduced. |

### Constraint and Score Detail

```json
{"confidence": "medium", "constraint_verdicts": [{"basis": "The authorization component is invoked before all protected persistence.", "constraint_id": "HC01", "verdict": "pass"}], "scores": [{"basis": "Single runtime with explicit authorization and invitation boundaries scores 5/5 for requirements-fit on the cited evidence.", "criterion_id": "requirements-fit", "evidence": ["docs/briefs/team-invitations-rbac.md"], "evidence_state": "recorded", "score": 5}, {"basis": "Single runtime with explicit authorization and invitation boundaries scores 5/5 for quality-attribute-fit on the cited evidence.", "criterion_id": "quality-attribute-fit", "evidence": ["docs/briefs/team-invitations-rbac.md"], "evidence_state": "inferred", "score": 5}, {"basis": "Single runtime with explicit authorization and invitation boundaries scores 5/5 for repository-fit on the cited evidence.", "criterion_id": "repository-fit", "evidence": ["docs/briefs/team-invitations-rbac.md"], "evidence_state": "recorded", "score": 5}, {"basis": "Single runtime with explicit authorization and invitation boundaries scores 4/5 for evolvability on the cited evidence.", "criterion_id": "evolvability", "evidence": ["docs/briefs/team-invitations-rbac.md"], "evidence_state": "inferred", "score": 4}, {"basis": "Single runtime with explicit authorization and invitation boundaries scores 4/5 for operability on the cited evidence.", "criterion_id": "operability", "evidence": ["docs/briefs/team-invitations-rbac.md"], "evidence_state": "inferred", "score": 4}, {"basis": "Single runtime with explicit authorization and invitation boundaries scores 4/5 for delivery-feasibility on the cited evidence.", "criterion_id": "delivery-feasibility", "evidence": ["docs/briefs/team-invitations-rbac.md"], "evidence_state": "inferred", "score": 4}], "weighted_score": 4.6}
```

## Direction A02 — Separate invitation runtime with eventual authorization

**Option hash:** `05893aa77f7e93ecbd9203fd0ce88669376addb21291ed00dd4734fcb8b15af4`  
**Confidence:** not-applicable  
**Summary:** Deploy invitation handling separately and persist pending invitations before centralized authorization reconciliation.  

| Architecture dimension | Complete direction detail |
|---|---|
| Responsibilities and boundaries | An invitation service owns invitation intake while the application retains authorization and membership. |
| Runtime and deployment | A separately deployed invitation runtime communicates with the existing application and PostgreSQL. |
| Data ownership | The invitation runtime persists pending invitation state before membership authorization is reconciled. |
| Integrations and failure behavior | Authorization unavailability permits pending invitation persistence for later reconciliation. |
| Trust, residency, and security | The new runtime introduces a service trust boundary around invitation intake. |
| Quality tactics | Asynchronous reconciliation isolates invitation intake from application availability. |
| Migration and evolution | Invitation ownership must migrate behind a new service contract and deployment. |
| Capability implications | C01 gains an asynchronous intake and reconciliation boundary. |
| Assumptions | Pending invitation persistence before authorization would be acceptable. |
| Irreversible commitments | A new runtime and service contract become operational commitments. |

### Constraint and Score Detail

```json
{"confidence": "not-applicable", "constraint_verdicts": [{"basis": "Pending invitations are persisted before the required authorization decision.", "constraint_id": "HC01", "verdict": "fail"}], "scores": [], "weighted_score": null}
```

## Eliminated, Unresolved, and Uncarried Directions

[{"constraint_ids": ["HC01"], "option_id": "A02", "reason": "This direction persists invitation state before satisfying the authorization-before-persistence constraint."}]

## Evidence Sources

[{"kind": "brief", "path": "docs/briefs/team-invitations-rbac.md", "sha256": "6c48d52ac4c4713cb27fbda8c4094077d64c760f4ea11ee14177796368267387"}]

## Decision Workbench Audit

| Revision | Event | Human input / question | Response or resulting change | Prior report SHA-256 |
|---:|---|---|---|---|
| 1 | initial-synthesis | Initial comparison requested | Initial option set and recommendation synthesized | None — initial revision |

## Machine-Readable Comparison Projection

```json
{
  "blocking_decision": null,
  "criteria": [
    {
      "basis": "Preserve the invitation and RBAC outcomes.",
      "id": "requirements-fit",
      "weight": 0.25
    },
    {
      "basis": "Make authorization and idempotency explicit.",
      "id": "quality-attribute-fit",
      "weight": 0.2
    },
    {
      "basis": "Prefer the established single-runtime repository shape.",
      "id": "repository-fit",
      "weight": 0.15
    },
    {
      "basis": "Keep logical boundaries independently evolvable.",
      "id": "evolvability",
      "weight": 0.15
    },
    {
      "basis": "Retain one application operational boundary.",
      "id": "operability",
      "weight": 0.1
    },
    {
      "basis": "Minimize migration and delivery risk.",
      "id": "delivery-feasibility",
      "weight": 0.15
    }
  ],
  "eliminated_options": [
    {
      "constraint_ids": [
        "HC01"
      ],
      "option_id": "A02",
      "reason": "This direction persists invitation state before satisfying the authorization-before-persistence constraint."
    }
  ],
  "evaluation_frame": {
    "accepted_decisions": [],
    "architecture_applicability": "required",
    "capabilities": [
      {
        "actors": [
          "administrator",
          "invitee"
        ],
        "data": [
          "invitation",
          "membership"
        ],
        "id": "C01",
        "integrations": [
          "existing application and PostgreSQL"
        ],
        "observable": "An accepted invitation creates one authorized membership.",
        "outcome": "Authorized administrators invite users who become team members."
      }
    ],
    "decision_owner": {
      "authority_basis": "This evaluation fixture assigns architecture applicability and direction approval to the repository architecture owner.",
      "identity_or_role": "Repository Architecture Owner"
    },
    "driver_screen": [
      {
        "basis": "The workflow requires a reviewed cross-feature solution baseline.",
        "evidence": [
          "docs/briefs/team-invitations-rbac.md"
        ],
        "id": "explicit-architecture-deliverable",
        "verdict": "positive"
      },
      {
        "basis": "The accepted scope retains one application runtime.",
        "evidence": [
          "docs/briefs/team-invitations-rbac.md"
        ],
        "id": "multi-runtime-or-deployment-boundary",
        "verdict": "negative"
      },
      {
        "basis": "The bounded fixture has no asynchronous flow.",
        "evidence": [
          "docs/briefs/team-invitations-rbac.md"
        ],
        "id": "cross-feature-durable-or-async-flow",
        "verdict": "negative"
      },
      {
        "basis": "Invitation acceptance and membership writes share transactional ownership concerns.",
        "evidence": [
          "docs/briefs/team-invitations-rbac.md"
        ],
        "id": "shared-data-ownership-or-migration",
        "verdict": "positive"
      },
      {
        "basis": "Authorization must precede protected membership and invitation writes.",
        "evidence": [
          "docs/briefs/team-invitations-rbac.md"
        ],
        "id": "trust-residency-or-sensitive-boundary",
        "verdict": "positive"
      },
      {
        "basis": "No new cross-runtime protocol is required.",
        "evidence": [
          "docs/briefs/team-invitations-rbac.md"
        ],
        "id": "shared-protocol-or-schema",
        "verdict": "negative"
      },
      {
        "basis": "The repository topology is retained.",
        "evidence": [
          "docs/briefs/team-invitations-rbac.md"
        ],
        "id": "platform-or-topology-choice",
        "verdict": "negative"
      },
      {
        "basis": "The recorded quality targets do not force another topology.",
        "evidence": [
          "docs/briefs/team-invitations-rbac.md"
        ],
        "id": "architecture-determining-nfr",
        "verdict": "negative"
      },
      {
        "basis": "Feature ownership is explicit in the plan evidence.",
        "evidence": [
          "docs/briefs/team-invitations-rbac.md"
        ],
        "id": "contested-cross-feature-owner",
        "verdict": "negative"
      },
      {
        "basis": "No separate team policy recommendation is needed.",
        "evidence": [
          "docs/briefs/team-invitations-rbac.md"
        ],
        "id": "team-policy-recommendation",
        "verdict": "negative"
      },
      {
        "basis": "The capability is bounded to this plan.",
        "evidence": [
          "docs/briefs/team-invitations-rbac.md"
        ],
        "id": "planned-reuse-recommendation",
        "verdict": "negative"
      },
      {
        "basis": "Required drivers already determine applicability.",
        "evidence": [
          "docs/briefs/team-invitations-rbac.md"
        ],
        "id": "baseline-preference",
        "verdict": "negative"
      }
    ],
    "journeys": [
      {
        "actors": [
          "administrator",
          "invitee"
        ],
        "capability_refs": [
          "C01"
        ],
        "id": "J01",
        "observable": "Repeated acceptance never duplicates membership.",
        "outcome": "A valid invitation is accepted safely.",
        "steps": [
          "Authorize invitation creation",
          "Persist invitation",
          "Accept invitation transactionally"
        ]
      }
    ],
    "material_gaps": [],
    "non_goals": [
      "Email delivery and production deployment topology"
    ],
    "project_intent": "Add team invitations and role-based authorization without splitting the existing application runtime.",
    "quality_attribute_scenarios": [
      {
        "attribute": "security",
        "environment": "Normal service operation",
        "evidence": [
          "docs/briefs/team-invitations-rbac.md"
        ],
        "id": "QA01",
        "priority": "must",
        "response": "The write is rejected before persistence.",
        "stimulus": "An unauthorized caller attempts an invitation write.",
        "target": "No unauthorized invitation or membership record is created."
      }
    ]
  },
  "evidence_fingerprint": "c935622ebd51b09d06ac75366785604b00aedb03c63ad42b7f19f90e868f86bc",
  "exploration_id": "AEX-18cb57213ed7",
  "hard_constraints": [
    {
      "authority": "human-confirmed requirement",
      "basis": "The protected-write requirement cannot be traded against delivery convenience.",
      "id": "HC01",
      "statement": "Authorization must execute before invitation or membership persistence."
    }
  ],
  "option_set_sha256": "18cb57213ed706814bf38c66dba8a0434f8aac24fd0abe31eafeb399f1c8a530",
  "options": [
    {
      "assumptions": [
        "The existing runtime and database remain adequate for the recorded load."
      ],
      "capability_implications": [
        "C01 decomposes into authorization foundation followed by invitation delivery."
      ],
      "confidence": "medium",
      "constraint_verdicts": [
        {
          "basis": "The authorization component is invoked before all protected persistence.",
          "constraint_id": "HC01",
          "verdict": "pass"
        }
      ],
      "data_ownership": [
        "Invitation and membership writes remain explicit and transactionally coordinated."
      ],
      "integrations_and_failure": [
        "In-process authorization failure stops before persistence."
      ],
      "irreversible_commitments": [
        "No irreversible infrastructure commitment is introduced."
      ],
      "migration_and_evolution": [
        "No runtime migration; logical boundaries can later be extracted if evidence requires it."
      ],
      "option_id": "A01",
      "option_sha256": "5244376e42b49a22815fc86d460a1d826cedbd62b355875e3c15955783c22879",
      "quality_tactics": [
        "Transactional acceptance provides idempotent membership creation."
      ],
      "responsibilities_and_boundaries": [
        "Authorization owns capability checks; invitations owns invitation lifecycle."
      ],
      "runtime_and_deployment": [
        "One application runtime with the existing PostgreSQL data store."
      ],
      "scores": [
        {
          "basis": "Single runtime with explicit authorization and invitation boundaries scores 5/5 for requirements-fit on the cited evidence.",
          "criterion_id": "requirements-fit",
          "evidence": [
            "docs/briefs/team-invitations-rbac.md"
          ],
          "evidence_state": "recorded",
          "score": 5
        },
        {
          "basis": "Single runtime with explicit authorization and invitation boundaries scores 5/5 for quality-attribute-fit on the cited evidence.",
          "criterion_id": "quality-attribute-fit",
          "evidence": [
            "docs/briefs/team-invitations-rbac.md"
          ],
          "evidence_state": "inferred",
          "score": 5
        },
        {
          "basis": "Single runtime with explicit authorization and invitation boundaries scores 5/5 for repository-fit on the cited evidence.",
          "criterion_id": "repository-fit",
          "evidence": [
            "docs/briefs/team-invitations-rbac.md"
          ],
          "evidence_state": "recorded",
          "score": 5
        },
        {
          "basis": "Single runtime with explicit authorization and invitation boundaries scores 4/5 for evolvability on the cited evidence.",
          "criterion_id": "evolvability",
          "evidence": [
            "docs/briefs/team-invitations-rbac.md"
          ],
          "evidence_state": "inferred",
          "score": 4
        },
        {
          "basis": "Single runtime with explicit authorization and invitation boundaries scores 4/5 for operability on the cited evidence.",
          "criterion_id": "operability",
          "evidence": [
            "docs/briefs/team-invitations-rbac.md"
          ],
          "evidence_state": "inferred",
          "score": 4
        },
        {
          "basis": "Single runtime with explicit authorization and invitation boundaries scores 4/5 for delivery-feasibility on the cited evidence.",
          "criterion_id": "delivery-feasibility",
          "evidence": [
            "docs/briefs/team-invitations-rbac.md"
          ],
          "evidence_state": "inferred",
          "score": 4
        }
      ],
      "summary": "Keep one deployable application and separate authorization, invitation, and persistence responsibilities logically.",
      "title": "Single runtime with explicit authorization and invitation boundaries",
      "trust_residency_and_security": [
        "Every protected write crosses the authorization boundary first."
      ],
      "weighted_score": 4.6
    },
    {
      "assumptions": [
        "Pending invitation persistence before authorization would be acceptable."
      ],
      "capability_implications": [
        "C01 gains an asynchronous intake and reconciliation boundary."
      ],
      "confidence": "not-applicable",
      "constraint_verdicts": [
        {
          "basis": "Pending invitations are persisted before the required authorization decision.",
          "constraint_id": "HC01",
          "verdict": "fail"
        }
      ],
      "data_ownership": [
        "The invitation runtime persists pending invitation state before membership authorization is reconciled."
      ],
      "integrations_and_failure": [
        "Authorization unavailability permits pending invitation persistence for later reconciliation."
      ],
      "irreversible_commitments": [
        "A new runtime and service contract become operational commitments."
      ],
      "migration_and_evolution": [
        "Invitation ownership must migrate behind a new service contract and deployment."
      ],
      "option_id": "A02",
      "option_sha256": "05893aa77f7e93ecbd9203fd0ce88669376addb21291ed00dd4734fcb8b15af4",
      "quality_tactics": [
        "Asynchronous reconciliation isolates invitation intake from application availability."
      ],
      "responsibilities_and_boundaries": [
        "An invitation service owns invitation intake while the application retains authorization and membership."
      ],
      "runtime_and_deployment": [
        "A separately deployed invitation runtime communicates with the existing application and PostgreSQL."
      ],
      "scores": [],
      "summary": "Deploy invitation handling separately and persist pending invitations before centralized authorization reconciliation.",
      "title": "Separate invitation runtime with eventual authorization",
      "trust_residency_and_security": [
        "The new runtime introduces a service trust boundary around invitation intake."
      ],
      "weighted_score": null
    }
  ],
  "project_slug": "team-invitations-rbac",
  "recommendation": {
    "basis": "A02 fails the authorization-before-persistence constraint, leaving A01 as the sole eligible direction.",
    "confidence": "medium",
    "option_id": "A01",
    "sensitivity": "not-applicable",
    "sensitivity_witness": null
  },
  "report_projection_schema_version": 1,
  "source_capability_revision": 1,
  "source_exploration_attempt": 1,
  "source_input_sha256": "765f0fa6984353e912abf467bd14a00e4765543e5244d9f9c5ddaff2a516a13a",
  "sources": [
    {
      "kind": "brief",
      "path": "docs/briefs/team-invitations-rbac.md",
      "sha256": "6c48d52ac4c4713cb27fbda8c4094077d64c760f4ea11ee14177796368267387"
    }
  ]
}
```

## Human Decision

| Field | Value |
|---|---|
| Status | awaiting-selection |
| Selected direction | Not selected |
| Selected option hash | Not selected |
| Decided by | Not selected |
| Approved by | Not selected |
| Rationale | Review the comparison above before choosing. |

## Integrity

| Field | Value |
|---|---|
| Report schema | 1 |
| Workbench revision | `1` |
| Project slug | `team-invitations-rbac` |
| Capability revision | `1` |
| Exploration attempt | `1` |
| Exploration id | `AEX-18cb57213ed7` |
| Source input SHA-256 | `765f0fa6984353e912abf467bd14a00e4765543e5244d9f9c5ddaff2a516a13a` |
| Evidence fingerprint | `c935622ebd51b09d06ac75366785604b00aedb03c63ad42b7f19f90e868f86bc` |
| Option-set SHA-256 | `18cb57213ed706814bf38c66dba8a0434f8aac24fd0abe31eafeb399f1c8a530` |
| Gate locator | `Gate 2 of 8 — Architecture Direction Selection` |
