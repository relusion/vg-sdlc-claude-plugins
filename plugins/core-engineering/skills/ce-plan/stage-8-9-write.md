# Feature-Plan Workflow — Stages 8–9: Final Review and Write

Stage file for the `plan` skill (orchestrator: `SKILL.md`). Covers Final Plan
Review, the Validation Checklist, writing, and closing. Load this file after
Stage 7 passes. After a Single-Feature Final Plan Approval (§4.1.3), enter only
the Recommended Minimal Output write plus Stage 9 validation/cleanup/closing;
do not replay the multi-feature Stage 8 gates.

At the write step, also read `${CLAUDE_SKILL_DIR}/artifact-template.md` for the plan directory structure and per-file templates.

---

## Stage 8 — Final Plan Review

After reachability/consumability and session-fit checks pass, present the final plan.

For a multi-feature plan, this is the final approval point. The separately
attested single-feature route has its abbreviated final approval at §4.1.3.

---

### 8.1 Freeze Candidate Shape

Before presenting the final plan:

- apply any final complexity adjustments
- apply any final ordering changes
- ensure bridge metadata is complete
- ensure high-risk justifications are recorded
- ensure deferred journeys are recorded
- ensure no provisional dependency errors remain
- verify the architecture disposition and accepted architecture result still
  reference the current `candidate_revision`

If a final ordering, dependency, bridge, feature, driver, or accepted-decision
change alters the candidate revision, do not call the shape frozen. Re-run
Stage 3.9. Return to
`${CLAUDE_SKILL_DIR}/stage-5a-architecture-convergence.md` only when the current
route is required or an explored recommended direction has a current human
election to shape this revision. When the route remains recommended but the
prior shaping election was deferred or is stale, return to §5.4.1 for a fresh
human election; do not silently force Stage 5A. An explicit direction deferral,
candidate-shaping deferral, and not-applicable disposition remain distinct.
Then re-run every affected Reachability and Session-Fit check before presenting
the final plan.

---

### 8.2 Present Final Plan

Lead with this exact heading; do not make the human find the decision surface
inside the complete plan:

```text
What needs your decision
```

Under it, render these blocks in order:

1. **Decision delta** — what changed since the last human checkpoint. Name the
   changed candidate revision, features, dependencies/order, journeys, bridges,
   risks, architecture direction/disposition, `TZ-NNN` / `IC-NNN` rows, NFRs,
   and deferred scope. If nothing changed, say `No decision-bearing delta` and
   name the checkpoint compared. In the light tier, where §5.4 did not fire,
   compare against the last Stage 4–7 checkpoint and label this the first
   decomposition review.
2. **Unknowns and material rows** — one row per unresolved unknown, explicit
   deferral, high-risk justification, architecture waiver/gap/park, foundation
   exception, continuity/bulk/bridge disposition, and material `TZ-NNN` or
   `IC-NNN` assignment. Give every row an id, current disposition, **basis +
   cost-if-wrong**, required owner/authority, evidence state, and the later gate
   or stage that owns resolution. Never aggregate distinct TZ/IC rows into a
   single consent surface.
3. **Recommendation** — name the recommended Final Approval option (or the
   specific adjustment/evidence/owner route), confidence `high` / `medium` /
   `low`, the evidence supporting it, and what new fact would change it. For a
   required architecture disposition, say whether the recommendation is
   `Write plan & continue to architecture` or `Write plan & park architecture`
   and state that specification remains blocked until publication succeeds.
4. **Consequence preview** — state what the recommended choice writes, what it
   does not settle, the next human-owned gate, and the output directory path.

Then collapse settled material so it remains inspectable without competing
with the decision surface:

```markdown
<details>
<summary>Auto-resolved (<count>)</summary>

<id — resolution — evidence/checkpoint> ...

</details>
```

An item belongs in `Auto-resolved` only when its evidence and owning checkpoint
are recorded and no human choice remains. A model inference, missing authority,
or unanswered unknown is not auto-resolved.

Finally retain the complete plan as supporting detail, after the triage above,
using a second collapsed section (or the UI's equivalent disclosure control):

```markdown
<details>
<summary>Supporting detail — full final plan</summary>

<the complete final-plan presentation>

</details>
```

The supporting detail must still contain:

- project summary
- Brownfield friction tier and reason
- final dependency flow
- final feature table
- journey/consumability summary
- bridge summary
- risk summary
- **threat-model summary** — the trust boundaries, the `sensitive`/`personal`
  nouns (re-projected from §6.3), and the per-feature security obligations
  (`TZ-NNN` threat-ids, *surface-don't-force*); or an explicit **No Security
  Surface** if none detected. Its model-derived assignment is attested
  separately in 8.2.1, never by silence in this summary.
- **interaction-contract summary** — the cross-feature producer→consumer edges
  and the §6.3 durable nouns touched by >1 feature (the `IC-NNN`
  behavioural-protocol invariants: medium / idempotency / delivery / ordering /
  retry / concurrency), and the architecture-determining numeric NFRs
  re-projected with their source and shaping consequence; or an explicit **No
  Cross-Feature Protocol** if none detected. Its model-derived assignment is
  attested separately in 8.2.2, never by silence in this summary.
- **selected architecture direction** — exploration id, selected option id/title
  and binding hashes, confidence/sensitivity, human rationale, and how the
  candidate realizes it; or the explicit human-confirmed
  `not-applicable`/`deferred`/`waived` direction status. Never substitute a new
  recommendation at Final Review.
- **architecture disposition** — `required`, `recommended`, `not-required`, or
  `waived`; its Stage 3.9 trigger evidence, current candidate revision,
  convergence/deferral summary, accepted ADR refs, and downstream consequence
- notes and deferred scope
- output directory path and file list

If the presentation channel cannot render collapsible content, keep this same
order and print only the `Auto-resolved` count/index by default; expand its rows
on request. Still print the full supporting plan after the decision surface.

**Light-plan tier — this presentation folds the Candidate Review.** In the light tier
(§4.3) the standalone §5.4 gate did not fire, so this final presentation **is** the candidate
review: the feature table, dependency flow, and per-feature blocks above are the decomposition
the human signs off at 8.3. (In the standard tier they were already reviewed at §5.4 and this
is the second, final look.)

**Which attestation gates fire next.** Resolve both re-projection outcomes, then
run **§8.2.1 followed by §8.2.2 for every plan tier**. The light tier keeps each
negative prompt compact, but never combines the two material calls and never
relaxes HITL R3. Count both gates in M from the outset. Questions that isolate
rows inside one attestation keep that gate's locator and do not silently change
M; if a correction adds a conditional gate or revisits a prior gate, recompute M
and say so at the locator.

### 8.2.1 Threat-model attestation  [material]

The threat-id assignment is **model-derived**, so it is confirmed as its **own
evidence-first prompt** (HITL Gate Standard R2/R3) — **before** Write is
offered in 8.3 — never a bullet in the 8.2 dump the human consents to by not objecting.

Print this exact locator before its questions:

```text
Gate N of M — Threat-Model Attestation
```

For every material row, identify the required authority before asking. The
default authority is the named security/trust-boundary owner or the feature's
security/secrets Boundary-Owner. If neither exists, name the project technical
owner who can accept the surface and its acceptance-criterion consequence.
The model is never the authority. Show `Owner/authority: <name or missing>` and
`Evidence state: <refs or missing>`; a missing or unavailable owner routes to
the park path rather than being treated as consent.

For each feature the model assigned a `TZ-NNN`, render its **basis + cost-if-wrong** in
plain language, glossing the security terms from the shared consequence-glossary (a
`TZ-NNN` is a *security-review obligation*; a *trust boundary* is where data or an
action crosses from less-trusted to more-trusted):

```text
<feature> needs a security-review obligation, because: <the trust boundary it crosses,
or the sensitive/personal noun it writes — e.g. "accepts the login form off the
internet" / "writes credentials (sensitive)">.
If this is wrong (NO): the feature ships with NO required security acceptance criterion
for that surface — the Veracode-flatline path.
```

Create **one independently answerable `AskUserQuestion` question per material
`TZ-NNN` row** under the same locator. Never offer `Confirm all`. A tool call may
batch at most four separate row questions; when more than four remain, split
them into ordered batches, label `batch x/y`, and do not advance the gate until
every row resolves. Each row question uses only these options:

| Option | Result |
|---|---|
| Confirm this `TZ-NNN` | The recorded owner/authority accepts this assignment; it becomes a `[SECURITY]` obligation the feature's `/core-engineering:ce-spec` must cover. |
| Correct/remove this `TZ-NNN` | State the evidence and correction; return to the owning feature-review step, update the row, and re-present this question. A removal records the reason as a consented exclusion. |
| Need evidence / route to owner | Name the missing evidence or required owner, route the row there, and **park this gate with resumable scratch**. This is not a decision. |

`Confirm this TZ-NNN` is valid only when the answering human has the displayed
authority or records that authority's evidence-backed approval. After all
current rows resolve, ask one separate coverage-control question under the same
locator (do not append it as a fifth question to a four-row batch):

| Option | Result |
|---|---|
| Coverage complete | The required owner confirms no material security surface is missing from the resolved set. |
| Add a missing threat | Name the feature and evidence; return to feature review, add its `TZ-NNN`, and attest the new row independently. |
| Need evidence / route to owner | Name the missing evidence or authority and **park this gate with resumable scratch** until it is supplied. |

When the summary was **No Security Surface**, attest *that* too — confirming there is
no surface is itself a model-derived negative (R2), equally rubber-stampable as a
printed line. Render the negative's basis + cost-if-wrong and the required
owner/authority, then ask this **separate** question under `Gate N of M —
Threat-Model Attestation`:

| Option | Result |
|---|---|
| Confirm No Security Surface | The displayed owner/authority accepts the attested negative — no feature crosses a trust boundary or owns a `sensitive`/`personal` noun. |
| Actually, there is a surface | Name its evidence; return to feature review to assign and independently attest the missed threat. |
| Need evidence / route to owner | Name the missing evidence or authority and **park this gate with resumable scratch**. This is not a negative attestation. |

Do not offer Write (8.3) until this attestation resolves.

**Checkpoint — Threat-Model attestation (8.2.1) passed.** Once this attestation resolves,
append a `## Threat-Model Attestation (8.2.1) — passed` checkpoint to
`docs/plans/.drafts/<slug>/scratch.md` — `decided_by: human`, the decision,
owner/authority, and evidence reference for **each** `TZ-NNN`, the coverage-control
result (or the separately attested negative), and the resolved `TZ-NNN` set — per
SKILL.md → *Gate Checkpoint & Resume*. A parked route does not write a passed
checkpoint.

### 8.2.2 Interaction-contract attestation  [material]

The interaction-contract invariants and architecture-NFR rows are **model-derived**, so
each is confirmed as its **own evidence-first prompt** (HITL Gate Standard R2/R3) —
**after** the 8.2.1 threat-model attestation and **before** Write is offered in 8.3 —
never a bullet in the 8.2 dump the human consents to by not objecting.

Print this exact locator before its questions:

```text
Gate N of M — Interaction-Contract Attestation
```

For an `IC-NNN`, the required authority is the named owner of the shared
producer→consumer contract; when ownership is split, record both producer and
consumer owners or one boundary owner explicitly authorized by both. For an
architecture-NFR row, record the cited requirement owner and the architecture
owner authorized to accept its shaping consequence. Show
`Owner/authority: <name(s) or missing>` and `Evidence state: <refs or missing>`
for every row. The model is never the authority, and an absent or contested
owner routes to evidence/owner parking.

For each `IC-NNN`, render its **basis + cost-if-wrong** in plain language, glossing the
protocol terms from the shared consequence-glossary (an `IC-NNN` is a *cross-feature
behavioural-protocol obligation* or an *architecture-determining NFR*; *idempotency* = a
replayed message / retry must not double-apply; *at-least-once* = the consumer **will**
sometimes see a duplicate; *per-key ordering* = events for one entity arrive in order):

```text
<edge / shared noun> needs <the invariant — e.g. "the consumer to dedupe on order_id">,
because: <the medium and why — e.g. "order.placed is delivered at-least-once over the
event bus, so the broker WILL redeliver">.
If this is wrong (NO): the consumer ships with NO required dedupe acceptance criterion —
duplicate orders on every broker redelivery.
```

For an **architecture-NFR** row the basis is *"the plan cited this number (§2 / §3 / §4) and
it forced `<the split / boundary>`"* — the human confirms the plan stated it **and** that
it shaped the cut, never elicits a fresh target; if wrong, the cut is unjustified or the
target is unmet at integration.

Create **one independently answerable `AskUserQuestion` question per material
`IC-NNN` or architecture-NFR row** under the same locator. Never offer `Confirm
all`. A tool call may batch at most four separate row questions; when more than
four remain, split them into ordered batches, label `batch x/y`, and do not
advance the gate until every row resolves. Each row question uses only these
options:

| Option | Result |
|---|---|
| Confirm this row | The recorded owner/authority accepts this assignment; an `IC-NNN` becomes a `[CONTRACT]` obligation the feature's `/core-engineering:ce-spec` must cover, or the cited NFR remains a shaping constraint. |
| Correct/remove this row | State the evidence and correction; return to the owning feature/architecture-review step, update the row, and re-present this question. A removal records the reason as a consented exclusion. |
| Need evidence / route to owner | Name the missing evidence or required owner, route the row there, and **park this gate with resumable scratch**. This is not a decision. |

`Confirm this row` is valid only when the answering human has the displayed
authority or records that authority's evidence-backed approval. After all
current rows resolve, ask one separate coverage-control question under the same
locator (do not append it as a fifth question to a four-row batch):

| Option | Result |
|---|---|
| Coverage complete | The required owner confirms no material cross-feature invariant or shaping NFR is missing from the resolved set. |
| Add a missing invariant / NFR | Name its edge, noun, or cited source; return to the owning review step, add the row, and attest it independently. |
| Need evidence / route to owner | Name the missing evidence or authority and **park this gate with resumable scratch** until it is supplied. |

When the summary was **No Cross-Feature Protocol**, attest *that* too — confirming there
is no cross-feature contract is itself a model-derived negative (R2), equally
rubber-stampable as a printed line. Render the negative's basis + cost-if-wrong
and the required owner/authority, then ask this **separate** question under
`Gate N of M — Interaction-Contract Attestation`:

| Option | Result |
|---|---|
| Confirm No Cross-Feature Protocol | The displayed owner/authority accepts the attested negative — the four detection conditions are all absent: no integration boundary carrying a cross-feature edge, no Journey-Map / Dependency-Flow edge over a durable/async medium, no >1-touched durable noun, no architecture-determining NFR cited. |
| Actually, there is a cross-feature contract | Name its evidence; return to feature review to add and independently attest the missed invariant or NFR. |
| Need evidence / route to owner | Name the missing evidence or authority and **park this gate with resumable scratch**. This is not a negative attestation. |

Do not offer Write (8.3) until this attestation resolves.

**Checkpoint — Interaction-Contract attestation (8.2.2) passed.** Once this attestation
resolves, append a `## Interaction-Contract Attestation (8.2.2) — passed` checkpoint to
`docs/plans/.drafts/<slug>/scratch.md` — `decided_by: human`, the decision,
owner/authority, and evidence reference for **each** `IC-NNN` / NFR row, the
coverage-control result (or the separately attested negative), and the resolved
`IC-NNN` / NFR set — per SKILL.md → *Gate Checkpoint & Resume*. A parked route
does not write a passed checkpoint. A crash between the attestations and Write
re-enters at Stage 8.3 Final Decision with both attestations already recorded.

### 8.2.3 Light-tier attestation routing

The light tier preserves proportionality through compact negative questions,
not by merging material calls. Always run `Gate N of M — Threat-Model
Attestation` (§8.2.1), write its own checkpoint, then run `Gate N of M —
Interaction-Contract Attestation` (§8.2.2) and write its own checkpoint. When
both projections are negative, each gate has only its one three-option negative
question; there is no combined confirmation and no R3 relaxation. Positive
rows use the independently answerable row questions and batching rules above.

---

### 8.2.4 Architecture–Plan Convergence recheck

After the applicable TZ/IC attestation gates resolve and before Final Plan
Approval, re-run the Stage 3.9 applicability screen and compare the accepted
architecture result with the exact candidate:

- same `exploration_id`, capability revision, exploration attempt, source/input
  fingerprint, option-set hash, selected option id, and selected-option hash;
- same `candidate_revision`;
- same features, dependencies, order, journeys, durable nouns, and owners;
- same architecture trigger ids and evidence boundary;
- same attested TZ/IC rows and architecture-determining NFRs; and
- no new material decision, coverage gap, or unrecorded accepted ADR.

An added, corrected, or removed threat/invariant, or a corrected negative that
changes one of these rows increments `candidate_revision`. A mismatch that
changes capabilities, hard constraints, quality priorities, source evidence,
or the selected direction returns to Stage 1A and requires a new human
selection before decomposition. Any other mismatch invalidates convergence:
for a required route or a recommended route already elected for shaping, update
the latest Architecture Shaping Input, load
`${CLAUDE_SKILL_DIR}/stage-5a-architecture-convergence.md`, and rerun shaping;
for a recommended route whose shaping was deferred, return to §5.4.1 with the
updated candidate and let the human shape or defer again.
If shaping changes the cut, rerun the touched Reachability and Session-Fit
checks plus the affected attestations. Never convert a stale result into a
waiver by silence.

When no mismatch exists, record the recheck in scratch as an autonomous pass.
Final Plan Approval is the human confirmation of the displayed disposition;
do not add a duplicate rubber-stamp prompt.

---

### 8.3 Final Decision `[material]`

This is the multi-feature **final-approval gate** and its only artifact commit
point. Print the locator and label each option by its consequence
(HITL Gate Standard R1/R5); the 8.2.1 threat-model and 8.2.2 interaction-contract
attestations must each have already resolved for every plan tier, so `Write` is
never the vehicle that also attests either:

```text
Gate N of M — Final Plan Approval
```

Render the **Material-Gate Decision Authority** block from `SKILL.md`; the
decision owner is the project/plan owner authorized to commit the displayed
scope, exclusions, risk acceptances, artifact paths, and downstream blockers.
Missing or contested authority cannot authorize Write.

| Option | What happens next |
|---|---|
| Write | **Freeze stable IDs and write the whole plan directory** to `docs/plans/<slug>/` (+ update the registry). This is the commit point. For `recommended`, `not-required`, or `waived`, use the conditional closing below. |
| Adjust | Loop back to feature decomposition or ordering — nothing is written yet. |
| Add context | Capture additional context, then revalidate — nothing is written yet. |
| More controls | Make no decision and open evidence/owner/park/abort controls under the same locator. |

If `More controls` is selected, ask this same-locator follow-up:

| Option | What happens next |
|---|---|
| Need evidence / route to owner | Name the exact missing evidence or accountable owner and park this gate until it returns; no approval is recorded. |
| Park with the draft resumable | Stop at this gate with every checkpoint and reviewed artifact preserved. |
| Abort and preserve draft | End this run without a final artifact; preserve `docs/plans/.drafts/<slug>/` until an explicit fresh-start decision or successful write removes it. |
| Back to approval choices | Re-display the primary approval question under the same locator; no state advances. |

Only `Write` creates the final artifact.

When `architecture_disposition.decision` is `required`, replace the generic
table with this four-option gate so architecture publication is an explicit
human-owned continuation, not a silent auto-run:

| Option | What happens next |
|---|---|
| **Write plan & continue to architecture** | Freeze/write the plan, then invoke `/core-engineering:ce-architecture <slug>`; the architecture workflow stops at its own human gates and no spec may start until publication succeeds. |
| **Write plan & park architecture** | Freeze/write a valid plan and stop; the missing required package remains a visible blocker for spec and auto-build. |
| **Adjust plan or context** | Return to the owning planning stage, invalidate convergence when needed, and write nothing yet. |
| **More controls** | Make no decision and open the same evidence/owner/park/abort follow-up above under this locator. |

**Light-plan tier (§4.3): this gate also carries the folded Candidate Review.** The feature
table and dependency flow presented at 8.2 are the decomposition, so `Write` accepts it and
`Adjust` **is** the candidate re-cut (Coarsen stays unavailable — moot at ≤ 3). Because the
generic gate already has four choices, use this same-locator two-step control; never append a
fifth option to one question. Replace the generic table above with this light-tier primary
question:

| Option | What happens next |
|---|---|
| Write | Freeze stable IDs and write the plan; this accepts the folded Candidate Review and records `plan_tier: light`. |
| Adjust | Return to the candidate decomposition or ordering and write nothing yet. |
| Add context | Capture context, revalidate the light-tier eligibility and candidate, and write nothing yet. |
| More controls | Make no decision and open the expansion/evidence/owner/park controls below under the **same locator**. |

If `More controls` is selected, reprint the exact same locator — `Gate N of M —
Final Plan Approval` — and ask this follow-up question:

| Option | What happens next |
|---|---|
| Expand to full gates | Leave the light tier: run the standalone **Candidate Decision (§5.4)**, then re-run the separate **Threat-Model Attestation (§8.2.1)** and **Interaction-Contract Attestation (§8.2.2)** before returning to Final Plan Approval. Record `plan_tier: standard`. |
| Need evidence / route to owner / park | Name the missing evidence or accountable owner and stop with every checkpoint preserved; no approval is recorded. |
| Abort and preserve draft | End this run without a final artifact; preserve `docs/plans/.drafts/<slug>/` and every checkpoint for resume. |
| Back to approval choices | Make no decision and re-display the light-tier primary question under this same locator. |

`More controls` and `Back to approval choices` are navigation, not approvals or
new gates; N and M remain unchanged. A required architecture disposition cannot
take the light tier (§4.3); if the states conflict, the required four-option
architecture gate above wins and the workflow must correct the tier record.

---

## Stage 9 — Write the Plan

When the user selects `Write`, freeze final IDs — replace every provisional `P01-…` ID with its stable `01-…` slug — and write the plan **directory**:

```text
docs/plans/[project-slug]/
├── feature-plan.md       # index: overview, dependency flow, feature table, checklist
├── shared-context.md     # codebase profile, selected direction, decisions, known pitfalls
├── architecture-selection.json  # exact pre-decomposition evaluation + human direction disposition
├── architecture-options.md  # human-readable comparison when directions were explored
├── threat-model.md       # trust boundaries + data-classes + per-feature security obligations
├── interaction-contract.md  # cross-feature protocol invariants + architecture-determining NFRs
├── features/
│   └── <NN>-<slug>.md    # one file per feature, full feature block
└── plan.json             # machine-readable manifest, features in ship order
```

**Write `threat-model.md`** alongside `shared-context.md` — a **read-only
re-projection** assembled from data already settled, *not* a new set of decisions
(template + the four sections in `${CLAUDE_SKILL_DIR}/artifact-template.md` → *Threat Model*). Derive:
trust boundaries and exposure surface from the §3 codebase profile
(`public_interaction_surfaces`, `integration_boundaries`, `cross_cutting_layers`);
the Secrets & Data-Classes table by copying the §6.3 closure's data-class column
**verbatim** (never re-assign it here); and the **Per-Feature Security Obligations**
block by *surface-don't-force* — a `TZ-NNN` per feature that crosses a trust boundary
or is the security/secrets Boundary-Owner, an `advisory` (not a threat_id) for a
feature that only owns a `sensitive`/`personal` noun. If **none** of the four
detection conditions hold across the plan, write the **No Security Surface** attested
negative instead — **never omit the file** (the §6.4-`N/A` discipline).

**Write `interaction-contract.md`** alongside `threat-model.md` — a **read-only
re-projection** assembled from data already settled, *not* a new set of decisions
(template + the two tables in `${CLAUDE_SKILL_DIR}/artifact-template.md` → *Interaction
Contract*). Derive: the **Behavioural-Protocol Invariants** by *surface-don't-force* —
one `IC-NNN` per already-traced cross-feature producer→consumer edge (a §8 Journey-Map
step or a §10 Dependency-Flow edge that crosses between two features) **on an
async/durable medium** (event-bus / queue / external-API / shared-store; a synchronous
in-proc call earns no row), and one per §6.3 durable noun **touched by >1 feature** (its
multi-toucher concurrency/idempotency posture — never re-assigning its data-class); and
the **Architecture-Determining NFRs** by re-projecting only a numeric target the plan
**literally cited** in §2 / §3 / §4 *and* that shaped the cut, each with its `Source` pointer
— never an invented or non-shaping number. If **none** of the four detection conditions
hold, write the **No Cross-Feature Protocol** attested negative instead — **never omit
the file** (the §6.4-`N/A` discipline).

Use **`${CLAUDE_SKILL_DIR}/artifact-template.md`** in this skill's directory for the directory layout, the per-file section map, and every file template. Do not reconstruct any file's format from memory.

Write one `features/<id>.md` per feature; `feature-plan.md` carries only the compact feature table and links to those files — never the full feature blocks.

For a single-feature plan whose §4.1.1 security attestation and §4.1.3 Final Plan
Approval passed, write exactly the reviewed single-file **Recommended Minimal
Output** instead of the directory (see `${CLAUDE_SKILL_DIR}/artifact-template.md`).

Also: write the `relates_to` captured in Stage 0's Sibling Plans subsection into `plan.json`. Then **update `docs/plans/plans.json`** (the repo's plan registry) — create it if missing, append this plan's entry (slug, description, `relates_to`). The registry is what `/core-engineering:ce-spec` and `/core-engineering:ce-implement` consult to resolve feature ids across plans.

**Record architecture disposition.** Every new full plan writes the exact
`architecture_disposition` object from Stage 5A / the final applicability
recheck. For `not-required`, write `triggers: []`, `convergence.status:
not-applicable`, `iteration_count: 0`, and the human-confirmed basis from Final
Plan Approval. For `recommended` without shaping, copy the exact human
election's `deferred`, `iteration_count: 0`, rationale, and visible coverage
gap; Stage 9 never invents that state during serialization. Never omit the
object from a newly written full plan;
single-feature minimal output has no `plan.json` and remains N/A by construction.

**Publish the selected direction.** Copy the exact reviewed draft
`docs/plans/.drafts/<slug>/architecture-selection.json` to
`docs/plans/<slug>/architecture-selection.json`; never regenerate options,
scores, evidence, sensitivity, or the human selection from prose. Compute the
SHA-256 of the final bytes and write the `architecture_disposition.direction`
summary from the same artifact: status, exploration id, artifact path/hash,
selected option id/hash (or explicit null when the direction status itself is
`not-applicable`, `deferred`, or `waived`),
`decided_by: human`, and summary. The summary and artifact must agree exactly.
For a new full plan, either a human-selected/adopted direction or the explicit
not-applicable/deferred disposition exists—absence is never the cheap path. A
later shaping waiver preserves the selected direction that actually shaped the
cut; only a human-reaffirmed legacy no-direction waiver uses direction status
`waived`.

**Publish the readable comparison.** When the direction came from fresh explore
mode (schema v2 with `architecture_options_report.status: present`), require the
immutable pre-approval report at
`docs/plans/.drafts/<slug>/architecture-options.md`. Re-read it and verify its
integrity table, option ids/titles/hashes, recommendation, source-input hash,
evidence fingerprint, option-set hash, and exact file SHA-256 against the
schema-v2 binding in `architecture-selection.json`; the later selected id/hash
and rationale remain in JSON because this report preserves what existed before
the choice. Then copy its exact bytes to
`docs/plans/<slug>/architecture-options.md`. Do not regenerate the report from
plan prose. A missing, mutated, unsafe, or contradictory report blocks the
write and retains scratch. Schema-v1 selections are explicit legacy artifacts
with no report guarantee; not-applicable/deferred routes and legacy
adopted-existing records with no explored comparison omit the report
explicitly. Absence is not an excuse to omit it from a schema-v2 present route.
The JSON remains the machine authority and the Markdown is its durable human
review surface.

**Record the plan tier.** Write `"plan_tier": "light"` into `plan.json` (top-level, beside
`plan_revision` — see `${CLAUDE_SKILL_DIR}/artifact-template.md` → *Plan Manifest*) whenever
the run entered the **light-plan tier** (§4.3) and did **not** expand back at 8.3; write
`"standard"` or omit the key otherwise (**absent ⇒ `standard`**). Also append a
`plan-tier: light` entry to §13 Notes naming **which gate was folded** — the standalone
Candidate Decision folded into Final Approval — and recording that the Threat-Model
Attestation (§8.2.1) and Interaction-Contract Attestation (§8.2.2) remained separate, each
with its own checkpoint. This lets `/core-engineering:ce-plan-audit` and a later Stage R read
the proportionality choice from the artifact instead of re-deriving it. It is the same
discipline as the Sizing Gate's, not a silent skip.

**Lint the written plan (write-time gate).** Immediately after the plan directory, `plan.json`, and `plans.json` are written — and **before** deleting the gate-checkpoint scratch — run the structural-integrity lint over the *persisted* artifact, so nothing closes on a plan that fails a mechanical invariant the ~40-item Validation Checklist below only self-attests. This is the on-disk twin of `/core-engineering:ce-plan-audit`'s hard lint, run here at the moment of writing:

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/architecture-selection-lint.py" \
  docs/plans/<slug>/architecture-selection.json \
  --require-current-schema --json
python3 "${CLAUDE_SKILL_DIR}/scripts/plan-lint.py" \
  docs/plans/<slug> --require-architecture-direction --json
```

Stage R may omit `--require-current-schema` only when it is preserving a
previously valid schema-v1 selection byte-for-byte. Any selection regenerated
by the current workflow—including N/A/deferred—must use schema v2 and the
current-schema flag.

Dispose by exit code (the same contract `/core-engineering:ce-spec`'s `spec-lint` follows — the lint **supplements** the checklist, never replaces it):

- **PASS (both exit 0)** → the selected-direction binding and H1–H10 plan invariants hold on disk. Annotate the checklist items the linters cover — frame/option/constraint/score/hash/selection integrity, dependency direction + cycle-freedom (H5/H6), referential integrity (H1/H3/H4), bridge resolution (H7), re-projection presence (H8), architecture posture (H9), and direction binding (H10) — as **`[machine-verified]`**; they **stay** in the checklist. Proceed to delete the scratch.
- **FAIL (exit 1)** → do **not** close on the failing artifact and do **not** delete the scratch (the run stays resumable). Present each hard failure and **return to the stage that owns it**: frame/selection/score/hash/hard-constraint or H10 direction-summary failures → Stage 1A; `H5`/`H6` → Stage 6 ordering; `H1`/`H3`/`H4`/`H7`/`H8` → re-write the offending file. Re-run both linters after the fix.
- **Could-not-run (either exit 2 or no result)** → do not close or delete the
  scratch. Show the parse/runtime failure and park until the bundled validators
  run. The manual checklist may diagnose the artifact but cannot replace the
  frame/hash/direction binding floor.
- **Single-feature minimal plan (no `plan.json`)** → record the lint line as **`N/A — single-feature minimal plan`** (mirroring `/core-engineering:ce-plan-audit`) and proceed; by construction there is no manifest to lint.

**Delete the gate-checkpoint scratch on success.** After the plan directory, `plan.json`, and `plans.json` are all written, delete `docs/plans/.drafts/<slug>/` (SKILL.md → *Gate Checkpoint & Resume*) — the final artifact now exists, so the resume transcript has served its purpose. Delete it **only** on a successful write; an abort or crash before this point leaves the scratch so the run stays resumable. Removing an emptied `.drafts/` parent when no other drafts remain is optional cleanup, never required.

**Metrics (best-effort, optional).** After writing, append a `stage-complete` line (`stage: "plan"`, `feature: null`) to `docs/plans/<slug>/.metrics.jsonl` per the `retro` skill's schema — include the already-known architecture decision, shaping iteration count, and whether convergence parked/was waived; label any token figure an estimate, and **never** let this block or fail the write. It powers `/core-engineering:ce-retro`.

---

## Validation Checklist Before Writing

This is the **consolidated final gate**, run on the **frozen candidate shape** — not a restatement of the Stage 4–7 gates. Stage 8.1 applies final complexity, ordering, bridge, and risk-justification changes *after* the Sizing, Reachability, and Session-Fit gates ran, so the checklist has **two distinct jobs**: block **A** re-verifies what 8.1 could have changed (the earlier gates can't vouch for it — they ran first), and block **B** confirms the written files actually captured the upstream-settled decisions (a failure surface no upstream gate covers). Keep the two jobs distinct; do not rubber-stamp either. If any check fails, return to the relevant stage. All checks must pass:

### A. Frozen-shape delta re-check (post-Stage-8.1)

Re-verify, against the frozen plan, every property Stage 8.1 could have mutated plus the gate results it ran after:

- [ ] Sizing Gate result is recorded.
- [ ] Candidate plan was reviewed.
- [ ] Architecture applicability was screened before Sizing; a required route
      did not take the single-feature or light-plan shortcut.
- [ ] `architecture-selection.json` is current for the confirmed capability
      frame, passes its deterministic lint, and records human authority; its
      selected option or explicit N/A/defer/waiver matches the final plan.
- [ ] A schema-v2 explored direction has the immutable pre-approval
      `architecture-options.md` whose exact hash and integrity values match its
      `architecture-selection.json` binding; explicit N/A/defer/schema-v1 legacy
      routes record why no comparison report applies.
- [ ] `architecture_disposition` is complete and internally consistent; any
      required shaping result is `converged`, human-decided, within the
      three-pass cap, and current for the final candidate revision.
- [ ] Every accepted architecture decision is recorded in the Resolved Project
      Decisions ledger and cited by repository-relative ADR path when ADR-worthy.
- [ ] Reachability or consumability was traced.
- [ ] Every non-deferred journey carries a primary modality, and every step has an expected observable and a modality (its own or inherited from the journey).
- [ ] Deferred journeys are recorded in Notes with a reason.
- [ ] On a brownfield plan, every existing shipped public surface a feature removes / renames / incompatibly changes carries a dispositioned continuity obligation (deprecate / shim / consented hard-break); greenfield plans record §6.4 `N/A`.
- [ ] Session-Fit Check passed.
- [ ] Final plan was approved before writing.
- [ ] Every feature has final Complexity.
- [ ] No feature exceeds 5 Open-Unknowns.
- [ ] No feature is too large for one implementation session.
- [ ] No feature has hidden duplicated scope.
- [ ] Hard dependencies point only to earlier features.
- [ ] No direct dependency cycles exist.
- [ ] No transitive dependency cycles exist.
- [ ] Soft forward dependencies have bridges or fallbacks.
- [ ] Every bridge references a valid future feature.
- [ ] Every bridge is below the bridge cost ceiling.
- [ ] At most one high-risk feature exists by default.
- [ ] Multiple high-risk features have explicit justifications.
- [ ] Boundary-Owner categories are unique.
- [ ] Reviewer-trigger pressure has been applied.
- [ ] Cascade Cap has been applied.

### B. Write-completeness manifest

Settled through planning and reconfirmed by the post-attestation convergence
recheck — this block does **not** re-litigate them; it confirms each one is
**present in the written files**:

- [ ] Project description is recorded.
- [ ] Codebase profile is recorded.
- [ ] `threat-model.md` is written: every feature that crosses a trust boundary or is the security/secrets Boundary-Owner carries ≥ 1 `TZ-NNN`, every `sensitive`/`personal` noun is re-projected (data-class unchanged from §6.3), and a feature owning a `sensitive` noun with no boundary carries an advisory — **or** the plan records an attested **No Security Surface** (never a silent omission).
- [ ] `interaction-contract.md` is written: every already-traced cross-feature edge on an async/durable medium and every §6.3 durable noun touched by >1 feature carries ≥ 1 `IC-NNN` behavioural-protocol invariant, and every architecture-determining numeric NFR is re-projected with its `Source` + shaping consequence — **or** the plan records an attested **No Cross-Feature Protocol** (never a silent omission).
- [ ] The post-attestation Architecture–Plan Convergence recheck passed; no
      stale candidate revision, trigger, decision, TZ/IC row, or NFR remains.
- [ ] Brownfield friction tier is recorded with reason.
- [ ] Decomposition Q&A is recorded.
- [ ] Project docs are recorded or explicitly set to `None`.
- [ ] Known pitfalls are recorded or explicitly absent.
- [ ] Primary slicing method is named.
- [ ] Secondary validation methods are named.
- [ ] Every feature has a unique stable ID.
- [ ] Every feature has a type.
- [ ] Every feature has scope and exclusions.
- [ ] Every feature has Risk-Profile.
- [ ] Every feature has dependencies listed, even if `None`.
- [ ] Every feature has Open-Unknowns listed, even if `None`.
- [ ] Every feature has a validation target.
- [ ] Every feature has a downstream Run line.

---


## Closing Behavior

After writing the plan, confirm what was created:

```text
Created: docs/plans/[project-slug]/
  feature-plan.md
  shared-context.md
  architecture-selection.json
  architecture-options.md  (when solution directions were explored)
  threat-model.md
  interaction-contract.md
  plan.json
  features/  (<N> feature files)
Updated: docs/plans/plans.json
```

Then route from the recorded disposition:

```text
Next feature:
01-feature-slug

Architecture disposition: <required | recommended | not-required | waived>
Reason: <recorded basis>
```

- **Required + `Write plan & continue to architecture`:** invoke
  `/core-engineering:ce-architecture [project-slug]` now. Do not print a direct
  spec command; specification remains blocked until the current package is
  approved and published.
- **Required + `Write plan & park architecture`:** print the architecture
  command as the only immediate next action and state that spec, direct
  implementation, and auto-build will stop until it succeeds.
- **Recommended:** offer the architecture command first and identify absence as
  a coverage gap; also print the first spec command because publication is not
  mandatory.
- **Not-required:** print the first spec command and the attested N/A basis.
- **Waived:** print the first spec command together with the human waiver and
  residual architecture-rework risk; never describe the waiver as security,
  compliance, release, or production acceptance.

Do not automatically start specification. Start architecture only when the
human explicitly selected `Write plan & continue to architecture` at Final Plan
Approval.

---
