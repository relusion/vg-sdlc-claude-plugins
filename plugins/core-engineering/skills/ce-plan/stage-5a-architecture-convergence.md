# Feature-Plan Workflow — Stage 5A: Architecture Convergence

Stage file for the `plan` skill (orchestrator: `SKILL.md`). Load this file after
Candidate Review when architecture applicability is `required`, when the human
elects a `recommended` shaping pass, or whenever later evidence invalidates an
earlier result.

**Next:** on the fresh-plan path, after a current result is accepted or
explicitly waived, return to `${CLAUDE_SKILL_DIR}/stage-4-7-gates.md` and start
or resume Stage 6; a post-Reachability re-entry returns to Stage 7. When Stage R
is the caller, return to its R.4 ordered gate sequence instead. Never jump from
a revision into the fresh-plan stages.

**Stage R caller mapping.** In this file, a back-edge to Stage 2 means Stage R
R.1 (update the explicit delta), followed by R.2 affected-gate recomputation and
R.3 confirmation. A fresh-path return to Stage 6/7 means resume Stage R R.4 at
the next ordered check. The revision caller owns preservation and write routing.

## 5A.1 Preserve ownership

`/core-engineering:ce-architecture` supplies read-only architecture judgment;
it does not own the feature cut. Freeze project intent, exclusions, recorded
requirements, and human authority for this pass. Keep feature IDs, boundaries,
dependencies, and order provisional.

- Architecture may identify a component, deployment, flow, data, quality, or
  decision consequence and propose a paste-ready delta.
- Only `/core-engineering:ce-plan` may apply that delta to the candidate.
- Only the human may approve the revised cut, a material technical decision,
  or a waiver.
- Shaping convergence is not final architecture approval, security acceptance,
  compliance attestation, release approval, or deployment authority.

## 5A.2 Write the bounded shaping handoff

Append one complete, latest-wins block to
`docs/plans/.drafts/<slug>/scratch.md`. Use the exact headings and terminators
below so shaping mode never reconstructs the candidate from chat:

```markdown
## Architecture Shaping Input
draft_slug: <validated slug>
candidate_revision: <positive integer>
shaping_attempt: <positive integer; increment before every shape invocation>
parent_gate_index: <next positive index in this ce-plan run>
parent_gate_total: <current computed M for this ce-plan run>
project_intent: <one bounded sentence>
non_goals: <semicolon-separated list or None>
architecture_triggers: <semicolon-separated Stage 3.9 driver-id => evidence basis>
evidence_paths: <comma-separated repository-relative files already read, or None>
accepted_decisions: <comma-separated accepted ADR paths / recorded decisions, or None>

### Provisional Features
| Provisional ID | Stable source (revision only) | Title | Type | Scope | Excluded | Hard dependencies | Soft dependencies | Order | Boundary-Owner | Open unknowns | Validation target |
|---|---|---|---|---|---|---|---|---:|---|---|---|
| P01-... | None (new) / 01-... | ... | foundation/user-facing/integration | ... | ... | ... | ... | 1 | ... | ... | ... |

### Journeys and Consumability
<current journey/consumability rows, including cross-feature media and observables;
use `Pre-Reachability: ...` with known flows on the first pass>

### Durable State
<known nouns, source/write owner, access/data class, migration/lifecycle and unknowns;
use `None detected — evidence: ...` only with a cited basis>

### Threat and Interaction Obligations
<candidate TZ/IC rows and architecture-determining NFRs, each labeled candidate
until the Stage 8 attestations; use explicit attested negatives only after attestation>
## End Architecture Shaping Input
```

Every provisional feature id must match
`P[0-9]{2}-[a-z0-9]+(?:-[a-z0-9]+)*`. Include only evidence already read; do not
invent paths, decisions, topology, or NFRs to make the block look complete. A
material unknown stays explicit and normally produces `blocked` or
`requires-decision`, not guessed convergence.

## 5A.3 Invoke the composable shaping mode

Invoke `/core-engineering:ce-architecture shape:<slug>` through the `Skill`
tool. Do not locate or read a sibling skill directory directly; plugin-qualified
invocation is the portable composition seam.

The returned `Architecture Shaping Result` must echo this block's exact
`source_candidate_revision`, exact `source_shaping_attempt`, and exactly one status:

- `converged`
- `requires-plan-delta`
- `requires-decision`
- `blocked`

It must also render `Evidence Boundary`, `Architecture Drivers`, `Provisional
System Shape`, `Decisions and Gaps`, `Plan Delta`, and `Next Owner`. Reject an
unrecognized/missing status, a stale candidate revision or shaping attempt, an
omitted material gap, or a result that claims to have written the plan or architecture package.
Treat that as `blocked`; do not reinterpret malformed output into a pass.

Increment `architecture_iteration_count` for every complete shaping result.
The maximum is three results in one bounded sequence. A candidate re-cut
increments `candidate_revision` but does not reset that sequence's cap.
Increment `shaping_attempt` before every new handoff, including an evidence-only
retry whose candidate revision remains unchanged; this keeps the append-only
scratch unambiguous. If the human starts a new sequence at §5A.5, keep
`architecture_iteration_count` cumulative across both sequences.
The parent locator fields are part of the byte-fresh handoff. Compute them from
the current plan gate manifest, including this scope gate and the result gate;
if conditional gates change M, append a later shaping attempt with the revised
locator rather than letting the nested skill start a second `1 of 1` sequence.

## 5A.4 Route the result

Render the full result as Markdown first. Then present only the rows needing a
human call under **What needs your decision**; collapse direct source-backed
rows to a count. Print the computed `Gate N of M` locator before every prompt.

### `converged` — Architecture-Plan Convergence `[material]`

Evidence-first, show why the provisional component/deployment/data/quality
shape fits the feature cut and the cost if that inference is wrong. Ask:

| Option | What happens next |
|---|---|
| **Accept convergence** | Record this exact candidate revision as architecture-shaped and continue; the governed post-write package is still required when disposition is `required`. |
| **Adjust candidate or evidence** | Return to the owning plan/evidence stage, increment the candidate revision if structure changes, and rerun shaping; nothing final is written. |
| **Waive with a human reason** | Record `decision: waived` and the residual rework risk; downstream surfaces the waiver, but this does not accept security/compliance/production risk. |
| **Park** | Stop with the draft intact until the named evidence, authority, or scope input exists. |

On acceptance, preserve the Stage 3.9 decision (`required` or `recommended`) and
record `convergence.status: converged`. On waiver, record `decision: waived`,
`convergence.status: waived`, and require a non-empty rationale and summary.

### `requires-plan-delta` — Architecture Decomposition Impact `[material]`

Show the exact proposed add/remove/re-cut/reorder/dependency/owner/boundary rows,
their evidence, and cost-if-wrong. Architecture has proposed them, not applied
them. Ask:

| Option | What happens next |
|---|---|
| **Apply the proposed delta in planning** | The human authorizes `/core-engineering:ce-plan` to change only the shown rows; increment `candidate_revision`, return to Stage 2, and re-run every affected gate plus shaping. |
| **Adjust the proposal or evidence** | Keep the current cut, gather/correct the named input, and rerun shaping. |
| **Waive with a human reason** | Keep the current cut and record the escaped architecture risk for downstream review; no security/compliance/production acceptance is implied. |
| **Park** | Stop without a final plan until the delta can be decided. |

Never hide a structural delta as a waiver note while also marking convergence.

### `requires-decision` — Material Architecture Decision `[material]`

Show exactly one option set, evidence, reversibility, affected provisional
features, and cost-if-wrong. Ask:

| Option | What happens next |
|---|---|
| **Route to `/core-engineering:ce-decide`** | Score the supplied option set; resume only from the human's recorded choice and an accepted ADR when the decision is cross-feature and ADR-worthy. |
| **Supply an existing human decision** | Cite the accepted ADR or recorded decision, add it to `accepted_decisions`, and rerun shaping. |
| **Adjust candidate or evidence** | Return to the owning plan/evidence stage and rerun; no decision is invented. |
| **Park** | Stop until the decision owner is available. |

`ce-decide` recommends and drafts; it does not accept an ADR or mutate this
candidate. Record accepted decision paths in the final disposition and the
plan's Resolved Project Decisions ledger.

### `blocked` — Architecture Coverage Gap `[material]`

Show the exact missing evidence/authority and what could be wrong without it.
Ask:

| Option | What happens next |
|---|---|
| **Add evidence** | Gather only the named in-scope evidence, refresh the input block, and rerun shaping. |
| **Add bounded discovery work** | Return to Stage 2 and add an independently verifiable discovery/foundation feature only when it has a concrete output and validation target. |
| **Waive with a human reason** | Continue with the named uncertainty visible downstream; this is delivery-risk acceptance only, not security/compliance/production approval. |
| **Park** | Stop without a final plan until the gap closes. |

A material coverage gap can never become `approved-with-gaps` architecture at
this stage; it is either resolved, explicitly waived by the human, or parked.

## 5A.5 Enforce the convergence cap

If the third shaping result is not accepted as `converged`, do not invoke a
fourth pass automatically. Present `Gate N of M — Architecture Convergence Cap`
with the three result summaries and ask:

| Option | What happens next |
|---|---|
| **Change scope/evidence and restart shaping** | Make the named human-owned change, retain the audit summaries, and begin a new bounded three-pass sequence. |
| **Waive with a human reason** | Freeze the current cut with the non-convergence recorded and visible downstream. |
| **Park** | Stop with the resumable draft until an owner or evidence change exists. |
| **Abort** | Exit without writing a final plan; keep the draft unless the human explicitly chooses a fresh start later. |

## 5A.6 Record the disposition and checkpoint

Maintain this in-flight shape for the eventual `plan.json`:

```json
{
  "architecture_disposition": {
    "decision": "required | recommended | not-required | waived",
    "triggers": ["stage-3.9-driver-id"],
    "rationale": "non-empty evidence or human-waiver basis",
    "decided_by": "human",
    "convergence": {
      "status": "converged | deferred | not-applicable | waived",
      "iteration_count": 1,
      "summary": "non-empty result or deferral summary",
      "decision_refs": ["repository-relative accepted ADR path"]
    }
  }
}
```

Use no pipe-delimited enum literals in the real JSON. `required` must be
`converged` with at least one trigger and one iteration. `recommended` may be
`converged` with at least one iteration or explicitly `deferred` with zero
iterations. `not-required` is created outside this stage with no triggers,
`not-applicable`, and zero iterations. `waived` requires at least one trigger,
one completed shaping result, and a non-empty human reason.

After acceptance or waiver, append `## Architecture-Plan Convergence — passed`
to scratch with `decided_by: human`, the exact disposition, candidate revision,
shaping attempt, iteration count, accepted decision refs, and the full returned result as
`state:`. A stale result never earns this checkpoint.
