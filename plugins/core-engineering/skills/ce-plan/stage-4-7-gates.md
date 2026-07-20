# Feature-Plan Workflow — Stages 4–7: Gates

Stage file for the `plan` skill (orchestrator: `SKILL.md`). Covers the Sizing Gate, Candidate Plan Review, Reachability / Consumability Trace, and Session-Fit Check. Load this file after Stage 3 is complete.

**Next:** when Stage 7 passes, load `${CLAUDE_SKILL_DIR}/stage-8-9-write.md`. If the Sizing Gate accepts a single-feature plan at Stage 4, go straight to `${CLAUDE_SKILL_DIR}/stage-8-9-write.md`.

---

## Stage 4 — Sizing Gate

Before presenting a multi-feature plan, evaluate whether the project actually warrants decomposition.

Recommend a single-feature plan if any of the following hold:

1. **Single-Simple fits**  
   Total scope scores Simple on every Complexity dimension and Brownfield friction is not High.

2. **Not independently separable**  
   Candidate features share layout, deployment, or data model so tightly they cannot be shipped or validated separately.

3. **Spec overhead exceeds implementation surface**  
   The generated plan and downstream feature specs would outweigh the actual implementation work.

4. **No meaningful dependency chain exists**  
   The work can be implemented as one cohesive change without losing reviewability.

---

### 4.1 Sizing Result Block

If the project fails the Sizing Gate, present this block. Print the **gate locator**
and label each option by its consequence — `Accept` is a *terminal early-exit* that
skips every later gate, so that cost must be in the option text
(HITL Gate Standard R1/R5):

```markdown
Gate N of M — Sizing   (N/M per the gate-locator discipline in SKILL.md)

## Sizing Result

Recommendation: Single-feature plan

Reason:
- [specific reason 1]
- [specific reason 2]

If you Override, this is the multi-feature split you'd get instead:
- P01-<slug> · P02-<slug> · P03-<slug>   (<one-line shape of the split>)

Options:
1. Accept — write ONE single-feature artifact and EXIT now. This skips the Candidate
   Review, Reachability, Session-Fit, and Final-Approval gates entirely.
2. Override — build the multi-feature plan previewed above instead: more specs to
   review and a longer pipeline, but each feature ships and is reviewed independently.
3. Adjust — revise the project scope or decomposition approach, then re-size.
```

If the user selects:

| User Choice | Result |
|---|---|
| Accept | Write a single-feature artifact and exit — **skips Stages 5–8** |
| Override | Continue with the multi-feature plan previewed above |
| Adjust | Loop back to candidate feature decomposition |

On `Accept`, write the single-feature artifact using the **Recommended Minimal Output** structure in `${CLAUDE_SKILL_DIR}/artifact-template.md`.

---

### 4.2 Checkpoint — Sizing Gate passed

Append a `## Sizing Gate — passed` checkpoint to `docs/plans/.drafts/<slug>/scratch.md` per
SKILL.md → *Gate Checkpoint & Resume* when the run continues into the multi-feature flow:

- If the Sizing Result block fired and the human chose **Override**, record
  `decided_by: human`, `decision: Override`, and the previewed split.
- If the project passed the gate **without** a prompt (a plain multi-feature request),
  record `decided_by: workflow (autonomous pass)` and the candidate feature set — resume
  still needs a Stage-4 anchor.

`Accept` exits to a single-feature write (Stage 9 cleans up any scratch), so it needs no
forward checkpoint; `Adjust` loops back and appends nothing.

---

### 4.3 Light-Plan Tier Detection

Once the Sizing Gate has confirmed a **multi-feature** plan, screen it for the
**light-plan tier** — a proportionality mode that folds ceremony without dropping any
correctness gate, taking a small plan's ~8 interactive stops down to ~4. This is a
**mechanical screen, not a prompt** (an extra gate here would defeat the purpose): if
**all three** hold on the scored candidate set, the run enters the light tier —

1. **≤ 3 candidate features** (the single-feature case already took the Sizing early-exit).
2. **No contested Boundary-Owner** — no cross-cutting or interface-foundation category is
   claimed by more than one candidate (the §7.5 uniqueness guard has nothing to reconcile).
3. **No `sensitive` data-class in sight** — no candidate obviously writes a `sensitive`
   noun (credentials, financial, health, biometric, precise location) per the Stage 1–3
   profile. This is a **preliminary** screen; the definitive data-class is assigned in §6.3
   and the security surface is re-checked at 8.2 (see the auto-restore below).

If any condition fails — or the plan has more than 3 features — the run stays **standard
tier** and every gate fires as written (a 4-plus-feature plan is entirely unchanged by this
section).

**What the light tier folds (ceremony only).** Entering the light tier sets `plan_tier:
light` (recorded in `plan.json` and §13 Notes at write time — Stage 9) and folds:

- the standalone **Candidate Decision (§5.4)** does **not** fire — the candidate table and
  provisional order carry forward and are reviewed inside the **Final Plan Review (8.2/8.3)**,
  whose decision then carries Proceed / Adjust. **§5.5 Coarsen is unavailable** — with ≤ 3
  features a scope-preserving merge is moot;
- the two material attestations **8.2.1 + 8.2.2** combine into **one** gate (§8.2.3), but
  **only when both re-projections resolve negative** at 8.2 (No Security Surface **and** No
  Cross-Feature Protocol).

**What it never folds (the correctness floor).** Reachability / Consumability (§6, gate
§6.6) and Session-Fit (§7) run **in full** — they are correctness, not ceremony — using the
collapsed-row rendering §6.6 already defines. The combined attestation still renders **each**
attested-negative as its own labeled line with basis + cost-if-wrong (§8.2.3): nothing
material is skipped, only co-located.

**Auto-restore on any real surface.** The attestation combine is contingent, re-evaluated at
8.2. If §6.3 later assigns a `sensitive` noun, or the threat-model / interaction-contract
re-projection detects a real surface, the **separate** material gate (§8.2.1 / §8.2.2) fires
automatically for that re-projection — a positive detection is never swept into a combined
negative (Done-when: *a light plan whose threat-model detects a real surface gets the
separate 8.2.1 gate back automatically*). The candidate-review fold (§5.4 → 8.3) is
orthogonal to security and stays folded regardless.

**Consented, never silent.** The tier is **disclosed** the moment it is entered — print, in
the conversation (not a dialog):

> *Light-plan tier: ≤ 3 features, no contested ownership, no sensitive data in sight.
> Candidate review folds into Final Approval; trivially-negative attestations combine.
> Reachability and Session-Fit still run in full. Recorded as `plan_tier: light`; you can
> expand back to the full separate gates at Final Approval.*

The human's affirmative **Write** at 8.3 (which now carries the folded candidate review) is
the consent, and 8.3 offers an explicit **Expand to full gates** back-edge — so the tier is
disclosed, recorded, and rejectable, never a silent skip.

**Checkpoint — Light-Plan Tier passed.** Append a `## Light-Plan Tier — passed` checkpoint
to `docs/plans/.drafts/<slug>/scratch.md` (per SKILL.md → *Gate Checkpoint & Resume*):
`decided_by: workflow (autonomous pass)`, `decision: enter light tier` (or `standard tier`
when the screen failed), and a `state:` block holding the screen result + candidate set. In
the light tier this is the Stage-4/5 resume anchor **in place of** the §5.4 Candidate
Decision checkpoint (which does not fire).

---

## Stage 5 — Candidate Plan Review

Stage 5 presents the candidate plan before detailed reachability and final session-fit validation.

This is not final approval.

The user is only approving the candidate plan for further validation.

---

### 5.1 Assign Provisional IDs and Order

Order provisional features so expected dependencies come first.

Use provisional IDs:

```text
P01-feature-name
P02-feature-name
P03-feature-name
```

Mark dependencies as:

```text
hard
soft
```

Do not freeze final IDs yet.

---

### 5.2 Present Candidate Plan

Print the candidate plan to the conversation as Markdown.

Include:

- dependency-flow diagram
- feature summary table
- per-feature blocks
- sizing line
- Risk-Profile
- Boundary-Owner
- Open-Unknowns
- Scope
- Excluded
- Dependencies
- Unlocks

---

### 5.3 Two-Surface Rendering Rule

When presenting structured content before asking for a decision:

1. Print long content in the conversation as Markdown.
2. Use the decision prompt only for the short question and options.

Long tables, diagrams, and multi-paragraph context must not be placed inside compact decision dialogs because Markdown may not render correctly there.

---

### 5.4 Candidate Decision

> **Light-plan tier (§4.3):** this standalone gate **does not fire**. The candidate table
> and provisional order carry forward to the **Final Plan Review (8.2/8.3)**, whose decision
> carries Proceed / Adjust (Coarsen is unavailable — §5.5 is moot at ≤ 3 features). Run §5.4
> **and** §5.5 as written **only in the standard tier**; in the light tier the resume anchor
> is the §4.3 checkpoint, not this one.

Print the gate locator, then ask. Label each option by what it does next — and note
that **`Continue` is not final approval**, it advances to two more validation gates
(HITL Gate Standard R1/R5):

```text
Gate N of M — Candidate Review

Continue, Coarsen, Adjust, Add context  (or Decide a fork)?
```

Options:

| Option | What happens next |
|---|---|
| Continue | **Not final approval** — validates this candidate through the Reachability and Session-Fit gates (two more gates before you can Write). |
| Coarsen | **Scope-preserving** — re-slice the *same* Scope into fewer, larger features (name a target count or "coarsest viable"). Trades session-fit headroom + per-diff review granularity for fewer spec→implement loops; records a consented session-fit relaxation, then re-runs Reachability + Session-Fit, which can still **reject** an over-coarse merge. **Not** an MVP cut (that drops scope — use Adjust) and **not** the single-feature collapse (that's the Sizing Gate). See §5.5. |
| Adjust | Loop back to feature decomposition and re-cut. |
| Add context | Capture more context, then loop back to feature decomposition. |
| Decide a fork | *(offer only when the escalation note below applies)* Send one no-dominant-option architecture fork to `/core-engineering:ce-decide` before committing the cut. |

> **Escalating an architectural fork to `/core-engineering:ce-decide` (optional, human-triggered).** If this
> candidate decomposition hinges on an unresolved **technical/architecture fork with no
> dominant option** — a choice that changes *how* features are cut (event-sourced vs CRUD,
> extract-a-service vs in-monolith, a shared persistence model) — the human may escalate it
> to `/core-engineering:ce-decide` for a situation-weighted scorecard before committing the
> cut; its **proposed ADR** feeds back as a Resolved Project Decision the plan and
> downstream specs honor. This review and the Sizing Gate already *detect* forks, so
> `/core-engineering:ce-decide` adds **rigor on the rare hard one, not a second detector** — reserve it for a
> genuine no-dominant-option fork. A fork that is really a *scope* change stays a `/core-engineering:ce-plan`
> matter (re-cut here), not a `/core-engineering:ce-decide`. **When this note applies, surface `Decide a fork`
> as the labeled option above — decidable in the dialog — rather than leaving it as prose
> the human must volunteer (R1).**

Do not write the artifact after this decision.

**Checkpoint — Candidate Decision passed.** On `Continue`, append a `## Candidate Decision
— passed` checkpoint to `docs/plans/.drafts/<slug>/scratch.md` — `decided_by: human`,
`decision: Continue`, and a `state:` block holding the current candidate feature table +
provisional order — per SKILL.md → *Gate Checkpoint & Resume*. The back-edge options
(`Coarsen` / `Adjust` / `Add context` / `Decide a fork`) loop without advancing, so they
overwrite the pending state rather than append a passed-gate block.

---

### 5.5 Coarsen — scope-preserving merge

> **Light-plan tier (§4.3):** `Coarsen` is **unavailable** — a scope-preserving merge into
> fewer features is moot at ≤ 3 features. This subsection applies only in the standard tier.

`Coarsen` answers a need the Sizing Gate cannot: the plan is genuinely multi-feature,
but the user wants **fewer, larger features over the same scope** — fewer
spec→implement loops, traded against session-fit headroom and review granularity. It
is distinct from its two neighbors:

- **Adjust** re-cuts and may **drop or change scope** (an MVP decision).
- **Sizing-Gate Accept** collapses the whole plan to **one** feature.
- **Coarsen** holds the **union of Scope invariant** — no Scope item is dropped — and
  merges cohesive candidates into a smaller feature set (a named target *N*, or
  "coarsest viable").

**The Coarsening Lease (consented, recorded).** A merged feature may exceed the
one-implementation-session envelope (Stage 2.3 / 3.5). Coarsening *is* the human
consenting to that, so the consent is recorded as a **lease** — without it, Stage 3's
`cannot_fit_in_one_impl_session` split would silently undo the merge on the next pass.
Record, in the artifact's *Why This Split* / Notes **and** on each affected feature's
sizing block (`session_fit: consented-coarsened`), which features are
consented-oversized and the one-line trade-off the user accepted. **No silent
oversize** — every consented-large feature is flagged.

**Guards still hold (the floor).** The coarser set re-enters decomposition, then
**re-runs Reachability (§6) and Session-Fit (§7) in full**. The lease relaxes only the
*size* veto; the **correctness** guards are not relaxed and can **reject** an
over-coarse merge — dependency-graph soundness (§7.1), Cross-Feature MODIFY reach
(§7.2), Boundary-Owner uniqueness (§7.5, a merge can't give one feature two ownership
roles), and bridge integrity (§7.7). A rejected coarsen loops back with the reason
shown — bounded by the same re-cut discipline as `Adjust` (repeated non-convergence
escalates to the user, never loops forever).

**Trade-offs the option must carry (decidable in the dialog — HITL R1).** When
offering `Coarsen`, state its costs so the human chooses with eyes open: a merged
feature's diff is **reviewed as one unit**, so review attributability drops; under
`/core-engineering:ce-auto-build`, merging independent features means fewer but larger sequential work
units; and a larger feature **re-imports some context-compaction risk** (mitigated by
the fresh worker context created for each feature).

**Not a lock breach.** Stage 5 is **pre-freeze** — IDs are provisional until Stage 9
(SKILL.md → *Feature ID*). Coarsening here is `/core-engineering:ce-plan` **authoring** boundaries, not
widening an already-frozen one, so it does not violate *escalate-up-never-expand*
(that lock governs a downstream stage widening a frozen boundary, not the plan setting
its own cut).

---

## Stage 6 — Reachability / Consumability Trace

A feature can be technically complete but unusable because surrounding surfaces have not shipped yet.

This stage validates whether the planned ship order is practically usable.

Use one of two modes:

| Project Type | Trace Mode | Verification Modality |
|---|---|---|
| UI application | User Journey Trace | browser (e.g. Chrome DevTools MCP) |
| Backend API | Consumability Trace | HTTP request (e.g. `curl` / client) |
| CLI tool | Consumability Trace | CLI invoke (args → stdout / exit code) |
| SDK / library | Consumability Trace | SDK call (import → call → assert return/error) |
| Worker / event system | Consumability Trace | event emit + observe |
| Infrastructure / IaC | Consumability Trace | plan / apply + observe |

A journey is **testable-by-design**: each step records not just structure but **how its success is observed**. Capture two things:

- **per journey, a primary verification modality** — the dominant tool class from the table above; and
- **per step, an expected observable** (the concrete signal that proves the step passed) **and the step's own modality** when it differs from the primary.

This is *verification intent*, not *test mechanics*: declare **what** to observe and **which tool class**; the exact selectors / flags / payloads are derived later in `spec` against the real design (do not invent them here — the routes and surfaces don't exist yet). The downstream consumers — `spec` (which turns each owned step into a test case) and the verifiers (`verify`, `ce-ux-audit`) — read the modality to pick their tool instead of guessing it.

**Journeys are often multi-modal.** A real path crosses surfaces — e.g. a web checkout: *click checkout* (`browser`) → *payment webhook* (`event` / `http`) → *order row written* (`db`) → *confirmation email* (`manual`). Record the primary modality on the journey and override per step where it changes; never flatten a multi-surface journey to one tool. A full-stack repo carries several journeys of mixed modality (UI journeys **and** consumability traces simultaneously) — that is expected, not an either/or.

**Modality vocabulary:** `browser` · `http` · `cli` · `sdk` · `event` · `iac` · `db` (data/state assertion — a row, document, or cache entry was written) · `manual` (no tool can drive it — pure human observation). Extend as the stack needs (e.g. `mobile`, `desktop`, `stream`).

**Tool fallback (never silent).** A modality names the tool class a verifier *should* use; it does **not** guarantee that harness exists. If a step's modality can't be driven downstream (no browser MCP, no live external system), it degrades to a **human-run check** — recorded in `spec` as `manual:harness-gap`, never dropped. Capture the intended modality here regardless; the degradation is a downstream concern, but it must be loud.

---

## 6.1 UI User Journey Trace

Use this mode for projects with user-facing UI surfaces.

A primary journey is an end-to-end path such as:

```text
entry navigation
→ list / browse
→ action
→ form
→ submission
→ confirmation
→ return
```

Most projects have up to 3 primary journeys. Complex projects may have up to 5.

Reuse workflows already named in Stage 1.4 when available. Otherwise, ask interactively.

---

### 6.1.1 Failure Modes Prevented

The trace prevents:

| Failure Mode | Meaning |
|---|---|
| Orphaned entry | Capability exists but no UI points to it |
| Bridged-but-degraded entry | A stopgap exists but surrounding context is fake or incomplete |
| Dead-ended exit | User completes the action but cannot naturally continue or return |

---

### 6.1.2 Map Journey Steps to Features

For each journey, produce a table — including each step's **expected observable** (what proves it passed) and its **modality** (inherit the journey's primary unless the step crosses to another surface, as step 4 does below):

| Step | Surface | Owned By | Reachability | Modality | Expected observable |
|---|---|---|---|---|---|
| 1 | Entry navigation | P01-dashboard-shell | provided | browser | dashboard renders; "Create" visible |
| 2 | Create item button | P02-create-item | n/a | browser | click opens the create form |
| 3 | Confirmation | P02-create-item | provided | browser | confirmation shows the new item's id |
| 4 | Return to list | P04-item-list | bridge: temporary success page with back-to-dashboard link | db | new item row persisted and appears in the list |

Keep expected observables outcome-level (what the user/consumer sees), not mechanics (selectors, exact markup) — those come from `spec`.

Reachability values:

| Value | Meaning |
|---|---|
| provided | Owning feature ships before or with the current step |
| bridge: description | Current owner must provide a temporary stopgap |
| n/a | The step is owned by the current feature itself |

---

### 6.1.3 Bridge Cost Ceiling

If a bridge requires any of the following, it is too expensive:

- more than approximately 5 files
- more than approximately 200 LOC
- a new integration boundary
- significant new data model work
- new authorization behavior
- new migration
- complex UI state management

If bridge cost is too high, loop back to ordering or re-cutting.

---

## 6.2 Backend / CLI / SDK / Worker Consumability Trace

Use this mode for projects without UI surfaces.

Do not skip reachability entirely.

Validate how another user, module, system, or operator discovers, invokes, verifies, and recovers from each feature.

---

### 6.2.1 Consumability Journey Examples

| Project Type | Consumability Journey |
|---|---|
| REST API | Consumer authenticates, calls endpoint, receives response, handles errors |
| CLI | User discovers command, passes arguments, receives output, handles failure |
| SDK/library | Developer imports function, calls it, handles return/error types |
| Worker/event system | Event is produced, consumed, retried, and observed |
| Infrastructure/IaC | Operator configures, plans, applies, verifies, and rolls back |
| Batch job | Operator starts job, monitors progress, handles partial failures |

---

### 6.2.2 Consumability Table

Example (primary modality = `http`; add a `Modality` column and override per step where it changes — here the final step crosses to `event`):

| Step | Surface | Owned By | Reachability | Modality | Expected observable |
|---|---|---|---|---|---|
| Consumer obtains token | Auth foundation | P01-auth-foundation | provided | http | `POST /auth` → 200 + token |
| Consumer calls create endpoint | Orders API | P02-orders-api | n/a | http | `POST /orders` → 201 + Location |
| Consumer receives validation error | Error contract | P02-orders-api | provided | http | bad body → 400 + error contract shape |
| Event is emitted | Order events | P04-order-events | bridge: temporary no-op publisher | event | `order.created` observed on the bus |

Keep expected observables outcome-level (status, response shape, exit code, emitted event), not mechanics (exact flags, payloads) — those come from `spec`.

---

## 6.3 Durable-State Closure

A trace built from forward journeys is **open under the state it creates**: a step
can persist a durable noun and the trace never asks how a user gets **back** to it.
That gap is the create-without-manage funnel — create works, but list / reopen /
switch / edit were never owned by any feature. This pass **closes** the trace:
for every durable noun a journey writes, the three reciprocal obligations are made
explicit and each is dispositioned exactly once.

Applies to **both** trace modes. The API-layer case — a `POST` resource with no
`GET` / list / `PATCH` / `DELETE` a consumer drives — is the same failure as a
missing list screen.

### 6.3.1 Detect durable nouns

Scan every journey / consumability step for a durable-state write — modality `db`,
or `event` / `iac` against a persisted target. Each distinct written noun gets a
closure row. Assign each an **access-mode**, defaulting to the stricter
`user-owned-mutable`:

| Access-mode | Meaning | Default |
|---|---|---|
| `user-owned-mutable` | a user creates and owns instances they expect to return to and change | assume unless argued down |
| `system-or-append-only` | logs, events, audit rows, derived projections, immutable-after-submit records | only by explicit downgrade + reason |

Alongside the access-mode, assign each durable noun a one-time **data-class**,
defaulting to the stricter `personal`. Access-mode answers *who returns to manage
it*; data-class answers *what governance the data itself owes*. The two are
orthogonal — a `user-owned-mutable` noun may be `operational`, a
`system-or-append-only` audit row may be `sensitive`:

| Data-class | Meaning | Default |
|---|---|---|
| `personal` | identifies or is attributable to a person — profile, contact, content they authored, anything keyed to a user | assume for any user-attributable noun unless argued down |
| `sensitive` | a regulated or high-harm subset of personal — credentials, financial, health, biometric, precise location, special-category data | only by explicit **upgrade** + reason (stricter than `personal`) |
| `operational` | non-attributable system data — config, derived projections, queue rows, infra state with no person behind it | only by explicit **downgrade** + reason (looser than `personal`) |

Data-class is **human-attested, assigned once per noun**, and recorded in the
closure row. It is not re-litigated downstream: `spec` and `verify` read it, they
never reset it.

### 6.3.2 Emit and dispose the reciprocals

For each durable noun, emit three reciprocal obligations and disposition each using
the **existing reachability vocabulary**:

| Reciprocal | Meaning | `user-owned-mutable` | `system-or-append-only` |
|---|---|---|---|
| `revisit` | list / find / reopen an instance | mandatory disposition | mandatory disposition |
| `amend` | change an existing instance | mandatory disposition | pre-`excluded` (override w/ reason) |
| `retire` | delete / archive / cancel | pre-`excluded` (override w/ reason) | pre-`excluded` (override w/ reason) |

Disposition values:

| Value | Meaning |
|---|---|
| `owned-by: <feature-id>` | a feature provides the surface; auto-filled when the plan already owns it (no human action) |
| `bridge: <desc>, replaced_by: <feature-id>` | consented forward stopgap, under the §6.1.3 Bridge Cost Ceiling |
| `excluded: <reason>` | consented terminal-by-design; recorded in §13 Notes |

A mandatory reciprocal satisfied **only** by a select-to-continue consumer (a
downstream step that lists instances to pick one, e.g. a wizard) does **not** count
as `owned-by` — that surface lets you *choose forward*, not *return to manage*. It
must be owned by a return-to-manage surface or consented `excluded`.

### 6.3.2a Emit and dispose the governance reciprocals

The access-mode triad above closes the noun for *use*; the data-class drives a
second, orthogonal triad that closes it for *governance*. Emit three governance
reciprocals per durable noun and disposition each using the **same disposition
vocabulary** (`owned-by` / `bridge` / `excluded`):

| Reciprocal | Meaning | `personal` / `sensitive` | `operational` |
|---|---|---|---|
| `retain` | a stated retention/expiry policy — how long it lives and what ends it | mandatory disposition | pre-`excluded` (override w/ reason) |
| `export` | a consumer can obtain the subject's data in a portable form | mandatory disposition | pre-`excluded` (override w/ reason) |
| `erase` | a subject-driven delete/forget that removes the data, not just hides it | mandatory disposition | pre-`excluded` (override w/ reason) |

`erase` is the governance sibling of `retire`, not a duplicate: `retire`
archives/cancels an instance a user no longer wants visible; `erase` is the
subject's right to have the data *gone*. A noun may own `retire` and still owe
`erase`. Where one surface genuinely satisfies both, disposition `erase`
`owned-by:` the same feature and note the shared surface in §13.

A governance reciprocal satisfied **only** by an operator-side admin tool or a
manual back-office runbook does **not** count as `owned-by` unless that surface is
a real, owned consumer the policy actually reaches — the same select-to-continue
rule above. A `retain` policy with no enforcing job, an `export` verb with no
consumer, or an `erase` that only soft-hides is an **undispositioned** reciprocal,
not a satisfied one.

### 6.3.3 No silent bulk-exclusion

A run of identical or near-identical `excluded:` reasons across nouns is a
re-decomposition smell — surface it, never accept it silently. The closure exists
to make each absence a named decision, not a checkbox swept in one motion.

The smell applies to **both** triads. A run of identical `excluded:` governance
reasons across `personal` nouns is especially loud — "no retention/export/erase
anywhere" is a compliance posture, not a per-noun planning decision, and must be a
named, consented call recorded in §13, never a swept default.

### 6.3.4 On an undispositioned or wrongly-satisfied reciprocal

Route into the §6.6 Reachability Decision loop (Approve / Reorder / Adjust): re-cut
the creating feature to own the loop, add an entity-management feature, reorder so
an owning feature ships in range, or record a consented `excluded`. This pass
**detects and routes** — it never widens a feature's scope itself (escalate up,
never expand).

Governance reciprocals route the same way. An undispositioned mandatory `retain` /
`export` / `erase` is a missing owner, not a scope to bolt onto the creating
feature: re-cut to own the policy, add a data-governance feature, reorder so an
owning feature ships in range, or record a consented `excluded` with a reason in
§13 — never silently widen scope (escalate up, never expand). Downgrading a noun's
data-class to dodge a mandatory governance reciprocal is itself a material
decision: state the reason, never relabel to escape the obligation.

---

## 6.4 Surface-Removal Closure

A trace built from forward journeys is also **open under the surfaces it breaks**: a
feature can remove, rename, or incompatibly change an **already-shipped public
surface** and the trace — which only walks the journeys this plan adds — never asks
what happens to the consumers already depending on the old one. That gap is the
remove-without-deprecate funnel — the new shape ships, but existing callers were
never owned by any feature. This pass is the inverse of §6.3: where §6.3 closes the
state a journey *writes*, this closes the surface a feature *removes*. For every
existing public surface a feature's scope breaks, the continuity obligation is made
explicit and dispositioned exactly once.

Applies to **both** trace modes and only to **brownfield** plans — it keys off the
existing shipped surfaces recorded in the Stage 1.2 codebase profile
(`public_interaction_surfaces`, `data_surfaces.event_schemas`). A greenfield plan
with no prior surfaces skips this pass and records it `N/A`.

### 6.4.1 Detect broken surfaces

Scan every feature's **Scope** and **Excluded** for a change that removes, renames,
or incompatibly changes a surface that already exists in the Stage 1.2 profile — a
route, an SDK / exported-function signature, an event / message schema, a CLI flag
or command, or a config key. Each distinct broken surface gets a closure row.
Assign each a **break-class**, defaulting to the stricter `contract-break`:

| Break-class | Meaning | Default |
|---|---|---|
| `contract-break` | an external or cross-team consumer relies on the surface (a public route, published SDK signature, documented event schema, stable CLI flag, supported config key) | assume unless argued down |
| `internal-only` | the only consumers are inside this plan's own boundary and move in the same change (a private helper, an unreleased route, an internal-only event) | only by explicit downgrade + reason |

A `removed` or renamed surface still consumed by a step in this plan's own
Reachability / Consumability Trace is a planning error, not a `contract-break` — fix
the order or the cut, do not deprecate a surface this plan still drives.

### 6.4.2 Emit and dispose the continuity obligation

For each broken surface, emit one continuity obligation and disposition it. A
`contract-break` carries a **mandatory disposition**; an `internal-only` surface is
pre-`hard-break` (it needs no window) but is still recorded:

| Continuity | Meaning | `contract-break` | `internal-only` |
|---|---|---|---|
| `continuity` | how existing consumers cross from the old surface to the new | mandatory disposition | pre-`hard-break` (override w/ reason) |

Disposition values:

| Value | Meaning |
|---|---|
| `deprecate: <window>, removed_by: <feature-id>` | old surface kept working alongside the new, with a stated window; a later feature owns its removal (a hard dependency, like a bridge in reverse) |
| `shim: <desc>, owned-by: <feature-id>` | a migration shim / adapter / redirect carries old consumers onto the new surface, under the §6.1.3 Bridge Cost Ceiling |
| `hard-break: <reason>` | consented incompatible break — no window, no shim; recorded in §13 Notes with the reason and the blast radius |

A disposition satisfied **only** by the new surface existing ("callers can just use
the new route") does **not** count — that is the break itself, not a continuity
plan. It must name a window, a shim, or a consented `hard-break`.

### 6.4.3 No silent bulk-break

A run of identical or near-identical `hard-break:` reasons across surfaces is a
blast-radius smell — surface it, never accept it silently. The closure exists to
make each break a named decision with its consumers weighed, not a sweep waved
through in one motion.

### 6.4.4 On an undispositioned or wrongly-satisfied continuity

Route into the §6.6 Reachability Decision loop (Approve / Reorder / Adjust): re-cut
the feature to keep the old surface alongside the new, add a deprecation /
migration feature that owns the removal, reorder so the window spans the break, or
record a consented `hard-break`. This pass **detects and routes** — it never widens
a feature's scope to absorb the deprecation itself (escalate up, never expand).

---

## 6.5 Aggregate Bridges by Feature

For each feature that ships at least one bridge, produce a bridge block.

Example:

```yaml
feature: P02-create-order
bridges:
  - type: exit
    description: "Show temporary order-submitted page until order history exists."
    replaces: "Missing order history return surface"
    replaced_by: "P04-order-history"
```

Features with no bridges are omitted from this section.

---

## 6.6 Reachability Decision

This is the **densest gate in the workflow** — it carries the Journey Map, the §6.3
durable-state reciprocals (use **and** governance), the §6.4 surface-removal rows, and
bridge blocks. A raw dump invites a rubber-stamp `Approve`. Present it under the
dense-gate discipline (HITL Gate Standard R3/R4/R5) so the human can act in
place, without scrollback and without attesting blind.

### 6.6.1 Render order

1. **Gate locator** — `Gate N of M — Reachability` (per the SKILL.md locator discipline).
2. **"What needs your decision"** — lead with ONLY the rows that need a human call,
   each numbered `R1, R2, …` (so `Change a disposition` can target one) and each with
   its **basis + plain-language cost-if-wrong** (evidence-first, R2). A row needs a
   call when it is:
   - **undispositioned** — a mandatory reciprocal or continuity with no `owned-by` /
     `bridge` / `deprecate` / `shim` yet, or one "satisfied" only by a
     select-to-continue surface (§6.3.2) or by the new surface merely existing (§6.4.2);
   - a **non-default override** — a durable noun whose **data-class** is anything other
     than the safe default `personal` (a downgrade to `operational` sheds the
     keep/copy/delete duties; an upgrade to `sensitive` adds a security duty), or a
     **break-class** downgraded `contract-break → internal-only` (which sheds the whole
     continuity obligation). Render the basis: *"`saved-search` set to `operational` —
     no person behind it? If wrong, it ships with no keep/copy/delete duty for user data."*
   - a **⚠ bulk run** — two or more near-identical `excluded:` (or `hard-break:`)
     reasons across nouns/surfaces. **Never collapse this into the auto-resolved count**
     (§6.3.3 / §6.4.3): "no retention/export/erase anywhere", or "break everything for
     `<reason>`", is a *posture* the human must consent to, not a per-item default.
3. **Auto-resolved (count)** — collapse every row already `owned-by:` a feature in this
   plan into one count with a `[details ↓]` pointer; do not make the human read them.
4. **Legend** — print this legend alongside the rows. It is the **runtime home** of the
   shared consequence-glossary (the HITL Gate Standard doc mirrors it for contributors —
   keep the two in sync; do not re-derive glosses, a term must read the same at every gate):

   | Term | Means |
   |---|---|
   | durable noun | something the app saves that a user expects to return to (a saved search, an order, a profile) |
   | reciprocal | the matching ability a saved thing needs — if you can create it, can you find / change / delete it? |
   | `revisit` / `amend` / `retire` | find it again / change it / delete-or-archive it |
   | `retain` / `export` / `erase` | how long it's kept / get a copy of it / permanently delete it |
   | access-mode | `user-owned-mutable` (users create + edit) vs `system-or-append-only` (a log nobody edits after the fact) — sets which reciprocals are mandatory |
   | data-class | `personal` (tied to a person — safe default) · `sensitive` (regulated: credentials/health/money) · `operational` (no person behind it). **Downgrading to `operational` drops the keep/copy/delete duties — a material move, not a default.** |
   | `owned-by` / `bridge` / `excluded` | a feature provides it (no action) / a temporary stand-in a later feature replaces / intentionally never built (ship without it) |
   | break-class | `contract-break` (an outside caller depends on it — default) vs `internal-only` (only this plan's own code uses it) |
   | `deprecate` / `shim` / `hard-break` | old surface kept for a stated window / an adapter carries old callers over / old surface breaks immediately |
   | select-to-continue | a screen that lists things only to pick one and move forward (a wizard) — does **not** count as "find it again" |
   | Scope Lock | the boundary a stage may not widen from inside — **frozen for this run; widening goes up a layer, never through it**; each stage locks a different scope (spec's planned feature boundary, implement's approved spec, patch's frozen file set, the scans' framed decision space, ship-release's release decision) |
5. **Full Journey Map / Consumability Trace + bridge blocks** — last, for reference.

### 6.6.2 The decision

Ask (the locator is already printed), labeling each option by its consequence:

| Option | What happens next |
|---|---|
| Approve trace | Accept every disposition shown — **including the ⚠ overrides and bulk runs above** — and continue to the Session-Fit Check. |
| Change a disposition | Pick a numbered row `R#`; you're offered **only that row's legal values** (a §6.3 reciprocal: `owned-by` / `bridge` / `excluded`; a §6.4 continuity: `deprecate` / `shim` / `hard-break`), each consequence-labeled from the legend. The pass then re-runs the §6.3.4 / §6.4.4 satisfaction check and re-prints "What needs your decision". |
| Reorder | Loop back to provisional ordering (a different ship order may auto-dispose a row). |
| Adjust journeys | Loop back to journey / consumer-flow collection. |

`Change a disposition` is the object-level edit — it **never widens a feature's scope
itself** (escalate up, never expand, §6.3.4): choosing `excluded` / `hard-break`
records a consented absence, while choosing `owned-by` routes to a re-cut or a new
entity-management / deprecation feature.

### 6.6.3 Checkpoint — Reachability Decision passed

On `Approve trace`, append a `## Reachability Decision — passed` checkpoint to
`docs/plans/.drafts/<slug>/scratch.md` — `decided_by: human`, `decision: Approve trace`,
and a `state:` block holding the **resolved disposition rows** (the durable-noun use and
governance reciprocals and the §6.4 surface-removal continuity rows, as dispositioned) plus
the Journey / Consumability Map — per SKILL.md → *Gate Checkpoint & Resume*. This is the
marathon gate the checkpoint most protects: a crash after `Approve` re-enters at the
Session-Fit Check, not back at the trace. `Change a disposition`, `Reorder`, and `Adjust
journeys` loop without advancing and append nothing.

---

## 6.7 Iteration Cap

For each journey or consumability trace, allow at most 3 loops.

On the third loop without convergence, escalate to the user. Label each option by its
consequence (HITL Gate Standard R1) — both are lossy:

| Option | What happens next |
|---|---|
| Defer journey | **Drop this journey from the MVP** — recorded under Notes, not built this plan. Use only when it is genuinely out of MVP. |
| Abort plan | **Exit the workflow without writing** — all planning work this session is lost; revisit the decomposition input and restart. |

Deferred journeys must be explicitly recorded in the final artifact.

---

## Stage 7 — Session-Fit Check

The Session-Fit Check is mandatory.

It validates dependency graph shape, implementation reach, reviewer pressure, risk distribution, and boundary ownership.

The workflow must not write an artifact until this check passes or the user explicitly aborts/defer-scope where allowed.

**Under a consented Coarsening Lease (§5.5), only the *size* veto is relaxed** — the
one-session-fit / complexity-ceiling split is suspended for the leased features (each
flagged `session_fit: consented-coarsened`). The **correctness** checks below — 7.1
graph soundness, 7.2 MODIFY-reach, 7.5 Boundary-Owner uniqueness, 7.7 bridge integrity
— are **not** relaxed and still fail-and-loop on an over-coarse merge.

---

### 7.1 Dependency-Graph Soundness

Rules:

- Every hard dependency must point to an earlier feature.
- No direct cycles are allowed.
- No transitive cycles are allowed.
- A backwards hard dependency is a planning failure.
- A feature with no dependencies must still deliver value or establish a verifiable foundation.

Failure resolution:

```text
merge
reorder
re-cut
remove invalid dependency
convert hard dependency to soft dependency only if a real bridge/fallback exists
```

---

### 7.2 Cross-Feature MODIFY Reach

Count how many other features each feature must modify.

Distinguish:

| Relationship | Meaning |
|---|---|
| CALL | Uses another feature's public interface |
| MODIFY | Edits files, behavior, or internal structures owned by another feature |

Rule:

```text
If a feature must MODIFY two or more other features, it is usually mis-sliced.
```

Resolution:

- move the modified concern into the owning feature
- merge features
- create a shared foundation feature
- re-cut around the actual boundary

---

### 7.3 Reviewer-Trigger Pressure

Re-verify reviewer-trigger pressure for the final feature set using the trigger list and rules defined in **Stage 3.3**. Confirm that the Complexity bump (`reviewer_trigger_count >= 2`) and the mandatory split (`reviewer_trigger_count >= 4` with intrinsic Complexity `Complex`) still hold after any re-cutting, and that the Cascade Cap (Stage 3.4) has been applied.

---

### 7.4 Risk-Profile Inflation Guard

Re-verify the Risk-Profile inflation guard (rule in **Stage 3.6** — by default at most one feature per plan carries `Risk-Profile: high`) against the final feature set. If more than one feature is genuinely high-risk after any re-cutting:

- justify each high-risk feature in one sentence
- explain why re-slicing did not reduce or concentrate the risk
- record justifications under Notes

Re-slicing is the preferred fix.

---

### 7.5 Boundary-Owner Uniqueness Guard

Re-verify Boundary-Owner uniqueness against the final feature set — each Boundary-Owner category (the cross-cutting + interface-foundation owners defined in **Stage 3.7**) may appear in at most one feature. If two features claim the same category, the plan is invalid.

Resolution:

- identify the real chokepoint
- move ownership to one feature
- remove incorrect owner tags
- re-cut if ownership is genuinely split

---

### 7.6 Unknowns Guard

Re-verify the Open-Unknowns cap (rule in **Stage 3.8** — maximum 5 per feature, each phrased as a question) against the final feature set:

- vague concerns must be rewritten as questions
- more than 5 unknowns requires clarification or re-cutting

---

### 7.7 Bridge Integrity Guard

Rules:

- every bridge must have a `replaced_by` feature
- `replaced_by` must reference an actual later feature
- bridges must not introduce new hard dependencies
- bridges must remain below the bridge cost ceiling
- bridges must be visible in the final artifact

---

### 7.8 Interface Foundation Gate

A surface with no established conventions ships divergence: UI with no shared
visual language ships inconsistent, unstyled screens; an API with no shared
contract ships drifting error shapes, status codes, and pagination. The cause is
the same as an unowned `persistence` concern — a project-wide interface chokepoint
with no owner. Each **primary interface surface** a plan exposes needs an
**Interface Foundation**: a binding convention contract, established before
feature work and consumed by every feature that touches the surface.

**Keying.** Run the gate **per primary interface modality** in the plan's Stage 6
Reachability / Consumability Trace. The foundation family — **one live surface
today; extend on demand, never pre-add an unused category:**

| Modality | Interface Foundation | Boundary-Owner | Status |
|---|---|---|---|
| `browser` | Design system — design tokens (color roles, type scale, spacing, radii) + core UI primitives | `design-system` | live |

*Other surfaces extend the family the same way when a plan exposes them — `http`
(`api-contract`: error envelope, status map, pagination), `cli`, `sdk`, `event`,
`iac`. Add the matching Boundary-Owner category only when a plan needs that
surface. `db` is already covered by `persistence`.*

**For each primary interface modality present, exactly one must hold — else the gate fails for that modality:**

| # | Condition | What to record |
|---|---|---|
| 1 | **Owned.** One feature claims the matching interface-foundation Boundary-Owner — a `type: foundation` feature that establishes the contract, ordered before the features exposing that surface (a hard dependency), and unlocks them. | the owning feature + its hard-dependency edges |
| 2 | **Detected.** The codebase profile (Stage 1.2) found an established foundation for that surface — e.g. a design system / theme / component library (`browser`). | which foundation, so specs cite it as a binding constraint |
| 3 | **Provided.** Conventions / tokens / mockups / a contract spec supplied as project reference docs (Stage 1.5). | the doc paths |
| 4 | **Consented exception.** The human explicitly accepts shipping that surface without a foundation (e.g. a throwaway internal tool). | the decision + reason under Notes — never a silent default |

**On failure** (a plan exposing a foundationed surface with none of the above):
loop back to feature decomposition (Stage 2) and add the foundation feature, **or**
record a consented exception. Prefer adding the foundation — re-cutting one
foundation feature is far cheaper than retrofitting conventions across every
surface already shipped.

The **consented exception** is a material attestation — present it evidence-first
(HITL Gate Standard R2/R3), in its own prompt, never as a silent default:
state the **cost if wrong** — every screen / response on this surface ships visually
or structurally inconsistent, and the conventions must later be retrofitted across
every surface already shipped — and require an explicit reason recorded under Notes.

**Multi-surface plans** need one foundation per primary modality (once more than
one surface is live in the family). Whether they are separate `type: foundation`
features or one combined foundations feature is a **Sizing** call (Stage 4):
combine when small, separate when each is substantial.

**Proportionality.** The contract scales to the surface — a one-endpoint service
needs a one-line error/status convention, not a ceremony doc. A one-line brief is
enormously better than nothing.

When you add a foundation feature, seed it with a **conventions** Open-Unknown
(e.g. *"What visual direction — reference product, brand colors, light/dark,
density?"*) so `spec` (or `ce-auto-build`'s Stage 0 sweep) resolves a chosen
direction instead of guessing.

This is a **detect-or-establish** gate, not a styling step: it guarantees a
*binding interface contract* exists. The owning feature's `spec` designs the
contract, promotes it to an **ADR** (the same propagation path as auth-token
format or persistence) so every later feature reads it fresh, **and delivers the
conformance checker** — the lint rule / contrast test / contract test, wired into
the project's lint or test command, that downstream features actually run.
Establishing the *checker*, not just the contract, is what makes conformance
enforceable rather than aspirational: the **conformance criteria** in `spec`
(Stage 2) are checkable only because the foundation shipped something that checks
them, and the **conformance check** in `implement` (Stage 2) runs it. The gate
establishes the contract *and its enforcement*; without the checker the contract
is decorative.

---

### 7.9 Checkpoint — Session-Fit Check passed

When every Session-Fit check (7.1–7.8) passes, append a `## Session-Fit Check — passed`
checkpoint to `docs/plans/.drafts/<slug>/scratch.md` before loading the write stage — per
SKILL.md → *Gate Checkpoint & Resume*. Record `decided_by: human` when the Interface
Foundation Gate (7.8) required a consented exception or a foundation choice, else
`decided_by: workflow (autonomous pass)`; the `state:` block holds the final feature set
and ship order. A crash after Session-Fit re-enters at Stage 8's Final Plan Review with the
validated shape intact.

---
