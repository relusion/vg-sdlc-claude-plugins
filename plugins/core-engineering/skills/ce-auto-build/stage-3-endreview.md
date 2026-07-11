# Auto Build — Stage 3: End-Review

Stage file for the `ce-auto-build` skill (orchestrator: `SKILL.md`). Load this file when the pipeline returns — normally or via a circuit-breaker.

**Next:** nothing loads after this file — the Closing block ends the run.

---

## Stage 3 — End-Review (interactive, in this skill)

Consume the pipeline's return. **Print the locator `Gate M of M — End-Review`** (HITL R5; M from the Stage-0 count). This is the framework's densest gate, so **lead with the triage block (HITL R4)** — separate *what needs your decision* from acknowledge-only, before the seven buckets:

```text
Gate M of M — End-Review
What needs your decision (N):
  • <P> parked features — each blocks until you resolve it           (bucket 1)
  • <A> low-confidence assumptions — Accept / Override               (bucket 2)
  • <S> additive-vs-breaking attestations — confirm / override       (bucket 6)
  • <I> interaction-contract coverage — any assigned IC-NNN DROPPED   (bucket 6)
  • <H> suspected-high review findings — Escalate / Defer / Dismiss  (bucket 5)
  • <J> manual:judgment verdicts to render now                       (bucket 4)
  • <D> below-policy-tier / unattested model runs — Accept / Re-run   (bucket 7)
Acknowledge-only (counts): <h> high-confidence assumptions · verification index · audit rows · cross-journey UX not walked (when browser journeys exist — bucket 7) · **merge-bar verdict** — this run, as landed, vs your exact CI bar (the *Merge-Bar Verdict* step below; a labeled degradation line, not a verdict, when Checkpoint Mode = `none`)
```

Then present the buckets, loudest-first.

**Correction is dependent-aware (the write-then-audit invariant).** Because spec/implement run *before* this review, any decision the human overturns here may already have propagated to later features in ship order — a ledgered resolution or ADR a downstream spec read fresh, a shared shape a dependent built against. **Every override/revert below therefore re-spawns the affected feature *and* its downstream dependents** — the same *feature + dependents* re-run a parked feature triggers (step 1), never the affected feature in isolation. The orchestrator **broadcasts** the ledger to *all* later features rather than recording which one read a given entry, so it cannot pinpoint exact consumers — it therefore re-spawns a **conservative superset: every later feature in ship order whose run could have consumed the overturned call** (over-approximate, never under). That superset is derivable from ship order alone, so it survives a `--resume` (no consumer map need persist). The correction thus reaches every feature that could have built on the overturned decision, not only the one that surfaced it — the batched review corrects *forward*, not just locally.

1. **Parked features** — each with its blocking decision. The human resolves it; the feature (+ dependents) can then run (re-spawn its pipeline). A feature parked by the diagnose gate carries its `specs/<id>/diagnosis.md` (reproduced cause + evidence) as the blocking record; a feature parked on an architectural / multi-option fork with **enrich-parks** on carries a `/ce-decide` **scored package + proposed-ADR draft** (weights `inferred` — re-derive against your real situation; promote the ADR if you accept it) so resolving it is a read-and-confirm, not a cold reconstruction.
2. **Low-confidence assumptions** — *Accept / Override* (override re-spawns *feature + dependents* per the dependent-aware correction rule above — never the affected feature alone when the assumption was a ledgered/shared one later specs consumed).
3. **High-confidence assumptions** — for acknowledgment.
4. **Verification** — per-feature (each `specs/<id>/verification.md`) + integration, plus **manual:judgment verdicts** to gather now against a server.
5. **Code-review findings** (from each feature's `review-summary.json` + `code-review.md`) — **`confirmed`-high** findings the review gate blocked on (resolved during the run, shown for audit) + **`suspected`-high** findings the verification pass demoted (never blocked — **flagged for triage now**, the precision/recall tradeoff the human owns) + medium / low for triage now: *Escalate* (→ `/ce-implement` or `/ce-spec`) · *Defer* · *Dismiss*. **On `Dismiss` of a false-positive shape, append an `RL-N` suppression rule to `docs/plans/<slug>/review-learnings.md`** (this is auto-build's *only* review-learnings write point — mid-run advisory review never triages) so the next run remembers it; a finding revealing a real recurring hazard seeds `patterns.md` instead (never both). Findings already shown under "Previously dismissed" (suppressed by a prior rule) are surfaced too, so a wrong suppression can be reversed. Diagnoses (when diagnose mode was on) are shown for audit too: bugs re-implemented during the run (resolved; `suspected`-confidence ones flagged) and any diagnosis that drove a park (in *Parked*, above).
6. **Agent-approved spec decisions to review** — the mid-run human gates are absent, so surface, applying the HITL Gate Standard's *isolate material attestations* (R3) and *evidence-first* (R2) rules rather than one undifferentiated dump:
   - **SHARED-shape `additive`-vs-`breaking` classifications (§3.5)** — each rendered as its **own** evidence-first attestation: the shape, the consumers enumerated from real code, the per-consumer call, and *if this was called additive but is breaking: a contract break ships to a shipped consumer with no migration owner.* Show the Challenge gate's verdict on each; the human confirms or overrides. This is the highest-cost spec call with no on-disk gate — it gets its own prompt, never a bullet in a dump. *(Gloss: `breaking` → **Boundary Conflict** — the change crosses into another feature's contract, so `/ce-plan` owns the migration + ship-order, not this spec.)*
   - **`manual` test-case classifications** — catch a hard test mislabeled `manual:judgment` to dodge it.
   - **The criteria / design the subagents self-approved**, and the **Resolved Project Decisions ledger appends** (each marked `provisional` until confirmed here — *confirm wording / revert*). **A revert re-spawns the feature *and its downstream dependents*** (the conservative ship-order superset, per the dependent-aware correction rule above), since later specs read the ledger fresh in ship order. *(Gloss: `provisional` = later features already read this as settled, so reverting it re-spawns those dependents.)*
   - **Interaction-contract coverage (`IC-NNN` → `[CONTRACT]`).** There is **no H5-style lint** for `IC-NNN` (the deliberate divergence from `TZ-NNN`), so this end-review is its only backstop: re-project each feature's assigned `IC-NNN` (from `interaction-contract.md`) against the spec on disk and render each **emitted** (a `[CONTRACT: IC-NNN]` AC + test case), **parked-N/A** (the agent's flagged N/A — its blocking confirmation already rides on the feature's bucket-1 park entry, never double-surfaced here), or **DROPPED** (no AC and no park — a Spawn-Contract violation that escalates to `/ce-spec`). Only a `DROPPED` obligation needs a decision here; emitted / parked are acknowledge-only. This closes for `IC-NNN` the loop H5 closes mechanically for `TZ-NNN`. *(Gloss: `IC-NNN` → a cross-feature behavioural-protocol obligation or architecture-determining NFR — see the shared consequence-glossary.)*
7. **What's not done / reduced confidence** — failed, blocked, and capability-degraded areas. **Below-policy-tier model runs are one of these, surfaced as an evidence-first accepted degradation (HITL R2/R3):** read the metrics stream's per-stage `model` field (the runtime leg of the model-tier policy — `hooks/model-attest.py` records what actually executed; see `/ce-retro`'s Model-tier attestation signal) and map each gate/judgment stage through `model-policy.json` `tier_patterns`. Any stage whose recorded model matches a **below-`strong`** tier gets its **own** attestation (never a buried bullet): the stage + gate, the **recorded model id** (the basis, not an assumption), and *cost-if-wrong: this judgment/gate stage produced its output on a weaker model, so the strong-model quality the policy guarantees is unattested for it.* The human **Accepts** the degradation (recorded, never silent) or **Re-runs** the stage on the strong model — a Re-run re-spawns the feature *and its downstream dependents* (the conservative ship-order superset, per the dependent-aware correction rule above). A stage whose `model` matches **no** tier pattern, or is `null` (a hook-less or Managed-Agent run that loaded no `model-attest.py`), is **`unattested`** — surfaced as a finding here, never assumed fine. **Every accepted or unattested line joins the run report's Degradations section**, which gives CLAUDE.md's standing *surface at the end-review as an accepted degradation — never silent* rule the metrics `model` field as its data source (it had none before). **Cross-journey experiential UX is one of these whenever any built feature owns a `browser`-modality journey:** the in-loop `surface-defect` park (step 5½) and the integration `verify` pass covered *single-surface* readability (evidence captured, verdict deferred to this end-review) and that each journey *behaves*, but no autonomous stage walked the **cross-journey experiential layer** — cross-feature consistency (action-label / pattern / navigation / tone drift), off-path dead-ends, coverage gaps, missing empty/error states. Surface it as an **acknowledge-only** note naming the follow-up — run `/ce-ux-audit <slug>` against the built app (it walks the plan's traced journeys, and auto-detects an adversarial plan-free probe where no plan owns the surface) — **never a decision bucket and never auto-run**: the orchestrator rendered no UX verdict here (the tool is interactive, browser-driven, findings-not-verdicts), so the call stays the human's. Honors *no silent gaps* by naming the un-walked layer rather than letting it pass unmentioned. Omit it on a plan with no `browser` journey.

**Merge-Bar Verdict (run it before writing the report — acknowledge-only).** The two enforcement surfaces meet here: the same `scripts/gate_runner.py` an adopter's CI runs on the PR is forked into this skill (`${CLAUDE_SKILL_DIR}/scripts/gate_runner.py`, registered in `fork-manifest.json` — byte-identical to the canonical, never hand-edited), so the human learns *"this run, as landed, passes/fails your exact CI merge bar"* **before** opening the PR, not after. Run it against the **committed** checkpoint branch — the bar judges committed state only, so this is meaningful **only in `isolated-branch` Checkpoint Mode**:

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/gate_runner.py" \
  --repo . \
  --base <run-baseline-ref> \
  --head auto-build/<slug>/<date> \
  --policy "${CLAUDE_SKILL_DIR}/../../merge-policy.json" \
  --plugin-root "${CLAUDE_SKILL_DIR}/../.." \
  --json
```

`<run-baseline-ref>` is the run's **integrity baseline from Stage 0 step 6** — the commit the checkpoint branch was cut from, or the `auto-build(baseline): pre-existing working-tree state` commit when the run proceeded dirty (so pre-existing edits stay outside the measured diff, the same baseline `test-guard`/`dep-guard` used). The explicit `--policy`/`--plugin-root` flags are **required**: the fork's `DEFAULT_PLUGIN_ROOT` (computed from `__file__`) mis-resolves from the copied location, and passing them keeps the fork byte-identical to the canonical rather than patched per-copy. No `--change-class` is passed, so the policy's fail-safe **`defaults`** bar runs; the verdict's `validity_required` records the `human`/`two-human` attestation the merge still owes (the runner never attests it — branch protection does).

Render it as a single **acknowledge-only** line in the triage block — *"this run, as landed, passes/fails the exact CI bar: N/M required gates"* (from the verdict's `summary`) — and write the **full verdict JSON** into the run report's `## Merge-Bar Verdict` section: the recorded `base_sha`/`head_sha` + policy `sha256` are the pre-handover attestation the evidence pack wants (a run's integrity verdict, reproducible from the SHAs it names). It is **acknowledge-only, never a decision bucket**: the bar reports, the human still owns whether to open the PR. A runner `status: "error"` (exit 2 — a missing ref, an unreadable policy) is surfaced verbatim as an honest *could-not-run* line, **never laundered into a pass**.

In **`none` Checkpoint Mode** there is no committed branch to judge (the run lands as one uncommitted working tree), so the bar **cannot run** — record a labeled degradation line in the report's *Degradations* section (*"merge-bar verdict unavailable: Checkpoint Mode = `none`, the bar judges committed state only"*) and the same in the acknowledge-only triage line. **Never fabricate a verdict** where none was computed.

Write the run report to `docs/plans/<slug>/ce-auto-build/<date>-run.md`, following the
template bundled at `${CLAUDE_SKILL_DIR}/run-report-template.md` — **load it now**, do not
reconstruct it from memory (the same on-demand discipline as the gate modules). **Nothing is
"done" until the human signs off.**

---

## Run Report Template — `docs/plans/<slug>/ce-auto-build/<date>-run.md`

The full template is bundled at `${CLAUDE_SKILL_DIR}/run-report-template.md` and loaded
only at the Stage-3 end-review when the report is written (see *Stage 3*) — it is write-time
detail, not common-path context, so it lives beside the gate modules rather than inline (the
same progressive-disclosure discipline `/ce-spec` and `/ce-verify` apply to their artifact
templates). It carries the report's full section set: the run header (scope · substrate ·
checkpoint mode · feature counts), Foundational Decisions, Capability Preflight, Decisions
Made On Your Behalf, Shared-Shape Reconciliations (§3.5), Challenges, Parked, Verification
index, Code Review, Diagnoses, Integration, **Merge-Bar Verdict** (the committed checkpoint
branch judged against the exact CI bar, or a degradation line in `none` mode), Degradations,
and the End-Review Record.

---

## Closing

```text
Auto-Build: <slug> — <date>  (spawning orchestrator)
Built: <N> · Parked: <P> · Failed: <F>
Decisions made on your behalf: <total> (<assumed> flagged)
Report: docs/plans/<slug>/ce-auto-build/<date>-run.md
```

Name the next action: resolve parked features (decide the blocker → re-spawn); then land the reviewed work — in **Checkpoint Mode**, review the `auto-build/<slug>/<date>` branch and squash / cherry-pick / `reset` it onto your own branch; otherwise commit the reviewed working tree yourself. **Never commit to your branch, push, open PRs, or deploy automatically.**
