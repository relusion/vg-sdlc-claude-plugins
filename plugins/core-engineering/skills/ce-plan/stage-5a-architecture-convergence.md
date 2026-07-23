# Stage 5A — Architecture convergence

Run this read-only shaping pass after a feature candidate exists and only when a
direction was selected. `/core-engineering:ce-plan` owns the candidate; only
planning may apply a feature-cut delta. Architecture may diagnose and propose.

## 5A.1 Build the revision-bound input

Write this bounded block to the draft checkpoint:

```text
## Architecture Shaping Input
project_slug: <slug>
candidate_revision: <positive integer>
shaping_attempt: <positive integer>
shaping_input_sha256: <sha256 of this block's exact UTF-8 bytes, excluding this field>
parent_gate_index: <Material Exceptions gate index>
parent_gate_total: <current plan gate total>
architecture_selection_path: docs/plans/.drafts/<slug>/architecture-selection.json
architecture_selection_sha256: <sha256>
exploration_id: <id>
selected_option_id: <Axx>
selected_option_sha256: <sha256>

### Scope and Decision Frame
<Scope Lock, capabilities, journeys, constraints, accepted decisions>

### Provisional Features
<ids, value, scope, boundary owner, interfaces, dependencies, ship order>

### Journeys and Consumability
<journey-to-feature trace, release cuts, bridges>

### Durable State
<noun ownership, access/data class, lifecycle and governance dispositions>

### Threat and Interaction Obligations
<TZ/IC rows, sources, owners, gaps>
## End Architecture Shaping Input
```

Re-read and hash the exact block before invoking. `shaping_attempt` increases on
every request, including an evidence-only retry whose candidate revision stays
unchanged. Do not reuse an attempt number with different bytes.

## 5A.2 Invoke shaping without a consent prompt

Invoke:

```text
/core-engineering:ce-architecture shape:<slug>
```

This is bounded, read-only analysis against a human-selected direction. Do not
ask permission merely to run it. The result must echo:

```text
source_candidate_revision
source_shaping_attempt
source_shaping_input_sha256
source_architecture_selection_sha256
source_selected_option_sha256
status
summary
evidence
proposed_delta
decision_refs
```

Reject stale hashes/revisions or a changed selected-option binding.

## 5A.3 Route the bounded outcome

Accept only:

- `converged` — the candidate honors the selected direction; record the summary
  and decision refs, then return to Stage 6 without a human gate;
- `requires-plan-delta` — architecture proposes a precise before/after feature,
  ownership, dependency, journey, or obligation delta;
- `requires-decision` — a bounded material fork needs an authorized human;
- `blocked` — evidence, authority, or safe analysis is missing.

For `requires-plan-delta`, render the delta at the plan's existing Material
Exceptions locator with evidence, reasoning, assumptions, affected features,
scope effect, consequences, recommendation, and cost if wrong. Architecture has
proposed it, not applied it. Only the human may approve a material revised cut,
and only `/core-engineering:ce-plan` may apply that delta.

For `requires-decision`, use the same locator and 2–4 supplied alternatives.
Questions or requested revisions remain at that locator. A change to the
architecture option or decision frame returns to Stage 1A rather than being
smuggled into a shaping delta.

For `blocked`, route to the named evidence/authority owner or park.

After an accepted delta:

1. apply it in planning;
2. increment `candidate_revision`;
3. rerun only affected decomposition, dependency, reachability,
   security/interaction, session-fit, and spec-route checks;
4. invoke a fresh shaping attempt.

The maximum is three shaping results for one direction. At the cap, present
proceed-with-named-gap, return-to-architecture-direction, or park; never claim
convergence.

## 5A.4 Checkpoint

Record the current input hashes, outcome, evidence, accepted plan delta if any,
decision refs, iteration count, and convergence status. The result is valid
only for the echoed candidate revision and hashes.

Return to Stage 6 in
`${CLAUDE_SKILL_DIR}/stage-4-7-gates.md`.
