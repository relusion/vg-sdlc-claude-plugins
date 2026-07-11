---
name: ce-debug
description: |
  Diagnose a FAILING target and route one fix — auto-detecting whether a plan/spec owns it. Planned mode (a plan/spec owns the failing feature): reproduce → file:line root cause → classify (bug/spec-gap/structural) → route one targeted fix to /ce-implement, /ce-spec, or /ce-plan. Plan-free mode (a misbehaving component with no plan/spec — a stuck consumer, silent worker, or job that stopped): ranked, evidence-bound root-cause hypotheses + a discrimination plan (the cheapest observation that settles each). Read-only on code; never patches.
  Triggers: debug/root-cause/find why a feature, test, or journey fails; or investigate/troubleshoot why a service/worker/queue is stuck or silently failing. Auto-detects planned vs plan-free mode from plan state — you need not know which.
argument-hint: "[feature-id | failing-test | component-or-path] [symptom or error]"
allowed-tools: Read, Write, Glob, Grep, Bash, AskUserQuestion, Skill
---

# Debug

**Invocation input:** Failing feature, test, verdict, error, or misbehaving component: $ARGUMENTS


Diagnose why something is failing and route the fix — without fixing it here.

`/ce-debug` is invoked on a **failure or a symptom**: a red `auto` test, a failed
acceptance criterion or broken journey from `/ce-verify`, a `Fail` / `Blocked`
verdict, a correctness finding from `/ce-review`, a task that has hit
`/ce-implement`'s `~3-attempt` limit, a pasted error / stack trace — **or** a live
component making no progress: a consumer that stopped, a worker that went silent, a
job that never fires. It **reproduces or investigates**, **localizes** the cause,
and **routes** a targeted fix to the layer that owns it. It writes one artifact and
mutates nothing else.

It runs in one of **two auto-detected modes**, chosen by a Stage-0 probe of plan
state — you never have to know which:

- **Planned mode** — a `docs/plans/<slug>/specs/<id>/ce-spec.md` owns the failing
  feature. The spec is the **contract**: reproduce → localize to one `file:line`
  root cause → classify (`bug` / `spec-gap` / `structural`) → route one fix.
- **Plan-free mode** — no plan/spec owns the target (the rest of the world's code).
  Reproduction may be impossible at the desk, so the tool maps the mechanism,
  generates hypotheses from a curated failure bank, grades each against the
  evidence available, and produces a **discrimination plan** — the cheapest
  observations that settle what static reading cannot.

This is the diagnostic on the failure edge of the discipline chain (planned mode)
and the plan-free investigator for everything else:

```
plan ◄── spec ◄── implement ◄── { verify · review }
                       ▲                    │ failure
                       └─────── debug ◄─────┘   (planned mode)

  any repo · a misbehaving component ──► debug ──► ranked hypotheses + plan  (plan-free mode)
```

Like its read-only siblings `/ce-verify` and `/ce-review`, debug **escalates, never
mutates** — in both modes.

## Runtime Inputs

- **Failure or symptom signal (required):** in **planned mode** — a feature id
  (`03-checkout` or `<plan-slug>/03-checkout`), a failing test name, a failed AC /
  journey, a review finding id, or a pasted error / stack trace. In **plan-free
  mode** — a component (path, directory, project, or name) plus what is misbehaving
  (and, if known, since when). If missing, ask; do not guess.
- **Runtime evidence (plan-free, optional but first-class):** logs, stack/thread
  dumps, metrics, broker/console state, config from the live environment — pasted
  or as file paths. Quoted into evidence with source labels; this is what lifts a
  hypothesis past the Static Ceiling (see the plan-free stage files).
- **Loaded read-only inputs** are mode-specific and are enumerated in the mode's
  stage file: planned mode loads the spec / `tasks.json` / recorded failure /
  implemented files / `shared-context.md` / `patterns.md`; plan-free mode loads the
  suspect mechanism and the provided runtime evidence.

Writes only the mode's artifact: **planned** → `diagnosis.md` + an `evidence/`
directory in the plan directory (`docs/plans/<slug>/`), or the per-feature
`specs/<id>/` under auto-build; **plan-free** → a dated
`docs/investigations/<date>-<slug>.md` + its `evidence/` directory (never
overwritten — a same-day re-run suffixes `-2`, `-3`, …).

## Execution Contract

*Gate locator (HITL R5):* print `Gate N of M — <name>` at every interactive gate; compute M from the gates that actually fire this run, never a hardcoded constant.

0. **Session write lease (structural, first act).** `python3 "${CLAUDE_SKILL_DIR}/scripts/write-lease.py" --set --skill ce-debug --allow 'docs/plans/**/diagnosis.md' --allow 'docs/plans/**/evidence/**' --allow 'docs/plans/**/.metrics.jsonl' --allow 'docs/investigations/**'` — one lease covers both modes' write boundaries (planned mode writes under `docs/plans/**`; plan-free writes under `docs/investigations/**`); a run writes only its own mode's paths. Last act: `python3 "${CLAUDE_SKILL_DIR}/scripts/write-lease.py" --restore-baseline`. A denied write mid-session means this contract and the action disagree — reconcile; never edit or delete the lease to proceed.
1. **Diagnose / investigate, do not fix.** Find the cause and route it; never patch
   code, edit specs or config, or apply instrumentation. Writes only the mode's
   artifact + its `evidence/` (and, on a plan-free fallback run, the proposed-module
   skeleton).
2. **Read-only on the working tree; Bash is read-only on the repo.** Repo-local
   read-only commands (`grep`, `git log`/`blame`/`show`) are free — never `sed -i`,
   redirection into tracked files, or `git checkout`/`stash`/`commit`. Any
   working-tree-moving probe (`git bisect` / `checkout`) or running the target /
   its tests / a repro harness is **consent-gated [material]**. Before a
   tree-moving probe, snapshot `HEAD` and the dirty state; wrap the restore so it
   runs on **every** exit path — abort and circuit-break included — and verify the
   tree matches the snapshot before returning. There is **no hook backstop** for
   this (git-guard gates only `commit` / `push` / PR), so the restore is a workflow
   discipline. Anything that could reach an external system or mutate state outside
   the repo is **refused** — propose it as a discrimination-plan item instead.
3. **Evidence-bound.** Every claim cites `file:line`, a test / command output, a
   stack frame, a config key, a commit, or a quoted log/metric line with its
   source. No evidence → no claim. **Reproduce before you confirm** (planned) or
   honor **the Static Ceiling** (plan-free): code reading alone caps a cause at
   `suspected`; only discriminating runtime evidence `confirmed`s it.
4. **Redact before you record (plan-free).** Live evidence is redacted before it is
   quoted or saved — credentials, tokens, connection strings, and personal data are
   masked; cite a config *key* and the shape of its value, never a secret's value.
5. **Diagnosis / hypotheses, not verdict.** Debug explains and routes; the human
   owns the decision to act. It never declares ship / no-ship or beyond-repair, and
   never asserts a single cause unless `confirmed`.
6. **Classify up, never sideways.** Every outcome routes to the layer that owns the
   fix or to the human. Debug holds no authority to mutate code — so escalate-up is
   structural, by construction.
7. **Never commit, push, or deploy.**

## Stage 0 — Mode Probe *(auto-detect, announced, never a question)*

Resolve the mode yourself from repo state — **plan-existence is internal state the
user should not have to know**, so this is an announced auto-detect with an
override escape hatch, **never** a question:

1. **Read `docs/plans/plans.json`** (read-only). If it is absent → **plan-free
   mode**.
2. **If present, resolve whether a spec owns the failing target.** If the input
   names a feature id, check for its `docs/plans/<slug>/specs/<id>/ce-spec.md`. If
   it names a file / test / error, resolve the owner **mechanically**: scan each
   feature's `tasks.json` `files` array (and the spec Design's file list) across the
   plan — a file mapping to exactly one spec'd feature → **planned mode**; a target
   no plan/spec owns → **plan-free mode**; a file owned by several features (a
   cross-cutting layer) is ambiguous → name the candidates and ask which feature.
3. **Announce the detected mode in one line, then proceed** — offer the override,
   do not gate on it:
   - Planned: *"Planned mode — `docs/plans/<slug>/specs/<id>/` owns the failing
     target; diagnosing against its spec. (To force a plan-free investigation
     instead, say so.)"*
   - Plan-free: *"Plan-free mode — no plan/spec owns this target; investigating with
     ranked hypotheses + a discrimination plan. (To point me at a plan feature
     instead, name it.)"*
4. **Load the mode's stage file and continue:**
   - **planned** → `${CLAUDE_SKILL_DIR}/mode-planned.md`
   - **plan-free** → `${CLAUDE_SKILL_DIR}/mode-planfree-0-intake.md`

The announcement is not one of the interactive gates counted in `Gate N of M` — it
is an auto-detect read-back. The mode's own **material** gates (planned mode's Scope
checkpoint + classification; plan-free mode's Stage-0 scope / execution gate +
Stage-5 route) are counted per that mode's stage files.

## Human-in-the-Loop — tiered

- **Stage 0 (announced auto-detect)** — the mode read-back above; override, never a
  question.
- **Planned mode** — a **material** Scope checkpoint (confirm the failure, feature,
  and contract); localization is autonomous but a `git bisect` / tree-moving probe
  is **material** (consent before, restore after; skipped under auto-build); the
  **classification** is a **material** human call (a `bug` vs a `spec-gap` route
  very different work).
- **Plan-free mode** — a **material** Stage-0 scope + execution gate (default: no
  execution of the target); a mid-run stuck-rule single question for a cheap
  evidence request; and a **material** Stage-5 route (the same evidence can justify
  a `/ce-patch`, a `/ce-plan`, or "go fetch discriminator #1 first").

No fix is ever applied by this workflow, in either mode.

## Autonomous Mode

`/ce-auto-build` invokes debug — **in planned mode only** — through its **Diagnose
Gate** (off by default, enabled as a consented Stage-0 choice). Plan-free mode is
interactive-only and is never auto-spawned (its execution/route gates need a human).
When spawned by auto-build, run planned mode without interactive gates: reproduce →
localize → classify → write `specs/<id>/diagnosis.md` → **return the routed
outcome** to the orchestrator:

- **`bug`** → return the diagnosis so the orchestrator can re-spawn implement **with
  `diagnosis.md` as input**. The debug spawn does **not** consume an implement
  retry; the subsequent re-implement consumes exactly one, under the same retry cap
  and circuit-breaker as today.
- **`spec-gap` / `structural`** → **park** (matches auto-build's existing
  park-on-spec-conflict / plan-change).
- **`not-a-code-defect`** (environmental / flaky / external, or an unreproducible or
  `indeterminate` outcome) → **park** with the evidence — never burn a retry on a
  cause no code change fixes.

History bisection is **skipped** when autonomous (it needs the consent gate it
cannot get here); a cause that would have needed it stays `suspected`. Never patch;
never escalate interactively; defer any judgment to the end-review.

## Modes — how to run

This skill is a thin **orchestrator**: the Stage-0 mode probe above chooses the
mode, then the mode's stages live in a companion file you load only when you reach
it. Read each at `${CLAUDE_SKILL_DIR}/<file>` by absolute path.

| Mode | Load this file | Then |
|---|---|---|
| Planned (a spec owns it) | `${CLAUDE_SKILL_DIR}/mode-planned.md` | Load-and-scope → reproduce → localize → classify → write `diagnosis.md` |
| Plan-free (no plan/spec) | `${CLAUDE_SKILL_DIR}/mode-planfree-0-intake.md` | Intake/classify/load a symptom module → map + hypothesize → discrimination plan + report |

**The companion files named above are bundled in this skill's own directory.** `${CLAUDE_SKILL_DIR}` resolves to this skill's directory regardless of the current working directory. Resolve it once if needed (`ls "${CLAUDE_SKILL_DIR}"`) and read each file by its resulting absolute path; **never load a companion file by bare name** — in an installed plugin the working directory is the user's project, so a bare name finds nothing and triggers a filesystem search. (`diagnosis.md`, `evidence/`, `docs/investigations/`, and everything under `docs/plans/` live in the user's project, not this skill — those paths stay as-is.)

---

## Escalation

Debug never fixes; every outcome routes to the layer that owns the fix — the mode's
route table carries the `Means` column and the pitfall / discrimination detail this
summary would only duplicate. **Planned mode** routes `bug → /ce-implement`,
`spec-gap → /ce-spec`, `structural → /ce-plan` (see `mode-planned.md` Stage 3).
**Plan-free mode** routes to `/ce-patch` (small, bounded), `/ce-plan` (structural),
the pipeline's own planned-mode diagnosis where a spec exists, the prover tools
(`/ce-probe-perf`, `/ce-probe-sec`), `/ce-review`'s Security lens, or the human/ops
armed with the discrimination plan (see `mode-planfree-4-5-report.md` Stage 5).

Planned mode completes the escalate-up chain: `plan ◄── spec ◄── implement ◄── { verify · review · debug }`.

---

## Honest Limitations

- **A diagnosis, not a fix.** "Done" means a routed, evidence-bound cause (planned)
  or a ranked set + discrimination plan (plan-free); whether the fix works is the
  routed skill's to prove. A wrong call surfaces as the next failure and re-enters
  debug.
- **Reproduction-bound / Static-Ceiling-bound.** A failure it can't reproduce here
  (planned) gets an honest `unreproduced`; without runtime evidence a plan-free
  hypothesis caps at `suspected` — the discrimination plan is the honest bridge, and
  a run that ends "all suspected, go fetch these three observations" has succeeded.
- **No instrumentation.** It localizes by reading, existing-test variation, and
  history bisection (planned) or the mechanism walk + provided evidence (plan-free);
  it adds no logging or probes (that would mutate code), so a cause needing live
  tracing stays `suspected`.
- **Contract only in planned mode.** Plan-free mode has no spec defining expected
  behavior; "expected" is inferred from the code, its docs, and the human's
  statement — weaker ground, and the report says which.
- **One feature's lens (planned) / bank-bounded floor (plan-free).** Planned mode
  roots the failure within the feature's code + one hop to call sites; a cross-
  feature cause surfaces as a `structural` escalation. Plan-free mode's loaded
  module guarantees the *known* failure modes get checked; novel modes depend on the
  code walk, and absence of a confirmed hypothesis is not absence of a defect.
- **Shares the model's blind spots.** It diagnoses with the same model family that
  wrote the code; a shared misconception can mis-root the cause. Independent ≠
  omniscient.
