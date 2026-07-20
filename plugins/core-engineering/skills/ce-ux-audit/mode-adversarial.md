# ce-ux-audit — Adversarial-discovery mode (no plan owns the surface)

Stage file for the `ce-ux-audit` skill (orchestrator: `SKILL.md`). The Stage-0 mode
probe routed here because `docs/plans/plans.json` is absent, or no plan owns the
target (a plain running app / a repo with no traced journeys). Load this file once
the probe announces adversarial-discovery mode.

The shared Execution Contract (write lease, findings-not-verdicts, read-only,
evidence-bound, running-target consent) is stated once in `SKILL.md`; this file adds
only the mode-specific stages and rules.

**Next:** this is the last file for an adversarial-discovery run — the run ends with
the Closing block below.

---

## What adversarial-discovery mode is

Adversarially probe a running web app to **discover unknown UX problems**. Where
journey-walk mode *verifies* planned journeys against planned criteria,
adversarial-discovery mode *discovers* problems by exploring journeys the planner
never traced and probing inputs and states the spec never specified.

The two modes are the same skill with a different job:

| | Journey-walk mode | Adversarial-discovery mode (this file) |
|---|---|---|
| Inputs | A plan with implemented features | App URL + optional description |
| Expected behaviour from | EARS criteria in specs | Description (intent) + UX heuristics |
| Job | Verification | Discovery |
| Needs a plan | Yes | No |

## Mode-specific rules

- **Description as hint, app as source of truth.** A project description (if
  present in the conversation) enables **gap-vs-description** findings (divergence
  from stated intent); without it, only **gap-vs-heuristic** findings. Use the
  description to surface intended-but-missing journeys; do not pretend it
  specifies behaviour the way EARS criteria do — descriptions tend to be
  aspirational and lag reality.
- **Non-deterministic by design.** Each run is a dated snapshot — re-runs surface
  different findings, so the report's filename is dated and runs never overwrite
  prior runs.
- **Web UI only.** Pure CLI / SDK / server-only apps are out of scope (different
  consumability concerns).
- **Credentials** are required when any protected route is in scope.

## Cross-cutting rule — Stuck or Ambiguous → Ask, Don't Guess

Chaos probing runs into a long tail of micro-ambiguities the workflow cannot enumerate in advance — a second user's id for a cross-user probe, a credential for a protected route, fixture data for a *50+ items* state probe, a choice between two plausible interpretations of the description, a persistent unexpected error from the browser MCP. For each:

- **Stop and ask the human** — never guess and continue, never silently skip.
- One short, direct question per stuckness; resume on the answer.
- Record the question and the answer in the report's **Open Questions / Stops** section so the run stays auditable.

This rule applies *between* the named HITL gates (Stages 0, 1, 3) — it covers everything in between.

---

## Stage 0 — Load and Scope

- Resolve the app URL: from the argument, the conversation, or by asking the human. If asked to start the app, look for a build/dev command in the repo (`package.json` scripts, `Makefile`, README mentions); start it via `Bash` only on the human's explicit confirmation.
- Verify the browser MCP is available; if not, stop with a clear message naming what's needed (`Claude_in_Chrome` or `Claude_Preview`).
- Capture the (optional) description and (optional) scope hint from the conversation.
- Derive the run slug: from the scope (a journey name slugified, an area name, or `whole-app`).

**Scope + running-target checkpoint [material]:** confirm the app URL, that the app is running (or should be started), and that credentials are present if needed — *Proceed / Abort.*

---

## Stage 1 — Discover Journeys

1. Visit the entry URL with the browser MCP. Capture an initial screenshot and DOM.
2. Enumerate the navigation graph: visible nav links, primary buttons, route landmarks (header/footer/sidebar), any sitemap / `robots.txt` clues.
3. If a description was provided, match intended journeys against the discovered routes. **Surface intended-but-missing journeys as findings immediately** (gap-vs-description, severity high) — these need no probing to detect.
4. Cap candidate journeys at **3–8**. Each is `{name, entry → goal, candidate steps}`. Pick journeys that touch distinct areas; don't heavily overlap.
5. **Journey-list confirm [light material]:** present the list:

   ```
   Discovered journeys:
   1. Sign up → empty dashboard
   2. Login → dashboard
   3. Create item → confirmation
   4. Search → result detail
   …

   Proceed / Edit list / Abort?
   ```

   Accept user edits (rename, add, remove); proceed with the confirmed set.

---

## Stage 2 — Probe Each Journey

For each journey in turn:

1. Restate the journey and its steps.
2. Walk the happy path end-to-end via the browser MCP. At each step capture URL + screenshot + DOM + console.
3. At each step run the **mechanical checks** (the same set journey-walk mode uses):

   | Check | Catches |
   |---|---|
   | Dead-end | Step has no clear exit |
   | 404 / broken link | A followed link returned an error |
   | Console errors | JS errors during the step |
   | Missing error state | Likely-erroring action with no error UI observed |
   | Missing empty state | List / collection step shows blank with no "empty" UI |
   | Accessibility (heuristic) | Missing `alt`, unlabeled inputs, low contrast |
   | Coverage gap | Entry surface unreachable from any top-level route |

4. At each interactive step apply the **chaos probe taxonomy**. Apply each *category* at least once per journey on the most relevant step — do not exhaust every probe on every field:

   | Category | Probes | Catches |
   |---|---|---|
   | **Input** | empty submit · max-length · Unicode (emoji, RTL, combining) · HTML-like `<script>` · whitespace-only · negative / huge numbers · malformed types | Validation gaps · escaping / rendering bugs · crash on edge inputs · poor error messages |
   | **Sequence** | browser back mid-flow · refresh mid-flow · deep-link to mid-flow URL · two tabs racing the same form | State loss · stale data · UX-visible race conditions |
   | **Auth** *(protected only)* | access logged-out · cross-user resource via URL id · expired / cleared token | Permission leaks · auth-failure UX |
   | **Viewport** | 375 (mobile) · 768 (tablet) · 1920 (wide) | Layout breakage · overflow · hidden controls |
   | **Surface readability** | **Surface Critique** over each viewport's screenshot (against a generic default contract — no plan exists here) | Primary elements overlapping / occluded / off-canvas · illegibly crowded density · undiscoverable primary action · a surface failing its evident goal — **functional**, fallible, evidence-bound; works on `<canvas>`/WebGL too (reads pixels, not DOM) |
   | **Accessibility** | keyboard-only Tab walk · focus indicators · landmarks / ARIA · alt text · contrast (heuristic) | A11y violations · keyboard traps |
   | **State** | empty data · single item · 50+ items · very long strings | Missing empty / singular / many states · truncation |
   | **Network** *(best-effort)* | slow throttle · simulated 500 (if mockable) · timeout | Loading state · error recovery · perceived performance |

5. **One hop out** from the journey path: follow visible nav links one step beyond the planned trace — catches dead-ends a user naturally hits adjacent to the journey. Never recurse further.
6. From the **second journey onwards**, run the **cross-journey drift checks**:

   | Check | Catches |
   |---|---|
   | Action-label drift | Same action labelled differently (Save / Submit / Apply) |
   | Pattern drift | Similar UI elements styled inconsistently |
   | Navigation drift | Same "cancel" / "back" semantics going to different places |
   | Tone drift | Error / empty messages with markedly different tone |

   *(This drift-check table is mirrored in this skill's `mode-journeys.md` — a change to the check set must be applied to both.)*

**Walk all steps regardless of findings** — do not early-exit. The human wants the complete picture.

Per finding, capture evidence to `docs/ux-audits/evidence/<date>-<slug>/F-N.{png,html,txt}` and assemble the finding record.

---

## Stage 3 — Triage and Report

### 3.1 Categorize and Score

Group findings by category × probe. Assign severity heuristically:

- **High:** dead-end, broken link, console error, security-visible probe failure (XSS-rendered, auth bypass UX), gap-vs-description on a stated journey, viewport breakage that hides a primary action.
- **Medium:** missing error / empty state, a11y violation, sequence-induced state loss, plan-vs-reality drift on details, layout issues on a supported size that don't hide actions.
- **Low:** label / pattern / nav / tone drift, minor heuristic violations.

Suggest an escalation per finding (advisory — the human still decides):

| Finding shape | Suggested route |
|---|---|
| Spec exists and is right; app diverges | **bug** → `/core-engineering:ce-implement <id>` |
| Spec doesn't anticipate this state | **spec gap** → `/core-engineering:ce-spec <id>` |
| Journey design is broken / cross-feature | **plan** → `/core-engineering:ce-plan` |
| No plan in the repo | **review** — human decides |

### 3.2 Triage  [tiered]

Present findings batched by category × severity, with evidence per finding. The human triages each per the **Findings, Not Verdicts** rule in `SKILL.md`. High-severity / ambiguous → material decisions; clear-cut → batch approve-with-veto.

### 3.3 Write the Report

Write `docs/ux-audits/<date>-<slug>.md`. **Each run is a dated snapshot — never overwrite a previous run.** Use the template below.

---

## Report Template — `docs/ux-audits/<date>-<slug>.md`

````markdown
# UX Probe Audit — <date> · <slug>

> Generated by `/core-engineering:ce-ux-audit` (adversarial-discovery mode)
> URL: <url>   ·   Browser: <name>   ·   Viewports tested: 375 / 768 / 1920
> Description provided: yes / no
> Journeys discovered: <N>   ·   Probed: <M>   ·   Skipped: <list>
> Findings: <T>  (<H> high · <M> medium · <L> low)

## Discovered Journeys

| # | Name | Entry → Goal | Steps |
|---|---|---|---|

## Probe Budget Run

| Category | Per-journey applied | Skipped (rationale) |
|---|---|---|

## Findings

### F-N — <short title>  [severity]

- **Journey:** <name> (step <n>)
- **URL:** <url>
- **Probe:** <category / specific>
- **Type:** gap-vs-description | gap-vs-heuristic
- **Observation:** <what was seen>
- **Evidence:** `evidence/<date>-<slug>/F-N.png` + DOM + console
- **Expected** *(if gap-vs-description)*: <intent line from description>
- **Suggested action:** <skill or "review">
- **Triage:** Escalate / Defer / Dismiss — <date>
  ↳ Escalated to: <skill> | Deferred: <note> | Dismissed: <reason>

## Cross-Journey Inconsistencies

| # | Drift type | Examples | Severity |
|---|---|---|---|

## Open Questions / Stops

| # | When | Question asked | Human's answer | Effect on run |
|---|---|---|---|---|

## Triaged

| ID | Cat | Sev | Type | Triage | Action | Date |
|---|---|---|---|---|---|---|
````

Evidence files live at `docs/ux-audits/evidence/<date>-<slug>/F-N.{png,html,txt}`.

---

## Closing (adversarial-discovery mode)

After writing the report, confirm:

```text
UX Probe complete: <slug> — <date>
Journeys discovered: <N>  ·  Probed: <M>
Findings:           <total> (<high> high, <med> medium, <low> low)
Triaged:            <triaged>  ·  Pending: <pending>
Report:             docs/ux-audits/<date>-<slug>.md
```

Point to the next action: if any finding was escalated to `/core-engineering:ce-implement` or `/core-engineering:ce-spec`, name the first one. **Never commit; never patch; never deploy.**
