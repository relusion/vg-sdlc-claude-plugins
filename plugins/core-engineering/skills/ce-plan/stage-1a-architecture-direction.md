# Stage 1A — Architecture direction

Run this stage before feature decomposition. It decides whether a direction is
load-bearing and, when it is, delegates comparison and human selection to
`/core-engineering:ce-architecture`.

Planning owns the decision frame and later feature cut. Architecture owns option
generation, comparison, recommendation, and the iterative direction workbench.
The human owns selection. A selected planning direction is not yet a published
architecture baseline or ADR.

## 1A.1 Build the capability frame

Set `capability_revision: 1` for a new run. Increment it when intent, non-goals,
capabilities, journeys, hard constraints, quality scenarios, accepted
decisions, material gaps, drivers, criteria, decision ownership, or evidence
bytes change.

Create no provisional features here.

- Capabilities use `C01`, `C02`, … and record outcome, actors, data,
  integrations, and observable result.
- Journeys use `J01`, `J02`, … and record outcome-level steps and capability
  references, not feature ids or ship order.
- Hard constraints have an id, statement, evidence-backed basis, authority, and
  consequence. Preferences are not hard constraints.
- Quality scenarios record attribute, stimulus, environment, response, literal
  target or `unknown`, priority, and evidence. Never invent a numeric target.
- Decision ownership records exactly
  `{identity_or_role, authority_basis}`. Inspect repository rules, the brief,
  accepted ADRs, and team ownership evidence first. Ask only when the approver
  or authority basis remains ambiguous. Both values must be substantive;
  `human`, `TBD`, `unknown`, and template placeholders are invalid.

## 1A.2 Screen architecture applicability

Record every driver as `positive`, `negative`, or `unknown`, with basis and
evidence:

| Load-bearing driver id |
|---|
| `explicit-architecture-deliverable` |
| `multi-runtime-or-deployment-boundary` |
| `cross-feature-durable-or-async-flow` |
| `shared-data-ownership-or-migration` |
| `trust-residency-or-sensitive-boundary` |
| `shared-protocol-or-schema` |
| `platform-or-topology-choice` |
| `architecture-determining-nfr` |
| `contested-cross-feature-owner` |

When every load-bearing driver is negative, also evaluate
`team-policy-recommendation`, `planned-reuse-recommendation`, and
`baseline-preference`.

Classify:

- `required` when a load-bearing driver is positive or a material driver cannot
  yet be classified safely;
- `recommended` when all load-bearing drivers are negative and a recommendation
  driver is positive;
- `not-required` when every load-bearing driver is evidenced negative and no
  material architecture uncertainty remains.

An unknown that can be cheaply resolved should be investigated first. A
load-bearing unknown that cannot be resolved routes to the evidence owner or
parks; do not disguise it as a direction choice.

For `not-required`, record the complete negative screen and rationale in
scratch, then continue without a gate or architecture invocation. Final Plan
Approval will bind the eventual `not-applicable` disposition. A deterministic
negative is evidence, not a separate human attestation.

## 1A.3 Build the comparison criteria

Use exactly these criteria so deterministic option validation remains stable:

| Criterion id | Evaluates |
|---|---|
| `requirements-fit` | capabilities and journeys |
| `quality-attribute-fit` | sourced quality scenarios |
| `repository-fit` | observed stack, conventions, boundaries, and ADRs |
| `evolvability` | reversibility, coupling, and stated later scope |
| `operability` | failure isolation, observability, and support burden |
| `delivery-feasibility` | credible build/migration path and delivery risk |

Each criterion has a numeric non-negative weight and source-backed basis; the
weights sum to `1.0`. Hard constraints remain non-compensatory. Treat weights
as adjustable planning judgments, not facts.

## 1A.4 Write the exploration input

For `required` and `recommended`, write canonical UTF-8 JSON with sorted keys
and a trailing newline to:

```text
docs/plans/.drafts/<slug>/architecture-exploration.json
```

Use the architecture exploration schema:

```text
schema_version, project_slug, capability_revision, exploration_attempt
parent_gate_index, parent_gate_total
project_intent, non_goals, decision_owner, architecture_applicability, driver_screen
accepted_decisions, material_gaps, capabilities, journeys
hard_constraints, quality_attribute_scenarios, criteria, sources
```

Requirements:

- `schema_version` is `1`;
- `exploration_attempt` starts at `1` and increases for every rewritten request,
  including an evidence-only retry;
- parent gate fields point to the plan's one Architecture Direction locator and
  are excluded from the decision-relevant input hash;
- all ids and references resolve inside the object;
- `decision_owner.identity_or_role` names the person or accountable role that
  may bind this planning direction, and `authority_basis` names why;
- all twelve driver ids appear once in canonical order;
- all six criteria appear once;
- every source is a repository-relative regular non-symlink file with its
  current SHA-256 and kind
  `brief|brief-sidecar|adr|repository|planning-input`;
- missing or unsafe evidence is a named material gap, never silently omitted.

The canonical `source_input_sha256` is the SHA-256 of the parsed
decision-relevant object serialized with sorted keys, compact separators,
Unicode preserved, and finite numbers. Never reuse an attempt number for
different bytes.

## 1A.5 Run the architecture workbench

Invoke:

```text
/core-engineering:ce-architecture explore:<slug>
```

Do not reproduce option generation in planning. The architecture workflow must
write and lint the complete comparison at:

```text
docs/plans/.drafts/<slug>/architecture-options.md
```

Before any selection it must show, both in that artifact and in the
conversation:

- what needs a decision and why now;
- a comparison summary;
- every eligible option and every eliminated or uncarried option;
- hard-constraint results and weighted scores;
- repository evidence and its demonstrated/read/inferred/unknown state;
- reasoning, assumptions, material unknowns, and cost if wrong;
- the exact decision owner and authority basis;
- trade-offs, operational and migration consequences, and irreversible
  commitments;
- recommendation, confidence, and sensitivity to weights or uncertain
  evidence.

Use one plan locator:

```text
Gate N of M — Architecture Direction Selection
```

The workbench is conversational, not one-shot. Under the same locator the human
may:

- ask a question about any option or evidence;
- request an option revision or another credible alternative;
- change a preference or comparison weight;
- change a requirement, driver, source, quality scenario, hard constraint, or
  decision owner;
- select one eligible direction with a non-empty rationale;
- route to an evidence/decision owner, defer a `recommended` route, park, or
  abort.

Every answered question and every option-only revision remains inside
architecture and appends a new persisted workbench revision containing the
prior report hash, request or question, and result—even when no score changes.
A requirement, hard-constraint, criterion-weight, driver, source, quality
scenario, or decision-owner change returns a structured
`decision-frame-delta` to this stage. Apply only the recorded human-requested
delta, increment `capability_revision`, always increment
`exploration_attempt`, rewrite the input, reinvoke exploration, and resume the
same gate locator.

No question or adjustment counts as approval. Required architecture cannot be
deferred. Recommended architecture may be explicitly deferred with rationale;
that decision is human-owned and remains visible at Final Plan Approval.

## 1A.6 Accept only a fresh terminal result

Accept `direction-selected`, or `deferred` only for `recommended`.
`requires-evidence`, `requires-decision`, `blocked`, and `human-aborted` stop
before decomposition or route to the named owner. A bounded technical fork may
compose `/core-engineering:ce-decide`; whole-solution selection may not.

For a selected result, confirm:

- project, capability revision, attempt, and canonical input hash match;
- source hashes and evidence fingerprint are current;
- the returned evaluation frame preserves the current input;
- option-set and per-option hashes validate;
- `architecture-options.md` is the current linted pre-selection report and its
  hash matches the result;
- `selection.decided_by` is `human`,
  `selection.approved_by` exactly matches
  `evaluation_frame.decision_owner.identity_or_role`, the selected option is
  eligible, and its id/hash and non-empty rationale match;
- `next_owner` is `ce-plan`.

Delegation is not inferred. If another identity or role must approve, return to
the same workbench locator, revise `decision_owner` and its authority basis
through a decision-frame delta, recompute, and ask again.

Write the returned canonical JSON verbatim to:

```text
docs/plans/.drafts/<slug>/architecture-selection.json
```

Then run:

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/architecture-selection-lint.py" \
  docs/plans/.drafts/<slug>/architecture-selection.json \
  --repo-root . --require-current-schema --json
```

- exit 0: checkpoint the selected/deferred state and continue;
- exit 1: repair or rerun the workbench;
- exit 2 or no result: park with a coverage gap.

A human cannot waive this structural/freshness check. Only exit 0 authorizes
decomposition for an explored route.

## 1A.7 Freshness back-edge

Any later change to the capability frame, decision criteria, source hashes, or
selected option bytes invalidates the selection. Return here with a Back-Edge
Summary, increment the relevant revision and attempt, and rerun the workbench
before re-slicing features.

Candidate-only implementation detail that leaves the decision frame and
selected direction unchanged belongs to Stage 5A.

**Next:** load `${CLAUDE_SKILL_DIR}/stage-2-3-decompose-score.md`.
