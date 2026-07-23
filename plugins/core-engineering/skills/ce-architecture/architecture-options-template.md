# Solution Architecture Options Report

Use this template only in `explore:<draft-slug>` mode. Write each complete
workbench revision to
`docs/plans/.drafts/<slug>/architecture-options.md` before returning to the
Architecture Direction Selection gate. The report is the human-readable
decision surface; the canonical JSON returned to `/core-engineering:ce-plan`
remains the machine authority.

Do not omit a section because its answer is inconvenient. Use `None — <basis>`
or `Unknown — <cost and next check>` when that is the truthful result. Render
all generated directions, including eliminated and unresolved comparators.
Escape all source-derived and human-provided Markdown control characters;
never copy raw HTML, fence markers, headings, or link targets from untrusted
content into the rendered decision surface.

````markdown
# Solution Architecture Options — <project_slug>

> Decision status: awaiting-selection
>
> Workbench revision: <positive integer>
>
> Purpose: compare and iteratively refine complete solution directions before detailed work decomposition.
> Authority: decision support only. This report does not approve a final architecture baseline, security/compliance posture, implementation, release, or deployment.
> Snapshot rule: before selection, a revised report replaces this file and carries the prior hash and change ledger below. After selection, the sibling `architecture-selection.json` binds the final bytes.

Review this report before answering **Architecture Direction Selection**.

## What Needs Your Decision

- **Decision:** <the exact whole-solution direction choice>
- **Why now:** <how this choice changes decomposition>
- **Recommendation:** <Axx — title, or no defensible recommendation>
- **Recommendation basis:** <requirements-fit trade-off and leader-changing condition, or none>
- **Confidence / sensitivity:** <confidence> / <stable, unstable, or not-applicable>
- **Decision owner / authority:** <person or role and why this actor may bind the planning direction>
- **Current constraints:** <concise hard-constraint summary, including unknowns>
- **Cost if wrong:** <specific delivery, operational, security, migration, or reversibility consequence>
- **Material gaps and inferences:** <gap/inference, impact, and next check, or explicit none>

## Evaluation Frame

**Intent:** <locked project intent>

**Architecture applicability:** required | recommended

### Decision Owner

| Identity or role | Authority basis |
|---|---|
| <exact decision_owner.identity_or_role> | <exact decision_owner.authority_basis> |

**Non-goals:**

- <non-goal>

### Architecture Driver Screen

| Driver | Verdict | Basis | Evidence |
|---|---|---|---|
| <canonical driver id> | positive / negative / unknown | <basis> | <source> |

### Accepted Decisions

| Reference | Accepted decision summary |
|---|---|
| <docs/adr/... or explicit none> | <summary or basis> |

### Capabilities

| ID | Outcome | Actors | Data | Integrations | Observable |
|---|---|---|---|---|---|
| C01 | <outcome> | <actors> | <data> | <integrations> | <observable> |

### Journeys

| ID | Outcome | Actors | Capability trace | Steps | Observable |
|---|---|---|---|---|---|
| J01 | <outcome> | <actors> | C01 | <steps> | <observable> |

### Quality Scenarios

| ID | Attribute | Stimulus / environment | Required response and target | Priority | Evidence |
|---|---|---|---|---|---|
| QA01 | <attribute> | <stimulus / environment> | <response / target> | <priority> | <source> |

## Hard-Constraint Screen

Show this before weighted scores. `unknown` is unresolved and cannot be
selected; a weighted strength never compensates for `fail` or `unknown`.

| Constraint | Authority and basis | A01 | A02 | A03 | A04 |
|---|---|---|---|---|---|
| HC01 — <constraint> | <authority / basis> | pass — <basis> | fail — <basis> | N/A | N/A |

## Weighted Comparison

Weights are planning judgments, not facts. Show all six criteria, their bases,
every eligible option's full vector, the option-specific basis for every score,
the composite, evidence state, confidence, and the leader-changing sensitivity
condition when one exists.

| Criterion | Weight | Basis | A01 score / evidence | A02 score / evidence | A03 | A04 |
|---|---:|---|---|---|---|---|
| requirements-fit | <weight> | <criterion basis> | <score / score basis / state / source> | <score / score basis / state / source> | N/A | N/A |
| quality-attribute-fit | <weight> | <criterion basis> | <score / score basis / state / source> | <score / score basis / state / source> | N/A | N/A |
| repository-fit | <weight> | <criterion basis> | <score / score basis / state / source> | <score / score basis / state / source> | N/A | N/A |
| evolvability | <weight> | <criterion basis> | <score / score basis / state / source> | <score / score basis / state / source> | N/A | N/A |
| operability | <weight> | <criterion basis> | <score / score basis / state / source> | <score / score basis / state / source> | N/A | N/A |
| delivery-feasibility | <weight> | <criterion basis> | <score / score basis / state / source> | <score / score basis / state / source> | N/A | N/A |
| **Composite** | **1.0** |  | **<score>** | **<score>** | N/A | N/A |

**Sensitivity:** <stable/unstable/not-applicable and exact witness or basis>

**Recommendation confidence and basis:** <confidence> — <exact recommendation basis>

## Direction A01 — <title>

**Eligibility:** eligible | eliminated by HCxx | unresolved at HCxx  
**Option hash:** `<option_sha256>`  
**Confidence:** high | medium | low | not-applicable  
**Summary:** <complete direction summary>  
**Key gain:** <requirement-linked advantage>  
**Key cost / commitment:** <most important trade-off or irreversible commitment>

| Architecture dimension | Complete direction detail |
|---|---|
| Responsibilities and boundaries | <all rows> |
| Runtime and deployment | <all rows> |
| Data ownership | <all rows> |
| Integrations and failure behavior | <all rows> |
| Trust, residency, and security | <all rows> |
| Quality tactics | <all rows, traced to QA ids> |
| Migration and evolution | <all rows> |
| Capability implications | <all Cnn/Jnn implications> |
| Assumptions | <all assumptions> |
| Irreversible commitments | <all commitments> |

### Commitment Index

| Dimension | Ordinal | Statement SHA-256 | Exact statement |
|---|---|---|---|
| responsibilities_and_boundaries | 1 | `<sha256>` | <exact first string in that option array> |

Emit exactly one row for every string in the ten direction arrays. `Ordinal`
is one-based within its dimension. `Statement SHA-256` is the lowercase SHA-256
of the exact UTF-8 statement bytes with no added newline. This derived index is
review support; the canonical arrays and option hash remain the selection
authority.

### Trace and Evidence

- **Capabilities / journeys:** <every Cnn and Jnn>
- **Constraint verdicts:** <every HCnn verdict and basis>
- **Score vector:** <all six criterion scores, option-specific bases, and evidence states, or ineligibility basis>

<Repeat the complete direction section for every Axx in id order.>

## Eliminated, Unresolved, and Uncarried Directions

| Direction | Disposition | Reason | Evidence or next check |
|---|---|---|---|
| <Axx or concise uncarried label> | eliminated / unresolved / dominance-pruned | <constraint or reason> | <source or next check> |

## Evidence Sources

| Path | Kind | SHA-256 |
|---|---|---|
| <repository-relative path> | <kind> | `<sha256>` |

## Decision Workbench Audit

Carry every prior row forward. Record questions even when they do not change
the comparison. A frame-change request records the exact
`decision-frame-delta`; the next revision records how the refreshed planning
input changed the analysis. For a changed or superseded option, include its
prior option hash, concise direction summary, and disposition reason in the
response/change cell.

| Revision | Event | Human input / question | Response or resulting change | Prior report SHA-256 |
|---:|---|---|---|---|
| 1 | initial-synthesis | Initial comparison requested | <initial option-set and recommendation summary> | None — initial revision |
| <n> | question / frame-change / option-change / alternative-added | <exact human input> | <answer and recomputed disposition> | `<previous report sha256>` |

## Machine-Readable Comparison Projection

Include the exact selection-independent projection below in addition to the
human-readable tables. Populate every array/object fully from the current
revision's option set; never summarize or omit rows here. The schema-v2 selection linter
parses this visible JSON and requires exact equality before decomposition. The
workflow separately recomputes the displayed Commitment Index from those
canonical arrays before the gate; the table is not a second selection
authority.

```json
{
  "report_projection_schema_version": 1,
  "project_slug": "<project_slug>",
  "exploration_id": "<exploration_id>",
  "source_capability_revision": 1,
  "source_exploration_attempt": 1,
  "source_input_sha256": "<source_input_sha256>",
  "evaluation_frame": "<complete evaluation_frame object>",
  "blocking_decision": null,
  "sources": "<complete sources array>",
  "evidence_fingerprint": "<evidence_fingerprint>",
  "criteria": "<complete criteria array>",
  "hard_constraints": "<complete hard_constraints array>",
  "options": "<complete options array including hashes>",
  "eliminated_options": "<complete eliminated_options array>",
  "option_set_sha256": "<option_set_sha256>",
  "recommendation": "<complete recommendation object>"
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
| Workbench revision | `<positive integer>` |
| Project slug | `<project_slug>` |
| Capability revision | `<source_capability_revision>` |
| Exploration attempt | `<source_exploration_attempt>` |
| Exploration id | `<exploration_id>` |
| Source input SHA-256 | `<source_input_sha256>` |
| Evidence fingerprint | `<evidence_fingerprint>` |
| Option-set SHA-256 | `<option_set_sha256>` |
| Gate locator | `Gate <parent_gate_index> of <parent_gate_total> — Architecture Direction Selection` |
| Report file SHA-256 | Printed beside the path after the workflow re-reads this file; excluded from this self-referential table. |
````

`Human Decision` remains exactly `awaiting-selection` in every workbench
revision. Before selection, rewrites must increment the revision, preserve the
audit rows, and bind the prior report hash. After the human selects, do not
rewrite the final report: schema-v2 `architecture-selection.json` records the
choice and binds that exact SHA-256.
