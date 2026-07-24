# Stage 1A — Architecture direction

Run this stage before feature decomposition. It decides whether a direction is
load-bearing or explicitly requested and, when either is true, delegates
comparison and human selection to `/core-engineering:ce-architecture`.

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

A recommendation driver is positive only when repository policy or the
accountable human explicitly requests an architecture comparison now. Planned
reuse counts only when a named, evidenced consumer creates a present comparison
need. A generic possibility of future reuse, a model preference for producing a
baseline, or the mere availability of the architecture workflow is negative.

Classify:

- `required` when a load-bearing driver is positive or a material driver cannot
  yet be classified safely;
- `recommended` when all load-bearing drivers are negative and an explicit
  repository-policy or human opt-in makes a recommendation driver positive;
- `not-required` when every load-bearing driver is evidenced negative and no
  explicit opt-in or material architecture uncertainty remains.

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

Before any selection the complete artifact must show:

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

Conversation is a compact projection, not a second copy of the report. Show
only the decision and owner, an option comparison, decisive trade-offs and
eliminations, recommendation/confidence/sensitivity, material unknowns,
cost-if-wrong, and the artifact path/hash. The human can inspect the complete
reasoning, scores, evidence, and assumptions through the report or ask about
them at the same locator.

Use one plan locator:

```text
Gate N of M — Architecture Direction Selection
```

Never print that locator, label a comparison `awaiting-selection`, or imply a
direction can be selected until the complete report exists, has been re-read,
and passes `architecture-options-lint.py`. An interrupted or budget-exhausted
attempt remains `in-progress` or `blocked`; it may not promise to persist or
lint evidence after the human answers.

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

An ordinary answer that changes no evidence, reasoning, confidence, option, or
other decision-surface value stays conversational at the same gate. Persist and
re-lint a new audit-linked workbench revision only when an answer changes that
surface or the human explicitly adopts it as decision basis. Option-only
revisions remain inside architecture. A requirement, hard-constraint,
criterion-weight, driver, source, quality scenario, or decision-owner change
returns a typed, exact-before/after
`decision-frame-delta` to this stage only after architecture has rewritten the
same report as a validated, non-selectable `frame-change-pending` checkpoint.
The pending envelope binds `prior_report_sha256` to the last selectable report
H1; the current pending report has a distinct hash H2. A hidden draft-local
control receipt is exclusively persisted before H1 is replaced and binds the
target, H1, precomputed H2, pending id, and request/delta hashes. It is recovery
control state, not a second decision artifact.

On a continuation or interrupted run, do not reconstruct the delta from chat.
Run `architecture-workbench.py resume-frame-change` against the report with
`--expected-report-sha256 <H2>`. Require exit 0 and verify its
`selectable_prior_report_sha256` equals H1 while both
`pending_report_sha256` and `next_expected_previous_sha256` equal H2. Apply
only the extracted human-requested delta. When H2 was not retained because
stdout was lost, use `--recover-persisted`; it must validate the independent
receipt and report before returning H1, H2, and the typed delta. A
receipt-before-report interruption validates unchanged H1 and discards the
unactivated receipt; a stale receipt after validated H3 is consumed only after
the H2→H3 audit binding is proven.

Increment `capability_revision`, always increment `exploration_attempt`, rewrite
the input, and reinvoke exploration. The complete recomputation must revise the
pending report with `--expected-previous-sha256 <H2>`—never H1—and carry the
exact request in a `frame-change` audit event. The helper requires the new
canonical frame to equal H1 plus every typed `after` and the two increased
counters; missing members and unrelated mutations fail. Failed recomputation
restores H2 and retains the receipt. Validated H3 consumes it before resuming
the same gate locator. By default
`architecture-options-lint.py` rejects the pending report until recomputation
restores `awaiting-selection`.

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
  --repo-root . --json
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
