# ce-ux-audit — Journey-walk mode (a plan owns the surface)

Stage file for the `ce-ux-audit` skill (orchestrator: `SKILL.md`). The Stage-0 mode
probe routed here because `docs/plans/plans.json` resolves the target to a plan with
at least one `implemented` user-facing feature — the plan's traced journeys are the
**contract** to verify against. Load this file once the probe announces journey-walk
mode.

The shared Execution Contract (write lease, findings-not-verdicts, read-only,
evidence-bound, running-target consent) is stated once in `SKILL.md`; this file adds
only the mode-specific stages.

**Next:** this is the last file for a journey-walk run — the run ends with the
Closing block below.

---

## What journey-walk mode is

Walk the plan's traced journeys against the running app and report where the running
app diverges from the plan and its specs' EARS criteria. This is *verification*: the
plan's Reachability / Consumability Trace and the specs' EARS criteria define the
expected behaviour every step is checked against — never invented flows.

It runs in two sub-modes, keyed to the argument:

- **Milestone** (`<journey>` argument) — walk one journey once all its composing features are implemented.
- **Full** (no argument) — walk every journey whose composing features are implemented; report the rest.

## Stage 0 — Load and Scope

Resolve the plan via `docs/plans/plans.json` (the mode probe already did this).
Derive each feature's state from its artifacts (the same `implemented` condition
`verify` derives; only implemented-or-not matters here, not verify's
`specced`/`planned` split):

A feature is `implemented` only when `specs/<id>/tasks.json` exists, every task is `done`, and `specs/<id>/verification.md` exists; otherwise it is not yet implemented.

Identify scope:

- **Milestone** (`<journey>` argument): the target journey. Every composing feature must be `implemented`. If any is not, stop and report which.
- **Full** (no argument): every journey whose composing features are all `implemented`. Skip the rest; report them.

Detect or start the app — use the build / dev commands recorded in `shared-context.md`'s codebase profile. Ask the human whether the workflow should start the app or whether the human has already started it.

**Scope checkpoint [material]:** confirm scope and that the app is running — *Proceed / Abort.*

---

## Stage 1 — Walk and Detect

For each in-scope journey:

1. Restate the journey: its purpose, owning features, the step trace from the plan, each step's **expected observable** (from the plan's journey table), and the per-step EARS criteria from each owning spec — together these are the "expected behaviour" each step is checked against. (This audit's modality is *browser* by design — see Web-first scope.)
2. Drive the journey end-to-end via the browser MCP. At each step capture: URL, screenshot, DOM snapshot, console output.
3. At each step, run the **mechanical checks**:

   | Check | Catches |
   |---|---|
   | Dead-end | Step has no clear exit (no nav, no continue, no return) |
   | 404 / broken link | A followed link returned an error |
   | Console errors | JS errors during the step |
   | Missing error state | Spec mentions error handling; no error path observed |
   | Missing empty state | List / collection step shows blank with no "empty" UI |
   | Accessibility | Missing `alt`, unlabeled inputs, low contrast (heuristic) |
   | Spatial readability | **Surface Critique** over the captured screenshot — primary elements overlapping/occluded/off-canvas, illegibly crowded density, or a missing primary-action affordance. A coarse, falsifiable **functional** floor, not a "is this nice" judgment; works on `<canvas>`/WebGL too (reads pixels, not DOM) |
   | Plan-vs-reality | Journey says X happens; the running app does Y |
   | Coverage gap | Entry surface unreachable from any top-level route |

4. Follow visible nav links **one hop out** from the journey path — catches dead-ends a user might naturally hit adjacent to the planned walk.
5. From the second journey onwards, run **cross-feature inconsistency checks** against previously-walked journeys:

   | Check | Catches |
   |---|---|
   | Action-label drift | Same action labelled differently (Save / Submit / Apply) |
   | Pattern drift | Similar UI elements styled inconsistently |
   | Navigation drift | Same "cancel" / "back" semantics going to different places |
   | Tone drift | Error / empty messages with markedly different tone |

   *(This drift-check table is mirrored in this skill's `mode-adversarial.md` — a change to the check set must be applied to both.)*

**Walk every step regardless of findings** — do not early-exit. The human wants the complete picture, not a fail-fast halt.

**Bounded exploration:** journey path + one hop. No infinite link-walking.

Per finding, capture evidence to `docs/plans/<slug>/evidence/F-N.{png,html,txt}` and assemble the finding record.

---

## Stage 2 — Triage and Report

### 2.1 Categorize and Score

Group findings by category. Assign severity heuristically:

- **High:** dead-end, broken link, console error, plan-vs-reality contradiction.
- **Medium:** missing error / empty state, accessibility violation, plan-vs-reality drift on details.
- **Low:** label / pattern / navigation / tone inconsistency.

Suggest an escalation per finding (the human still decides):

| Finding shape | Suggested route |
|---|---|
| Spec exists and is right; app diverges | **bug** → `/ce-implement <id>` |
| Spec doesn't anticipate this state | **spec gap** → `/ce-spec <id>` |
| Journey itself is broken / cross-feature | **plan** → `/ce-plan` |
| Pattern issue spanning many features | batched escalation or accepted backlog |

### 2.2 Triage  [tiered]

Present findings batched by category × severity, with evidence per finding. The human triages each per the **Findings, Not Verdicts** rule in `SKILL.md`. High-severity or ambiguous findings → material decisions; clear-cut ones → batch approve-with-veto.

### 2.3 Write the Report

Write `ux-findings.md` in the plan directory. The file is **cumulative**: each run adds new findings and triage records; previously-triaged findings stay.

Use the template below.

---

## Findings File Template — `ux-findings.md`

````markdown
# UX Findings: <plan-slug>

> Generated by `/ce-ux-audit` (journey-walk mode)
> Last run: YYYY-MM-DD · Mode: milestone (<journey>) | full
> Journeys walked: N of M · Findings: T (H high, M medium, L low)

## Summary by Category

| Category | High | Medium | Low | Total |
|---|---|---|---|---|
| Dead-end | … | … | … | … |
| Plan-vs-reality | … | … | … | … |
| Inconsistency | … | … | … | … |
| Accessibility | … | … | … | … |
| Broken / 404 | … | … | … | … |
| Missing state | … | … | … | … |

## F-N — <short title>  [<severity>]

- **Journey:** <name> (step <n>)   ·   **Feature:** <id>
- **URL:** <url>
- **Observation:** <what the agent saw>
- **Evidence:** `evidence/F-N.png`, DOM snapshot, console
- **Spec says:** <AC reference and text, if applicable>
- **Suggested escalation:** <skill>
- **Triage:** Escalate / Defer / Dismiss — <date>, by human
  ↳ Escalated to: <skill> | Deferred as: <note> | Dismissed: <reason>

## Triaged

| ID | Category | Severity | Triage | Escalation | Date |
|---|---|---|---|---|---|
| F-1 | … | high | Escalate | /ce-implement 04-… | 2026-MM-DD |
````

Evidence files live in `docs/plans/<slug>/evidence/F-N.{png,html,txt}`.

---

## Closing (journey-walk mode)

After writing the report, confirm:

```text
UX Audit complete: <slug> — <mode>
Journeys walked: <N> of <M>
Findings:        <total> (<high> high, <med> medium, <low> low)
Triaged:         <triaged> · Pending: <pending>
Report:          docs/plans/<slug>/ux-findings.md
```

Point to the next action: if any finding was escalated to `/ce-implement` or `/ce-spec`, name the first one. Never commit; never deploy.
