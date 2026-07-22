# Feature-Plan Workflow — Stage R: Plan Revision

Stage file for the `plan` skill (orchestrator: `SKILL.md` — read it first for the
Execution Contract and Core Concepts). Load this file **only** when Stage 0 routed here:
a written plan already exists at `docs/plans/<slug>/` and the request is a change to it,
not a fresh project (see `stage-0-1-understand.md` → *Existing-Plan Check (Stage R)*).

Stage R **revises an existing frozen plan in place** — it does not re-decompose from
scratch. It diffs the requested change against the plan already on disk, re-runs **only**
the gates that change actually touches, preserves everything it does not, and writes the
result back as the next revision. It is the **receiving end** of every downstream
"escalate to `/core-engineering:ce-plan` and stop" path: `/core-engineering:ce-spec`'s structural Boundary Conflicts
(§3.3 / §3.5 / §3.6) and `/core-engineering:ce-implement`'s Boundary Conflict both land here.

**Next:** Stage R ends by writing through the **existing** Stage 8.3 approval + Stage 9
write path in `${CLAUDE_SKILL_DIR}/stage-8-9-write.md` — it does not invent a second write
mechanism. Load that file when you reach R.6.

---

## What Stage R must and must not do

- **Must** preserve the specs and feature files of every **untouched** feature
  byte-for-byte. A revision that re-writes an unchanged feature (or its `specs/<id>/`)
  is a bug — it silently invalidates specced/built downstream work.
- **Must** re-run every gate a delta genuinely touches, at full rigor — a revision is not
  a licence to skip a correctness check the change reopened.
- **Must not** re-ask a gate the delta did **not** touch. Those are **held from the prior
  revision** and listed as such (evidence-first, R2) — never silently, never re-prompted.
- **Must not** re-spec a feature. Stage R stamps a touched feature so the *next* `/core-engineering:ce-spec`
  knows its spec is stale; it never edits `specs/<id>/` itself (escalate up, never expand).
- **Must not** rename an existing stable feature id. New features earn new stable ids
  appended after the highest existing one; re-cut features keep their id (SKILL.md →
  *Feature ID*: a stable id is renamed only through an explicit revision, and even then
  only when the re-cut genuinely splits or merges the feature — prefer keeping the id).

---

## R.0 — Load the frozen plan

Read, from `docs/plans/<slug>/`, the whole frozen shape — do not reconstruct it from
memory:

- `plan.json` (the manifest — ship order, deps, feature files, current
  `plan_revision`, and `architecture_disposition`; **absent revision ⇒ 1**,
  absent disposition or direction binding ⇒ legacy-unassessed and therefore a
  revision delta);
- `architecture-selection.json` when named by the disposition; verify its exact
  file hash and selected-option hash before treating the direction as held;
- `architecture-options.md` when a schema-v2 selection binds it; run the
  selection linter so its sibling path, exact hash, visible option content, and
  immutable `awaiting-selection` marker are verified before preserving it;
- every `features/<id>.md`;
- `feature-plan.md` (Journey Map / Consumability Trace, Dependency Flow, Notes);
- `shared-context.md` (Codebase Profile, Architecture Disposition, Resolved
  Project Decisions);
- `threat-model.md` and `interaction-contract.md` (the read-only re-projections whose
  `TZ-NNN` / `IC-NNN` rows the attestations own);
- `docs/plans/plans.json` (the registry — the plan's entry and its `relates_to`).

Also refresh the **Codebase Profile delta** cheaply: the plan may have shipped features
since it was written, so re-scan (Stage 1.2, single batched sweep) only what the requested
change plausibly touches — do not replay the full nine-dimension profile unless the change
is broad. Record what you re-scanned.

Before deciding whether an architecture package exists, inventory direct children of the
plan directory whose names start with `.architecture-publish-`, without following
symlinks. Any lock, stage, backup, or rejected path means architecture publication may be
live or may have crashed while the canonical directory was temporarily absent. Park the
plan revision, list every exact path, and route to
`/core-engineering:ce-architecture <slug>` for an explicit human recovery decision. Never
delete or consume those transaction paths, and never treat their presence as architecture
absence.

---

## R.1 — State the delta as a diff against the frozen shape

Express the requested change as a **diff against the plan on disk**, not as a new plan.
Classify every element of the delta into exactly these buckets, and name the specific
features/rows in each:

| Delta bucket | What it means | Example |
|---|---|---|
| **feature added** | a new feature the frozen plan did not contain | "add `07-audit-log`" |
| **feature re-cut** | an existing feature's Scope / Excluded / boundary changed | "`03-checkout` now also owns refunds" |
| **feature re-ordered** | ship order changed; no scope change | "`05` ships before `04`" |
| **feature removed** | an existing feature dropped from the plan | "drop `06-legacy-import`" |
| **boundary row touched** | a `threat-model.md` (`TZ-NNN`) or `interaction-contract.md` (`IC-NNN`) row added / changed / removed, or a §6.3 durable-noun closure row moved (a new persisted noun, a data-class change, a new cross-feature edge) | "checkout now writes `refund` (sensitive)" |
| **architecture posture touched** | applicability triggers, evaluation-frame capabilities/constraints/quality priorities, selected direction or hashes, disposition, convergence evidence, waiver, accepted ADR refs, or another decomposition-shaping architecture driver changed; this includes adding the first disposition/direction binding to a legacy plan | "shared order writes now require a migration owner" |

A change that fits **no** bucket (a pure typo in a description, a Notes clarification) is not
a revision that reopens a gate — apply it, bump `plan_revision`, and skip straight to R.6.

Untouched features and untouched boundary rows are the **preserved set** — carry them
forward verbatim.

---

## R.2 — Compute the affected-gate set

The delta buckets determine, mechanically, which gates reopen. Apply this table; a gate not
triggered by any bucket is **held from revision N-1**:

| Gate | Re-runs when the delta includes… | Scope of the re-run |
|---|---|---|
| **Reachability / Consumability (§6, gate §6.6)** | a feature **added / re-cut / removed** that owns or changes a journey step, **or** a **re-order** | only the journeys whose step-owners changed — re-render §6.6 for those rows; untouched journeys carry their prior dispositions |
| **Session-Fit (§7)** | any feature **added / re-cut / removed** | re-check 7.1 graph soundness, 7.2 MODIFY-reach, 7.5 Boundary-Owner uniqueness, 7.6 unknowns, 7.7 bridge integrity, 7.8 Interface Foundation — over the changed feature set (correctness; mostly autonomous, interactive only on a 7.8 consented exception) |
| **8.2.1 Threat-model attestation** `[material]` | a **boundary row touched** that adds/changes a `TZ-NNN`, a trust boundary, or a §6.3 durable noun's data-class | attest **only** the changed `TZ-NNN` rows; unchanged threat rows are held |
| **8.2.2 Interaction-contract attestation** `[material]` | a **boundary row touched** that adds/changes an `IC-NNN` (a cross-feature edge or a >1-touched durable noun moved) | attest **only** the changed `IC-NNN` rows; unchanged contract rows are held |
| **Architecture direction selection (Stage 1A)** `[material, conditional]` | capabilities, hard constraints, QA scenarios/priorities, accepted architecture decisions, evidence basis, or selected option changed; also a missing legacy direction binding | rerun the capability-level Evaluation Frame and `/core-engineering:ce-architecture explore:<slug>` before revising detailed decomposition; require a fresh human-selected option binding |
| **Architecture applicability + convergence (Stage 3.9 / 5A)** `[material, conditional]` | any feature add/remove/re-cut/re-order, boundary-row change, architecture-posture change, accepted architecture decision, or missing legacy disposition/direction | re-screen the whole affected system boundary after direction selection; invoke `/core-engineering:ce-architecture shape:<slug>` when required, and accept only a result bound to the revised candidate and selected option |

**Gate locators (R5) are recomputed for this reduced set.** Two gates always fire in a
revision — **R.3 Revision Delta Confirmation** and **R.6 Final Revision Approval** — plus
each Architecture-Plan Convergence pass that actually needs a human call and
whichever of Reachability / 8.2.1 / 8.2.2 the delta triggers (Session-Fit adds a locator
only if 7.8 needs a consented-exception prompt). Compute **M from the gates that will
actually fire this revision** and print `Gate N of M — <name>` at each; if a re-run gate
surfaces a new interactive decision mid-run (e.g. a Reachability re-cut reopens Session-Fit
7.8), say so — never a silent cap. A minimal revision is `Gate 1 of 2` → `Gate 2 of 2`.

---

## R.3 — Revision Delta Confirmation  `[material]`

The delta and its computed affected-gate set determine what gets **re-litigated** versus
**preserved** — a wrong delta silently re-decides settled work or, worse, ships a change
whose gate never re-ran. So it is confirmed as its own evidence-first prompt (HITL Gate
Standard R1/R2/R3), never a bullet the human consents to by not objecting.

Print the locator, then render — as Markdown in the conversation (Two-Surface Rendering
Rule, §5.3), not inside the dialog:

```text
Gate 1 of M — Revision Delta   (M per the recomputed locator set, R.2)
```

1. **The delta** — the R.1 diff table, every added / re-cut / re-ordered / removed feature
   and every touched boundary row named.
2. **Gates that will re-run, and why** — each with its **basis** (which delta bucket
   triggered it) and its **cost-if-wrong** (what ships unchecked if the human waves it
   through): *"Reachability re-runs for the `checkout` journey because `03` was re-cut to
   own refunds — if skipped, the refund path could dead-end with no return surface."*
3. **Held from revision N-1 (count + list)** — the gates **not** re-running and the
   preserved feature set, so the human sees exactly what is carried forward untouched.
   *"Held: Session-Fit (no feature re-cut), 8.2.2 interaction-contract (no cross-feature
   edge moved); preserved specs: `01`, `02`, `04`, `05`."*

Render the **Material-Gate Decision Authority** block from `SKILL.md`; the
decision owner is the project/plan owner authorized to redefine the delta and
the set of prior decisions that remain held.

Architecture convergence may be held only when no feature, dependency, order,
journey, boundary, trigger, NFR, or accepted decision changed and the prior
disposition is present. A legacy-unassessed plan can never hold it.

Then attest with `AskUserQuestion`, each option labelled by its consequence (R1):

| Option | What happens next |
|---|---|
| **Confirm delta** | Accept the delta and the affected-gate set; proceed to re-run the triggered gates (R.4). The held gates stay held. |
| **Amend the delta** | The delta is mis-stated (a feature is touched that shouldn't be, or a change was missed) — restate it and recompute the affected-gate set. Loops without advancing. |
| **Need evidence / route to owner / park** | Name the missing evidence or accountable owner and stop with the revision scratch resumable; no delta is confirmed. |
| **Abort** | Exit now, **writing nothing** — the frozen plan is untouched and this run ends; the scratch, if any, stays so the revision remains resumable. |

**Checkpoint — Revision Delta passed.** On `Confirm delta`, append a `## Revision Delta —
passed` checkpoint to `docs/plans/.drafts/<slug>/scratch.md` (creating `.drafts/<slug>/` on
this first write) per SKILL.md → *Gate Checkpoint & Resume* — `decided_by: human`,
`decision: Confirm delta`, and a `state:` block holding the R.1 delta table + the computed
affected-gate set + the preserved/held lists. This is the first resumable point of the
revision. `Amend the delta` loops without advancing; `Need evidence / route to
owner / park` stops with the pending state resumable. Neither appends a passed
checkpoint.

---

## R.4 — Re-run only the affected gates

Run **only** the gates R.2 marked as triggered, at the same rigor and in this
fresh-plan order. Reuse the existing gate procedures, never a revision-only
variant:

1. **Pre-decomposition architecture direction** → when R.2 reopened direction
   selection, load `${CLAUDE_SKILL_DIR}/stage-1a-architecture-direction.md` in
   revision mode. Rebuild only affected capability, hard-constraint,
   quality-scenario, priority, and evidence rows; hold the rest. Confirm the
   Evaluation Frame and apply the same Stage 1A route as a fresh plan: a
   required route invokes `/core-engineering:ce-architecture explore:<slug>` and
   requires `direction-selected`; a recommended route may be human-deferred;
   and an all-negative route may be human-confirmed `not-applicable`. Only then
   may a detailed feature re-cut begin. A failed or unknown hard constraint
   parks; a weighted score can never compensate for it. For a legacy plan with
   a current human-approved baseline but no direction binding, offer a separate
   migration gate: adopt one complete, source-backed existing direction as
   `adopted-existing`, explore afresh, or park. Adoption still constructs and
   hash-binds the complete option; it never treats package presence as consent.
2. **Pre-Reachability architecture applicability / convergence** → when R.2
   reopened architecture, run Stage 3.9 and
   `${CLAUDE_SKILL_DIR}/stage-5a-architecture-convergence.md` before any
   Reachability or Session-Fit work. Treat the frozen plan as candidate revision
   1 for this revision run, increment on each accepted structural delta, and
   record the provisional disposition. For the Stage 5A handoff only, map every
   existing stable `NN-slug` to a unique `PNN-slug` alias and put the stable id in
   `Stable source (revision only)`; new features use the next free provisional
   id with `None (new)`. This is not a rename. Translate every returned delta
   through the alias map before showing it, and never let architecture alter a
   stable id or substitute a different selected architecture option.
   Architecture proposes; Stage R and the human alone modify the plan. Stage
   5A's Stage R caller mapping returns here, never to a fresh-plan stage.
3. **Reachability** → re-render `stage-4-7-gates.md` §6.6 (the Reachability Decision, its
  full legend and consequence-glossary) for **only** the journeys whose step-owners
  changed. Untouched journeys are shown as *held from revision N-1* with their prior
  dispositions; do not re-ask them. The §6.6 checkpoint appends as usual.
4. **Post-Reachability architecture re-screen** → whenever Reachability ran,
   rerun Stage 3.9 against its accepted journey, durable-state, continuity,
   trust/data, media, and NFR evidence. If that changed the candidate revision,
   triggers, decisions, or evidence boundary, invoke Stage 5A again and do not
   enter Session-Fit until the result is current or human-waived.
5. **Session-Fit** → run `stage-4-7-gates.md` §7 (7.1–7.8) over the changed feature set.
  This is correctness, not ceremony — a re-cut that breaks graph soundness or
  Boundary-Owner uniqueness **fails and loops back** exactly as in a fresh run. It is
  interactive only when 7.8 needs a consented exception (which then gets its own locator).
6. **8.2.1 / 8.2.2 attestations** → run `stage-8-9-write.md` §8.2.1 / §8.2.2 for **only** the
  changed `TZ-NNN` / `IC-NNN` rows. Each changed row is attested evidence-first with its
  basis + cost-if-wrong from the shared glossary, exactly as in a fresh run; unchanged rows
  are held. Their checkpoints append as usual.
7. **Post-attestation architecture convergence recheck** → run
   `stage-8-9-write.md` §8.2.4 after the changed TZ/IC attestations and before
   R.6. Any changed threat, interaction, NFR, decision, trigger, or evidence row
   invalidates the prior result. If it changes the selected direction's frame or
   viability, return to Stage 1A and reselect before Stage 5A; otherwise return
   directly to Stage 5A. A current result may pass autonomously; a new material
   outcome gets its own recomputed locator.

Because Stage R reuses those procedures verbatim, the shared consequence-glossary lives in
exactly one place (§6.6's runtime Legend); Stage R never re-defines a gloss.

A gate that **fails** during re-run routes through its own back-edge (a Reachability re-cut,
a Session-Fit re-slice) — which may itself enlarge the delta and reopen a held gate. When it
does, recompute the affected-gate set (R.2), say so at the next locator, and re-confirm only
the newly-reopened part — never silently.

---

## R.5 — Preserve the untouched, stamp the touched

Before writing:

- **Preserve** every untouched feature's `features/<id>.md` **and** its `specs/<id>/`
  directory byte-for-byte. Do not open, re-render, or re-time-stamp them.
- **Stamp** every touched feature's `features/<id>.md` Structured-Metadata block with
  `revised_by: plan-revision <N>` (the new revision number from R.6). A touched feature
  whose `specs/<id>/` already exists has a **stale spec**: the stamp is the signal that its
  `/core-engineering:ce-spec` must be re-run. State this in the Closing (R.6) — Stage R never edits the spec
  itself.
- **New features** get a fresh `features/<id>.md` and a new stable id appended after the
  highest existing ship_order; they have no spec yet.
- **Removed features** — drop their `features/<id>.md` and manifest entry. If a
  `specs/<id>/` exists for a removed feature, **do not delete it silently**: name it in the
  R.6 render as an orphaned spec the human disposes of (keep for history / delete manually).
- **Preserve or replace independent locks independently.** Preserve
  `architecture-selection.json` byte-for-byte whenever the capability/evaluation
  frame, evidence fingerprints, and direction choice are legitimately held,
  even when shaping convergence must rerun. Preserve its matching
  `architecture-options.md` human-readable view byte-for-byte too. Replace the
  pair only after Stage 1A
  returns a newly reviewed selected/deferred/N/A binding; a fresh explored
  binding replaces both files, while N/A/deferred may remove the no-longer-
  applicable options report only at the approved write. Preserve convergence
  only when its candidate/evidence binding is held. Then update the direction
  file hash and `architecture_disposition` in `plan.json` plus only the matching
  shared-context sections. A convergence waiver never erases the direction that
  shaped decomposition.

---

## R.6 — Write the revision

Write through the **existing Stage 8.3 approval + Stage 9 write path**
(`${CLAUDE_SKILL_DIR}/stage-8-9-write.md`) — Stage R does not fork a second write mechanism.
Two deltas from a fresh write:

**Final Revision Approval  `[material]`** — this is the Stage 8.3 Final Decision, relabelled
for a revision. Print the locator (`Gate M of M — Final Revision Approval`) and render, as
Markdown: the revised feature table (new / re-cut / re-ordered / removed marked), the
re-run gate outcomes, the **held-from-N-1** list, the touched-spec staleness list, and the
target `plan_revision: <N>`. When an lstat-style namespace check finds any entry
named `architecture` — including a broken symlink, symlinked directory,
non-directory, or partial package — also state that the plan revision will make
its revision/hash boundary stale or malformed and that
`/core-engineering:ce-architecture <slug>` must run before any touched/new spec;
the planning workflow does not silently refresh or remove that sibling-owned
package. Label each option by consequence (R1/R5):

Render the **Material-Gate Decision Authority** block from `SKILL.md`; the
decision owner is the project/plan owner authorized to commit the exact touched
file set, staleness consequences, and revision counter.

If this revision changes an explored direction to `not-applicable` or
`deferred`, the render must name deletion of the now-inapplicable
`architecture-options.md` as a reviewed file-level consequence. It is removed
only with **Write revision**, never during analysis or an aborted gate.

Even when no architecture namespace exists, a revised `decision: required`
means the current plan must publish its baseline before any touched/new spec.
Render that consequence at this gate.

| Option | What happens next |
|---|---|
| **Write revision** | Write the touched files + bumped `plan.json`, preserving the untouched set. **The commit point.** |
| **Adjust** | Loop back to R.1 / R.4 — nothing is written yet. |
| **Need evidence / route to owner / park** | Name the missing evidence or accountable owner and stop with the frozen plan plus revision scratch intact; no write is authorized. |
| **Abort** | Exit without writing — the frozen plan and its specs are untouched, and the revision scratch remains resumable until an explicit fresh start. |

On **Write revision**, apply the Stage 9 write, scoped to the revision:

1. **Bump `plan_revision`** in `plan.json` — `frozen value + 1` (absent ⇒ was 1 ⇒ write
   `2`). This is the one manifest field a revision always changes.
2. **Write only the touched files**: the changed / added / removed `features/<id>.md`, the
   updated `feature-plan.md` index (feature table, Dependency Flow, Journey Map for changed
   journeys), and — **only if a boundary row moved** — re-project `threat-model.md` /
   `interaction-contract.md` from the changed rows (still a read-only re-projection, never a
   fresh set of decisions; unchanged rows copied verbatim). Untouched re-projections are not
   rewritten. When architecture posture changed, also write the exact reviewed
   `architecture-selection.json`, its matching `architecture-options.md` when
   exploration ran, the new `architecture_disposition` and file hash in
   `plan.json`, and only the Architecture Disposition / Resolved Project
   Decisions sections in `shared-context.md`. Never reconstruct options or
   scores from a prose summary. When the approved new binding is N/A/deferred,
   remove the prior `architecture-options.md` named at Final Revision Approval;
   report whether the removed bytes are recoverable from version control and do
   not claim recovery when they are not. Never leave the old report silently
   represented as current evidence.
3. **Append the revision rationale to Notes (§13)** in `feature-plan.md`: `plan-revision <N>`
   — what changed, why, which gates re-ran, and which were held from `N-1`. The Notes
   history is the on-disk audit trail of how the plan evolved.
4. **Update `plans.json`** only if the plan's `description` or `relates_to` changed;
   otherwise leave the registry entry as-is.
5. **Delete the revision scratch** `docs/plans/.drafts/<slug>/` on the successful write
   (Stage 9's existing lifecycle rule) — the revision is now the frozen plan.
6. **Metrics (best-effort)** — append a `stage-complete` line (`stage: "plan"`,
   `feature: null`, note `plan_revision: <N>`) to `docs/plans/<slug>/.metrics.jsonl`; never
   let it block the write.

**Closing.** Confirm what changed (files written or removed, features touched,
`plan_revision: <N>`, and recovery status for a removed options report),
then name the next actions. If the revised disposition is `required` **or** that
lstat-style check found any `architecture` namespace occupant, print
`/core-engineering:ce-architecture <slug>` first and do not print a direct spec
command as the immediate next action; when the revised plan has only one
feature, that architecture run owns the explicit obsolete-package disposition.
For `recommended` with no existing package, offer architecture first and label
its absence a coverage gap, then print the spec reruns. Otherwise, for each
touched feature whose spec is now stale
(`revised_by: plan-revision <N>` with an existing `specs/<id>/`), print its
`/core-engineering:ce-spec <slug> <id>` re-run line; for each new feature, print its `/core-engineering:ce-spec` line. Do not
start downstream specification automatically.

---

## Resume — an aborted revision resumes too

Stage R reuses the T6 gate-checkpoint scratch (`docs/plans/.drafts/<slug>/scratch.md`), so a
crash or compaction mid-revision resumes from the last passed gate — not from a re-loaded
frozen plan and a re-stated delta. Because the written plan **and** a scratch coexist only
during an in-flight revision, Stage 0's *Existing-Plan Check* treats that pair as an
interrupted revision and re-enters Stage R at the last checkpointed gate (re-render its
`state`, continue at the next gate — do not re-run the R.0 load or re-ask the confirmed
delta).

There is one narrow crash window to recover before advancing. When R.2 reopened
Architecture Direction Selection, the draft may contain a newly persisted
`architecture-selection.json` and its bound `architecture-options.md`, but the scratch may
not yet contain `## Architecture Direction Selection — passed`. In that state:

1. Treat only the current draft attempt under `docs/plans/.drafts/<slug>/` as
   recovery evidence; the frozen plan's existing architecture files remain untouched and
   cannot stand in for the draft. Require its regular, non-symlink
   `architecture-exploration.json`, re-read it, and perform the complete Stage 1A freshness
   comparison: project slug, capability revision, exploration attempt, canonical
   decision-input hash, and every source hash must equal the selection. A valid pair from
   another attempt is stale and cannot reconstruct a checkpoint.
2. Run the current deterministic validator from the repository root over the sibling
   selection/report pair:

   ```bash
   python3 "${CLAUDE_SKILL_DIR}/scripts/architecture-selection-lint.py" \
     docs/plans/.drafts/<slug>/architecture-selection.json --repo-root . \
     --require-current-schema --json
   ```

3. On exit 0, additionally require `selection.status: direction-selected`,
   `selection.decided_by: human`, and `architecture_options_report.status: present`, then
   append the missing checkpoint **without invoking exploration, re-asking the human, or
   rewriting either artifact**. Reconstruct it exactly from the validated JSON: use the
   selected option id and that option's title for `decision`; copy
   `exploration_id`, `source_capability_revision`, `source_exploration_attempt`,
   `source_input_sha256`, and `option_set_sha256`; copy `selection.option_id`,
   `selection.option_sha256`, and `selection.rationale`; and copy
   `architecture_options_report.path` and `architecture_options_report.sha256`. Append this
   Stage 1A checkpoint shape (the report path is resolved relative to the validated JSON's
   parent, never accepted from an unvalidated path):

   ```text
   ## Architecture Direction Selection — passed
   decided_by: human
   decision: <selection.option_id + matching option title>
   state: |
     exploration_id: <exploration_id>
     source_capability_revision: <source_capability_revision>
     source_exploration_attempt: <source_exploration_attempt>
     source_input_sha256: <source_input_sha256>
     option_set_sha256: <option_set_sha256>
     selected_option_id: <selection.option_id>
     selected_option_sha256: <selection.option_sha256>
     architecture_options_report: docs/plans/.drafts/<slug>/<architecture_options_report.path>
     architecture_options_report_sha256: <architecture_options_report.sha256>
     rationale: <selection.rationale verbatim>
   ```

   In the recovery render, label the checkpoint `recovered from validated draft artifacts`.
   Then continue at the next **Stage R** gate in the already-confirmed affected-gate set.
   The persisted human selection is authoritative only because this exact v2 pair passed
   current-schema validation.
4. A report by itself — including a valid immutable report marked
   `awaiting-selection` — never proves approval. A missing selection, exit 1/2, schema-v1
   draft, missing/current-input mismatch, mismatched binding, or missing report must not
   produce a checkpoint or alter the frozen plan. Leave the existing written plan and
   legacy v1 artifacts unchanged, report the coverage gap, and resume the reopened Stage
   1A direction-selection work from the last real checkpoint.

On the successful R.6 write the scratch is deleted; an abort or crash leaves it, so the
revision stays resumable.
