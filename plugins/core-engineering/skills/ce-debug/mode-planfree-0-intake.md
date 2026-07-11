# ce-debug (plan-free mode) — Stage 0–0.5: Intake, Classify, Load

Stage file for the `ce-debug` skill's **plan-free mode** (orchestrator: `SKILL.md`). The Stage-0 mode probe routed here because no plan/spec owns the misbehaving target. Covers intake, symptom classification, module loading, and the fallback module synthesis. Load this file when the probe announces plan-free mode.

**Next:** when Stage 0 (and, on a fallback run, Stage 0.5) is complete, load `${CLAUDE_SKILL_DIR}/mode-planfree-1-3-investigate.md`.

---

## Stage 0 — Intake, Classify, Load

1. Resolve the **component** and the **symptom** (argument / conversation / ask).
2. **Classify the symptom class** per the architecture table and **load the
   matching `${CLAUDE_SKILL_DIR}/symptoms/<class>.md`** — or declare the generic fallback, stating it
   now and in the report, and proceed via **Stage 0.5 module synthesis**. (A
   matching module that fails to load is the *error-labeled* fallback per
   contract item 7 — distinguished in the report, and never synthesized over.)
3. Run **one grouped intake round** (never a drip of questions): environment;
   onset — since when, and what changed near then (deploy, config, dependency,
   producer, volume); total vs partial stall; whether a restart fixes it; what
   runtime evidence exists and can be fetched (logs and their level, metrics,
   broker/console state, dumps) — **plus the loaded module's class-specific
   intake questions.**
4. **Plan-awareness (already resolved):** the Stage-0 mode probe already
   established that no `specs/<id>/ce-spec.md` owns this target — that is why you
   are in plan-free mode. If mid-investigation you discover a spec that *does* own
   it, switch to planned mode — load `${CLAUDE_SKILL_DIR}/mode-planned.md` and
   diagnose against the contract. Otherwise proceed; do not seek plan artifacts
   beyond this.
5. **Execution gate [material]:** default is *no execution of the target*.
   Running existing tests or a local repro harness requires explicit consent.
   Prefer network-isolated execution (a sandbox / no-network run) where
   available; otherwise the consent ask must say plainly that the
   no-external-reach check is a **static, best-effort read** and name which
   config/environment the run would resolve. If isolation is unavailable and the
   static read cannot rule out external reach or outside-repo mutation, refuse
   and move it to the discrimination plan.
6. **Scope checkpoint [material]:** component · class · evidence inventory ·
   execution consent — *Proceed / Reclassify / Abort.*

## Stage 0.5 — Module Synthesis  *(fallback runs only)*

Runs only when Stage 0 found **no matching symptom module** for the classified
symptom. Draft an **ephemeral module skeleton** in the exact module shape —
applies-when signals, class-specific intake additions, a mechanism-map checklist,
and candidate failure families *each with static signatures and a runtime
discriminator* — from the symptom, the intake answers, and general failure
knowledge. *(The deliberate echo of `/ce-brief`'s Stage 0.5: a meta-step that
selects/shapes content, never one that decides or relaxes the contract.)*

The rules that keep it honest:

- **Content, never contract.** The skeleton supplies module-shaped *content*
  only; every spine discipline — the Static Ceiling, redaction, grading,
  routing, the locks — is unchanged and non-negotiable.
- **Unverified, and labeled.** The report header carries
  `generic fallback: synthesized module (unverified)`; synthesized bank entries
  are hypotheses *about failure modes* that have survived no review, and the
  run's Honest Limitations say so.
- **Propose, don't promote.** Save the skeleton to
  `docs/investigations/proposed-modules/<date>-<class>.md` and name it in
  the Closing. Promotion into the skill's `symptoms/` library is the human's
  call — a reviewed plugin contribution, never this run's side effect.
