---
name: ce-ux-audit
description: |
  Audit a running app's UX and report evidence-bound findings — auto-detecting whether a plan owns the surface. Journey-walk mode (a plan's traced journeys): walk each planned journey against the running app and report mechanical findings — dead ends, plan-vs-reality gaps, cross-feature inconsistencies, broken links, missing states. Adversarial-discovery mode (no plan owns the target, or a plain running app): chaos-test/fuzz/adversarially-probe the app to DISCOVER unknown UX problems — validation gaps, state loss, layout breakage, accessibility violations — on any repo. Findings, not verdicts; read-only on code; never patches.
  Triggers: UX-audit/smoke-test/walk the journeys of an implemented plan; or chaos-test/fuzz/adversarially-probe/UX-explore a running app plan-free. Auto-detects journey-walk vs adversarial-discovery mode from plan state — you need not know which.
argument-hint: "[journey | scope | running-app-url]"
allowed-tools: Read, Write, Glob, Grep, Bash, AskUserQuestion, Skill
---

# Ux Audit

**Invocation input:** Journey, scope, or running app to audit (optional): $ARGUMENTS


Walk a running app's UX via the browser and report **evidence-backed findings**
an agent can reliably detect — dead ends, plan-vs-reality gaps, cross-feature
inconsistencies, broken links, missing states, validation gaps, state loss,
layout breakage, accessibility violations.

The workflow is **read-only on code and existing artifacts**. It finds issues and
**escalates** to the rest of the toolset (`/core-engineering:ce-implement`, `/core-engineering:ce-spec`, `/core-engineering:ce-plan`) —
it never patches code or modifies any other artifact. Same discipline as
`/core-engineering:ce-verify`.

It runs in one of **two auto-detected modes**, chosen by a Stage-0 probe of plan
state — you never have to know which:

- **Journey-walk mode** — a plan on disk owns the surface. *Verifies* each
  planned journey against its EARS criteria: walk it once, run the mechanical
  checks, report where the running app diverges from the traced plan.
- **Adversarial-discovery mode** — no plan owns the target (a plain running app,
  or a repo with no traced journeys). *Discovers* unknown problems by exploring
  journeys the planner never traced and probing inputs and states no spec
  specified — a chaos taxonomy over inputs, sequence, auth, viewport, state.

Same evidence-bound finding shape and the same triage discipline in both modes;
different inputs and different jobs (verification vs discovery).

## Runtime Inputs

- **Target (mode-specific):** in **journey-walk mode** — an optional journey id /
  short name (without one, walk in full mode); the plan directory resolves via
  `docs/plans/plans.json`. In **adversarial-discovery mode** — an app URL (or a
  discoverable dev/build command) plus an optional scope (journey, route, area,
  or empty for whole app) and an optional project description.
- **Loaded read-only inputs** are mode-specific and enumerated in the mode's
  stage file: journey-walk loads `feature-plan.md` (journey trace), `plan.json`,
  each implemented feature's `ce-spec.md` (EARS criteria), `shared-context.md`;
  adversarial-discovery loads only the running app (source of truth) and the
  optional description (a hint).

Writes only the mode's artifact: **journey-walk** → `ux-findings.md` +
an `evidence/` directory in the plan directory (`docs/plans/<slug>/`);
**adversarial-discovery** → a dated `docs/ux-audits/<date>-<slug>.md` +
`docs/ux-audits/evidence/<date>-<slug>/` (never overwritten — each run is a dated
snapshot).
For an adversarial same-day collision, resolve the run key before writing: use
`<date>-<slug>` first, then `<date>-<slug>-2`, `-3`, and so on for report and
evidence together.

## Preconditions

- A browser MCP is available (Claude in Chrome / Claude Preview). If not, **stop
  and report** — this workflow cannot run without it, in either mode.
- The app can start locally or is reachable at a URL (the build/dev commands are
  discoverable, or the human provides the URL).
- Credentials are provided when any protected route is in scope.

## Execution Contract

*Gate locator (HITL R5):* print `Gate N of M — <name>` at every interactive gate; compute M from the gates that actually fire this run, never a hardcoded constant.

0. **Session write lease (structural, first act).** `python3 "${CLAUDE_SKILL_DIR}/scripts/write-lease.py" --set --skill ce-ux-audit --allow 'docs/plans/**/ux-findings.md' --allow 'docs/plans/**/evidence/**' --allow 'docs/ux-audits/**'` — one lease covers both modes' write boundaries (journey-walk writes under `docs/plans/**`; adversarial-discovery writes under `docs/ux-audits/**`); a run writes only its own mode's paths. Last act: `python3 "${CLAUDE_SKILL_DIR}/scripts/write-lease.py" --restore-baseline`. A denied write mid-session means this contract and the action disagree — reconcile; never edit or delete the lease to proceed.
1. **Never patch code, edit specs, or modify feature files.** Find, do not fix — in both modes. Write only the mode's report + its `evidence/`; no edits, no commits, ever.
2. **Running-target consent [material].** Starting the app, driving it, or probing it happens only on the human's explicit confirmation at the Stage-0 gate (or with an already-running app the human names). Never start or hit a target the human has not sanctioned; a protected route needs its credentials first.
3. **Evidence-bound.** Every finding carries URL + screenshot + DOM snapshot + (where relevant) console output. No evidence → no finding.
4. **Findings, not verdicts.** The agent reports observations; the human triages. It never declares pass / fail.
5. **Bounded exploration.** Walk each journey once; follow visible nav links **one hop out** from the path; a probe budget per category per journey (adversarial mode); no infinite link-walking.
6. **Honest scope.** Detects mechanical issues, pattern-based inconsistencies, and a **coarse readability floor** (the Surface Critique pass — overlap / occlusion / off-canvas / illegible density / a missing primary affordance). It renders **no aesthetic verdict** — palette, polish, and brand feel stay the human's call.
7. **Web-first.** Scoped to user-facing rendered surfaces. Pure CLI / SDK / server-only apps are out of scope.

## Cross-cutting rule — Findings, Not Verdicts

A finding is `{category, severity, journey, feature/step, URL, observation, evidence, suggested escalation}` (adversarial-discovery mode adds `probe` and `type` for chaos provenance — see its stage file).

The agent never declares pass / fail. The human triages each finding:

| Triage | Result |
|---|---|
| **Escalate** | Record the suggested skill (`/core-engineering:ce-implement <id>`, `/core-engineering:ce-spec <id>`, `/core-engineering:ce-plan`) in the report |
| **Defer** | Record as a known limitation in the report |
| **Dismiss** | False positive — record the dismissal and its reason (kept in the report, never silently dropped) |

Triage routes every real finding to exactly one of `implement`, `spec`, `plan`, or accept — the same escalate-up chain as the rest of the toolset. For plan-less repos (adversarial-discovery mode) the escalation column is advisory only — the human routes each finding wherever the project actually handles bugs.

## Stage 0 — Mode Probe *(auto-detect, announced, never a question)*

Resolve the mode yourself from repo state — **plan-existence is internal state the
user should not have to know**, so this is an announced auto-detect with an
override escape hatch, **never** a question:

1. **Read `docs/plans/plans.json`** (read-only). If it is absent → **adversarial-discovery mode**.
2. **If present, resolve whether a plan owns the target surface.** A named journey
   id / plan slug that resolves to a plan with at least one `implemented`
   user-facing feature → **journey-walk mode**. A bare running-app URL / route /
   area the plan does not trace, or a plan with no `implemented` user-facing
   feature → **adversarial-discovery mode**. Several plans match → name the
   candidates and ask which plan to audit.
3. **Announce the detected mode in one line, then proceed** — offer the override,
   do not gate on it:
   - Journey-walk: *"Journey-walk mode — `docs/plans/<slug>/` owns these journeys;
     walking them against the running app. (To force a plan-free adversarial
     probe instead, say so.)"*
   - Adversarial-discovery: *"Adversarial-discovery mode — no plan owns this
     target; probing for unknown UX problems. (To walk a plan's traced journeys
     instead, name the plan slug.)"*
4. **Load the mode's stage file and continue:**
   - **journey-walk** → `${CLAUDE_SKILL_DIR}/mode-journeys.md`
   - **adversarial-discovery** → `${CLAUDE_SKILL_DIR}/mode-adversarial.md`

The announcement is not one of the interactive gates counted in `Gate N of M` — it
is an auto-detect read-back. The mode's own **material** gates (the Stage-0 scope /
running-target gate in both modes, the adversarial mode's journey-list confirm, and
each mode's triage) are counted per that mode's stage file.

## Human-in-the-Loop — tiered

- **Stage 0 (announced auto-detect)** — the mode read-back above; override, never a
  question.
- **Both modes** — a **material** Stage-0 scope + running-target gate (confirm
  scope, that the app is running or should be started, and that credentials are
  present if needed).
- **Adversarial-discovery mode** — one extra **light material** gate: confirm or
  edit the discovered-journey list before probing.
- **Both modes** — a **tiered** triage of findings at the end (high-severity or
  ambiguous → material decisions; clear-cut → batch approve-with-veto).

No per-step verdicts during the walk — the agent walks / probes autonomously,
captures evidence, and reports.

## Modes — how to run

This skill is a thin **orchestrator**: the Stage-0 mode probe above chooses the
mode, then the mode's stages live in a companion file you load only when you reach
it. Read each at `${CLAUDE_SKILL_DIR}/<file>` by absolute path.

| Mode | Load this file | Then |
|---|---|---|
| Journey-walk (a plan owns the surface) | `${CLAUDE_SKILL_DIR}/mode-journeys.md` | Scope → walk each planned journey → mechanical + cross-feature checks → triage → write `ux-findings.md` |
| Adversarial-discovery (no plan) | `${CLAUDE_SKILL_DIR}/mode-adversarial.md` | Scope → discover journeys → probe (chaos taxonomy) → triage → write the dated report |

**The companion files named above are bundled in this skill's own directory.** `${CLAUDE_SKILL_DIR}` resolves to this skill's directory regardless of the current working directory. Resolve it once if needed (`ls "${CLAUDE_SKILL_DIR}"`) and read each file by its resulting absolute path; **never load a companion file by bare name** — in an installed plugin the working directory is the user's project, so a bare name finds nothing and triggers a filesystem search. (`ux-findings.md`, `evidence/`, `docs/ux-audits/`, and everything under `docs/plans/` live in the user's project, not this skill — those paths stay as-is.)

---

## Escalation

Implementation defects route to `/core-engineering:ce-implement`; missing or wrong criteria route to
`/core-engineering:ce-spec`; unplanned journeys or structural UX gaps route to `/core-engineering:ce-plan`; small,
bounded UI defects on a plan-less repo can route to `/core-engineering:ce-patch`. This workflow
writes findings and evidence only, in both modes — the mode's own stage file
carries the per-finding routing table.

## Honest Limitations

- **Mechanical + a coarse readability floor, no aesthetic verdict.** Beyond the mechanical checks, the **Surface Critique** pass reports *functional* surface findings (overlap, occlusion, off-canvas, illegible density, an undiscoverable primary affordance) from a first-time-user standpoint — fallible vision (it shares the model's blind spots), every finding the human's to triage. It renders no aesthetic verdict: "is this confusing / does it feel right" — palette, polish, brand feel — stays the human's.
- **Bounded by the mode's inputs.** Journey-walk is bound by the plan's trace (a flow the planner never surfaced is not walked — though the Surface Critique still assesses the assembled surface holistically once); adversarial-discovery is bound by its probe budget (it finds problems, not all problems, and re-runs surface different ones) and, without a description, emits only `gap-vs-heuristic` findings.
- **Web-first for DOM-snapshot checks; the screenshot critique covers canvas.** The DOM-snapshot mechanical checks (dead-end, broken link, missing `alt`) are web-DOM-bound and honestly N/A for a `<canvas>`. The screenshot-based **Surface Critique** additionally covers canvas/WebGL surfaces from pixels (the DOM exposes no per-object children). Backend / CLI / API / library audits remain out of scope.
- **False positives expected.** Triage is the human's job; the workflow never auto-acts on findings.
- **Stateful session.** Fixture data / known starting state may be required; a protected flow needs credentials. When a prerequisite is missing mid-run, the workflow asks rather than guessing (adversarial mode's *Stuck or Ambiguous* rule), rather than faking confidence.
