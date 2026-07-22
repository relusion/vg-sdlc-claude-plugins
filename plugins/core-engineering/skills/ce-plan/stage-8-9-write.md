# Feature-Plan Workflow — Stages 8–9: Final Review and Write

Stage file for the `plan` skill (orchestrator: `SKILL.md`). Covers Final Plan Review, the Validation Checklist, writing the plan directory, and closing. Load this file after Stage 7 passes, or directly from Stage 4 on a single-feature accept.

At the write step, also read `${CLAUDE_SKILL_DIR}/artifact-template.md` for the plan directory structure and per-file templates.

---

## Stage 8 — Final Plan Review

After reachability/consumability and session-fit checks pass, present the final plan.

This is the first true final approval point.

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

Print:

- project summary
- Brownfield friction tier and reason
- final dependency flow
- final feature table
- journey/consumability summary
- bridge summary
- risk summary
- **threat-model summary** — the trust boundaries, the `sensitive`/`personal` nouns (re-projected from §6.3), and the per-feature security obligations (`TZ-NNN` threat-ids, *surface-don't-force*); or an explicit **No Security Surface** if none detected. *(Its model-derived assignment is attested separately in 8.2.1 — never by silence in this summary.)*
- **interaction-contract summary** — the cross-feature producer→consumer edges and the §6.3 durable nouns touched by >1 feature (the `IC-NNN` behavioural-protocol invariants: medium / idempotency / delivery / ordering / retry / concurrency), and the architecture-determining numeric NFRs re-projected with their source and shaping consequence; or an explicit **No Cross-Feature Protocol** if none detected. *(Its model-derived assignment is attested separately in 8.2.2 — never by silence in this summary.)*
- **selected architecture direction** — exploration id, selected option id/title
  and binding hashes, confidence/sensitivity, human rationale, and how the
  candidate realizes it; or the explicit human-confirmed
  `not-applicable`/`deferred`/`waived` direction status. Never substitute a new
  recommendation at Final Review.
- **architecture disposition** — `required`, `recommended`, `not-required`, or
  `waived`; its Stage 3.9 trigger evidence, current candidate revision,
  convergence/deferral summary, accepted ADR refs, and downstream consequence.
  For `required`, state plainly that specification remains blocked until the
  post-write architecture package is current and approved.
- notes and deferred scope
- output directory path and file list

**Light-plan tier — this presentation folds the Candidate Review.** In the light tier
(§4.3) the standalone §5.4 gate did not fire, so this final presentation **is** the candidate
review: the feature table, dependency flow, and per-feature blocks above are the decomposition
the human signs off at 8.3. (In the standard tier they were already reviewed at §5.4 and this
is the second, final look.)

**Which attestation gate(s) fire next.** Resolve the two re-projection outcomes first, then
route:

| `plan_tier` | Threat-model | Interaction-contract | Attestation gate(s) |
|---|---|---|---|
| standard (any) | — | — | **§8.2.1 then §8.2.2**, always separate |
| light | No Security Surface | No Cross-Feature Protocol | **§8.2.3 combined** — both negatives, one gate |
| light | a real surface | any | **§8.2.1 separate** (positive restores it); §8.2.2 per its own outcome |
| light | any | a real protocol | **§8.2.2 separate** (positive restores it); §8.2.1 per its own outcome |

Any positive detection in the light tier restores the separate gate for **that**
re-projection automatically — the combine applies **only** when *both* resolve negative. If a
positive detection changes the count mid-run, recompute M and say so at the locator (no silent
cap).

### 8.2.1 Threat-model attestation  [material]

The threat-id assignment is **model-derived**, so it is confirmed as its **own
evidence-first prompt** (HITL Gate Standard R2/R3) — **before** Write is
offered in 8.3 — never a bullet in the 8.2 dump the human consents to by not objecting.

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

Then attest with `AskUserQuestion`:

| Option | Result |
|---|---|
| Confirm | Accept the assignment; each `TZ-NNN` becomes a `[SECURITY]` obligation the feature's `/core-engineering:ce-spec` must cover. |
| Add a threat | A feature crosses a boundary the model missed — name it; add the `TZ-NNN`. |
| Remove a threat (state the reason) | A flagged feature has no real surface — record the reason; *surface-don't-force* makes this a consented exclusion, not a silent drop. |

When the summary was **No Security Surface**, attest *that* too — confirming there is
no surface is itself a model-derived negative (R2), equally rubber-stampable as a
printed line:

| Option | Result |
|---|---|
| Confirm No Security Surface | Record the attested negative — no feature crosses a trust boundary or owns a `sensitive`/`personal` noun. |
| Actually, there is a surface | Return to feature review to assign the missed threat. |

Do not offer Write (8.3) until this attestation resolves.

**Checkpoint — Threat-Model attestation (8.2.1) passed.** Once this attestation resolves,
append a `## Threat-Model Attestation (8.2.1) — passed` checkpoint to
`docs/plans/.drafts/<slug>/scratch.md` — `decided_by: human`, the option taken (Confirm /
Add a threat / Remove a threat / Confirm No Security Surface), and the resolved `TZ-NNN`
set — per SKILL.md → *Gate Checkpoint & Resume*.

### 8.2.2 Interaction-contract attestation  [material]

The interaction-contract invariants and architecture-NFR rows are **model-derived**, so
each is confirmed as its **own evidence-first prompt** (HITL Gate Standard R2/R3) —
**after** the 8.2.1 threat-model attestation and **before** Write is offered in 8.3 —
never a bullet in the 8.2 dump the human consents to by not objecting.

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

Then attest with `AskUserQuestion`:

| Option | Result |
|---|---|
| Confirm | Accept the assignment; each `IC-NNN` becomes a `[CONTRACT]` obligation the feature's `/core-engineering:ce-spec` must cover. |
| Add an invariant | A cross-feature edge / shared noun the model missed — name it; add the `IC-NNN`. |
| Remove an invariant (state the reason) | A flagged edge has no real protocol residue (e.g. a synchronous in-proc call) — record the reason; *surface-don't-force* makes this a consented exclusion, not a silent drop. |

When the summary was **No Cross-Feature Protocol**, attest *that* too — confirming there
is no cross-feature contract is itself a model-derived negative (R2), equally
rubber-stampable as a printed line:

| Option | Result |
|---|---|
| Confirm No Cross-Feature Protocol | Record the attested negative — the four detection conditions all absent: no integration boundary carrying a cross-feature edge, no Journey-Map / Dependency-Flow edge over a durable/async medium, no >1-touched durable noun, no architecture-determining NFR cited. |
| Actually, there is a cross-feature contract | Return to feature review to add the missed invariant or NFR. |

Do not offer Write (8.3) until this attestation resolves.

**Checkpoint — Interaction-Contract attestation (8.2.2) passed.** Once this attestation
resolves, append a `## Interaction-Contract Attestation (8.2.2) — passed` checkpoint to
`docs/plans/.drafts/<slug>/scratch.md` — `decided_by: human`, the option taken, and the
resolved `IC-NNN` set — per SKILL.md → *Gate Checkpoint & Resume*. A crash between the
attestations and Write re-enters at Stage 8.3 Final Decision with both attestations already
recorded.

### 8.2.3 Light-tier combined attestation  [material]

Fires **only** in the light-plan tier (§4.3), and **only** when **both** re-projections
resolved negative — threat-model = **No Security Surface** *and* interaction-contract = **No
Cross-Feature Protocol**. It replaces the separate §8.2.1 + §8.2.2 gates with **one**
attestation, cutting a stop for the small-plan case. If **either** re-projection is positive,
do **not** use this gate — fire the positive one's separate gate (§8.2.1 / §8.2.2) per the
routing table in §8.2.

**Both calls are model-derived negatives, so each still gets its own evidence-first line**
(HITL Gate Standard R2). The **R3 isolation rule** — a material call gets its own prompt —
**relaxes here, and only here, because both calls are *negatives* with their evidence
rendered**: confirming "there is no security surface" and "there is no cross-feature protocol"
are two low-coupling attested-nothings, not two independent positive assignments where one
could hide inside the other. **Any** positive detection restores the separate, isolated gates.

Render both attested-negative lines, each with its basis + cost-if-wrong, glossing from the
shared consequence-glossary exactly as §8.2.1 / §8.2.2 do (a `TZ-NNN` is a *security-review
obligation*; an `IC-NNN` is a *cross-feature behavioural-protocol obligation* or an
*architecture-determining NFR*):

```text
[1] No Security Surface — basis: no feature crosses a trust boundary and no feature owns a
    sensitive/personal noun (per the §1.2 exposure surfaces + the §6.3 data-classes).
    If wrong (NO): a feature ships with NO required security acceptance criterion for a real
    surface — the Veracode-flatline path.

[2] No Cross-Feature Protocol — basis: the four detection conditions are all absent — no
    integration boundary carrying a cross-feature edge, no Journey-Map / Dependency-Flow edge
    over a durable/async medium, no >1-touched durable noun, no architecture-determining NFR
    cited.
    If wrong (NO): a consumer ships with NO required dedupe/ordering acceptance criterion for a
    real cross-feature edge, or a load-bearing NFR goes unrecorded.
```

Then attest with `AskUserQuestion` — print the gate locator first (`Gate N of M — Combined
Attestation (No Security Surface + No Cross-Feature Protocol)`; M per the light-tier locator
set, SKILL.md item 17):

| Option | Result |
|---|---|
| Confirm both negatives | Record both attested negatives — write the **No Security Surface** section into `threat-model.md` and the **No Cross-Feature Protocol** section into `interaction-contract.md`. |
| Actually, there is a security surface | Return to feature review to assign the missed `TZ-NNN`; the **separate §8.2.1** gate now fires (and §8.2.2 per its own outcome). |
| Actually, there is a cross-feature contract | Return to feature review to add the missed `IC-NNN` / NFR; the **separate §8.2.2** gate now fires (and §8.2.1 per its own outcome). |

Do not offer Write (8.3) until this attestation resolves.

**Checkpoint — Combined Attestation (8.2.3) passed.** Once it resolves, append a
`## Combined Attestation (8.2.3) — passed` checkpoint to `docs/plans/.drafts/<slug>/scratch.md`
— `decided_by: human`, `decision: Confirm both negatives`, and the recorded No-Security /
No-Cross-Feature negatives — per SKILL.md → *Gate Checkpoint & Resume*. This one checkpoint
stands in for the separate §8.2.1 + §8.2.2 checkpoints in the light tier; choosing "Actually,
there is …" routes to the separate gate, whose own checkpoint then appends.

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

An `Add/Remove threat`, `Add/Remove invariant`, or corrected negative that
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

### 8.3 Final Decision

This is the **first true final-approval gate** — the only point that creates the
artifact. Print the locator and label each option by its consequence
(HITL Gate Standard R1/R5); the 8.2.1 threat-model and 8.2.2 interaction-contract
attestations — **or the combined §8.2.3 attestation in the light tier** — must have already
resolved, so `Write` is never the vehicle that also attests either:

```text
Gate N of M — Final Plan Approval
```

| Option | What happens next |
|---|---|
| Write | **Freeze stable IDs and write the whole plan directory** to `docs/plans/<slug>/` (+ update the registry). This is the commit point. For `recommended`, `not-required`, or `waived`, use the conditional closing below. |
| Adjust | Loop back to feature decomposition or ordering — nothing is written yet. |
| Add context | Capture additional context, then revalidate — nothing is written yet. |
| Abort | **Exit without writing — all planning work this session is lost.** |

Only `Write` creates the final artifact.

When `architecture_disposition.decision` is `required`, replace the generic
table with this four-option gate so architecture publication is an explicit
human-owned continuation, not a silent auto-run:

| Option | What happens next |
|---|---|
| **Write plan & continue to architecture** | Freeze/write the plan, then invoke `/core-engineering:ce-architecture <slug>`; the architecture workflow stops at its own human gates and no spec may start until publication succeeds. |
| **Write plan & park architecture** | Freeze/write a valid plan and stop; the missing required package remains a visible blocker for spec and auto-build. |
| **Adjust plan or context** | Return to the owning planning stage, invalidate convergence when needed, and write nothing yet. |
| **Abort** | Exit without a final plan; keep the resumable draft unless a later fresh-start decision removes it. |

**Light-plan tier (§4.3): this gate also carries the folded Candidate Review.** The feature
table and dependency flow presented at 8.2 are the decomposition, so `Write` accepts it and
`Adjust` **is** the candidate re-cut (Coarsen stays unavailable — moot at ≤ 3). One extra
option is offered, the explicit reject-path that keeps the light tier consented, never silent:

| Option | What happens next |
|---|---|
| Expand to full gates | Leave the light tier: re-run the standalone **Candidate Decision (§5.4)** and the **separate §8.2.1 / §8.2.2** attestations before Write. Records `plan_tier: standard`. |

---

## Stage 9 — Write the Plan

When the user selects `Write`, freeze final IDs — replace every provisional `P01-…` ID with its stable `01-…` slug — and write the plan **directory**:

```text
docs/plans/[project-slug]/
├── feature-plan.md       # index: overview, dependency flow, feature table, checklist
├── shared-context.md     # codebase profile, selected direction, decisions, known pitfalls
├── architecture-selection.json  # exact pre-decomposition evaluation + human direction disposition
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

For a single-feature plan accepted at the Sizing Gate, write the single-file **Recommended Minimal Output** instead of the directory (see `${CLAUDE_SKILL_DIR}/artifact-template.md`).

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

**Record the plan tier.** Write `"plan_tier": "light"` into `plan.json` (top-level, beside
`plan_revision` — see `${CLAUDE_SKILL_DIR}/artifact-template.md` → *Plan Manifest*) whenever
the run entered the **light-plan tier** (§4.3) and did **not** expand back at 8.3; write
`"standard"` or omit the key otherwise (**absent ⇒ `standard`**). Also append a
`plan-tier: light` entry to §13 Notes naming **which gates were merged** — the standalone
Candidate Decision folded into Final Approval, and (when it fired) the combined §8.2.3
attestation in place of the separate 8.2.1 / 8.2.2 — so `/core-engineering:ce-plan-audit` and a later Stage R
read the merged-gate set from the artifact instead of re-deriving it. This is a **recorded
proportionality choice**, the same discipline as the Sizing Gate's, not a silent skip.

**Lint the written plan (write-time gate).** Immediately after the plan directory, `plan.json`, and `plans.json` are written — and **before** deleting the gate-checkpoint scratch — run the structural-integrity lint over the *persisted* artifact, so nothing closes on a plan that fails a mechanical invariant the ~40-item Validation Checklist below only self-attests. This is the on-disk twin of `/core-engineering:ce-plan-audit`'s hard lint, run here at the moment of writing:

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/architecture-selection-lint.py" \
  docs/plans/<slug>/architecture-selection.json --json
python3 "${CLAUDE_SKILL_DIR}/scripts/plan-lint.py" \
  docs/plans/<slug> --require-architecture-direction --json
```

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
