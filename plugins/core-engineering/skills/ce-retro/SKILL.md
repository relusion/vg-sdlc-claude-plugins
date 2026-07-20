---
name: ce-retro
description: |
  Read-only retrospective over a plan's pipeline — aggregate the .metrics.jsonl stream and existing artifacts into descriptive signals (testability, escalation, park/retry/circuit-break rates, review disposition, complexity drift). Scope-boxed by plan, and optionally time-boxed by a --since/--until window for a sprint retro; renders for a chosen audience (standup, sprint-review, on-call handoff) without ever computing a number the artifacts do not carry. Mutates nothing.
  Triggers: retrospective/metrics/health-report/how-did-this-plan-go, sprint retro, standup summary, on-call handoff brief. Dynamic counterpart of the static /ce-plan-audit.
argument-hint: "[plan-slug] [standup|sprint-review|handoff] [--since YYYY-MM-DD] [--until YYYY-MM-DD]"
allowed-tools: Read, Glob, Grep, Bash, AskUserQuestion, Skill
---

# Retro

**Invocation input:** Plan to report on: $ARGUMENTS


Aggregate what the pipeline already recorded into a read-only retrospective. This
is the toolset's **observability** surface: every other skill produces rich
per-run artifacts (specs, `verification.md`, `code-review.md`, auto-build run
reports) and appends to a lightweight metrics stream; `retro` reads them across
runs and reports descriptive signals. It **mutates no plan artifact** and renders
no verdict — the numbers are signals over the model's own (fallible) outputs, not
ground truth.

## Runtime Inputs

- **Plan slug (optional):** which plan to report on. If absent, read
  `docs/plans/plans.json` and ask (or report across all plans).
- **Loaded (read-only):** `docs/plans/<slug>/.metrics.jsonl` (if present), each
  `specs/<id>/ce-spec.md` (TC tags), `specs/<id>/tasks.json` (task counts),
  `specs/<id>/verification.md`, `code-review.md` + each `specs/<id>/review-summary.json`
  (review findings by lens × severity × confidence + the per-feature `suppressed`
  count) + `review-learnings.md` (dismissal `RL-N` entries — for the
  recurring-dismissal / promote-to-`review-policy.md` signal), `plan.json` and/or
  `feature-plan.md` (Final Complexity per feature — for the complexity-drift
  signal), `docs/plans/express-log.jsonl` (accepted express-patch activity, when
  reporting repo-wide), and `auto-build/<date>-run.md`.

## Execution Contract

0. **Session write lease (structural, first act).** `python3 "${CLAUDE_SKILL_DIR}/scripts/write-lease.py" --set --skill ce-retro --allow 'docs/plans/**/audit-export/**' --allow 'docs/plans/**/evidence-pack/**'` — writes nothing except the two consented, human-invoked exports (the audit export and the evidence pack), and the write guard now enforces that. Last act: `python3 "${CLAUDE_SKILL_DIR}/scripts/write-lease.py" --restore-baseline`. A denied write mid-session means this contract and the action disagree — reconcile; never edit or delete the lease to proceed.
1. **Read-only.** Read artifacts + the metrics stream; write nothing. No edits, no commits. Stage 1 runs `scripts/audit-export.py` **to stdout** as the deterministic aggregation floor — read-only, writes nothing, mutates nothing, so it needs **no consent** (it is the same read the whole skill is licensed to do, just done by a deterministic tool instead of by hand). *Two consented exceptions — both **writes**, each on an **explicit human request**:* a durable audit export (`audit-export.py --out`, below) and a compiled evidence pack (`evidence-pack.py --out`, below) — both deterministic projections that write a **new dated file / directory** and mutate no source artifact.
2. **Derive, don't fabricate.** Every number traces to a recorded artifact or a metrics line. A missing source is reported as "no data", never silently zeroed.
3. **Signals, not verdicts.** Report rates and hotspots; never declare the plan "good" or "done". The human interprets.
4. **Estimates stay labeled.** Token / duration figures from the stream are estimates (producers label them so) — carry the label through.

## The metrics stream — `docs/plans/<slug>/.metrics.jsonl`

The **canonical schema** (one JSON object per line) every producer appends to. It
is append-only, best-effort, and **never gates a run** — a missing or partial
stream degrades the relevant section of this report to "partial / no data", never
an error.

```json
{"ts":"YYYY-MM-DD","stage":"plan|spec|implement|verify|review|debug|release|document|auto-build|patch","plan":"<slug>","feature":"<id>|null","event":"stage-complete|gate|escalation|park|retry|circuit-break|attestation","gate":"pass|fail|null","escalation_type":"/ce-implement|/ce-spec|/ce-plan|null","detail":"<short>","model":"<id>|null","est":{"tokens":0}}
```

- `feature` is `null` for plan-level events.
- `est` holds **estimates only** (e.g. `tokens` ≈ chars/4) — never measured figures.
- `model` is the model id that **actually executed** the stage, read from the
  `.claude/ce-session-model.json` sidecar the `model-attest.py` hook refreshes
  (the runtime leg of the model-tier policy). Emit it on gate-stage and
  `attestation` lines; it is **`null` when the sidecar is absent**, so a
  hook-less run records the *absence*, never a guessed tier. `/ce-retro` maps it through `model-policy.json`
  `tier_patterns` (see the Model-tier attestation signal in Stage 1).
- Producers derive every field from data they already have, add the line *after*
  the stage's real work and gate complete, and swallow any failure.

### The `attestation` event — one line per HITL-gate decision

Every interactive Human-in-the-Loop gate a skill presents emits **one**
`attestation` line recording *what the human decided* — so the confirm-vs-override
ratio per gate becomes measurable (the raw material for proportionality tuning and
the evidence pack's human-attestation section). The **emitters** are the skills
that own the gates (`/ce-implement`, `/ce-review`, …); this section defines the
shape they emit into, and `audit-export.py` rolls the lines up under an
`attestations` summary (`confirms` / `overrides` / `edits` / `loops` / `by_gate`).

```json
{"ts":"YYYY-MM-DD","stage":"implement|review|...","plan":"<slug>","feature":"<id>|null","event":"attestation","gate":"<gate-name>","gate_index":"N of M","action":"confirm|override|edit|loop","basis_shown":true,"detail":"<short>","model":"<id>|null"}
```

- `gate` carries the **gate name** here — *not* `pass`/`fail`. That field is
  reused: `pass`/`fail` is only meaningful on an `event:"gate"` line.
- `gate_index` is the HITL Gate Standard **R5 `Gate N of M` locator string,
  verbatim** — the same string the gate printed to the human is the telemetry key,
  so there is no second vocabulary to keep in sync.
- `action` is what the human did at the gate: `confirm` (accepted the rendered call
  as-is), `override` (rejected or changed it), `edit` (accepted with a
  modification), or `loop` (a re-prompt of the *same* gate — one `loop` line per
  re-ask, so a churning gate stays visible).
- `basis_shown` records whether the gate rendered its evidence-first basis (R2) — a
  `false` here is itself a calibration signal (a gate asked for a judgment without
  showing the human its basis).

## Stage 0 — Load and Scope

Resolve the plan(s) via `docs/plans/plans.json`. Load `.metrics.jsonl` if present
and the per-feature artifacts. Confirm scope with the human (this plan / all
plans): *Proceed / Abort.* If neither a metrics stream nor artifacts exist, report
"no data yet" and stop.

**Two orthogonal dials, both optional, both resolved at this gate:**

- **Window (time-box).** A plan is *scope*-boxed; a sprint is *time*-boxed. `--since`
  / `--until` filter the metrics stream to a date range. **Only the stream can be
  windowed** — testability, evidence freshness, per-feature review state, and
  complexity drift are current on-disk state with no timestamp. The export says which
  is which in its `windowing` manifest; obey it (see the Audience section).
- **Audience.** `standup` · `sprint-review` (default) · `handoff` — a Stage-2
  *render*, never a different computation. Take it from `$ARGUMENTS` if present, else
  offer it as options on this same gate. Templates:
  `${CLAUDE_SKILL_DIR}/audiences.md`.

## Stage 1 — Aggregate

**Run the deterministic aggregation floor first.** Before narrating any number,
run the evidence compiler **to stdout** and read its JSON:

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/audit-export.py" docs/plans/<slug>
# time-boxed (a sprint retro), same command plus the window:
python3 "${CLAUDE_SKILL_DIR}/scripts/audit-export.py" docs/plans/<slug> \
  --since <date> --until <date>
```

A windowed export adds two keys you **must** read before narrating: `window`
(the bounds, the in/out/undated line census, and the day-granularity caveat) and
`windowing` (which blocks the filter touched — `windowed_blocks` — and which are
current state — `as_of_now_blocks`). Narrating an `as_of_now` number as if it
happened inside the window is a fabrication, and the export contradicts you in the
same document. Across plans, `scripts/metrics_report.py --since/--until` is the same
contract at repo scope.

This is read-only (it writes nothing without `--out`), so it needs no consent —
it is the Stage-0 lease's own read, done deterministically. **Narrate over its
counts; never hand-count `.metrics.jsonl` yourself.** The export tallies every
stream- and artifact-derived count this report needs — a hand recount can only
introduce drift, and the Done-state is that the report's numbers *equal* the
export's. For a signal the export carries, quote its field; only for the few it
does not (such as recurring dismissals) do you read the
underlying artifact — and even then never re-tally the JSONL by hand.

Compute each signal from its export field (or the noted artifact); **skip with
"no data" when the source is absent or the count is zero** (never block):

| Signal | Export field (deterministic floor) · else artifact |
|---|---|
| **Criteria-testability rate** | `testability` (`total` / `auto` / `harness_gap` / `judgment`, summed across specs from each spec's TC `verification:` tags) — narrate the % split; `total: 0` ⇒ "no data" |
| **Escalation hotspots** | `metrics.escalations[]` by feature × `escalation_type` (`/ce-implement` / `/ce-spec` / `/ce-plan`), **plus** entries whose `detail` begins `route:<cmd>` (lateral routes: `/ce-verify` / `/ce-review`) so none is silently dropped |
| **Park / retry / circuit-break rates** | `metrics.parks` / `metrics.retries` (+ `metrics.retries_by_feature`) / `metrics.circuit_breaks` (auto-build runs) |
| **Attestation (HITL) — confirm vs override** | `metrics.attestations` (`confirms` / `overrides` / `edits` / `loops` / `by_gate`) — the confirm-vs-override ratio per gate; a gate with many `overrides` or `loops`, or `basis_shown:false`, is a calibration signal for proportionality tuning |
| **Review-finding disposition** | per-feature `features[].review` (`blocking_high` / `findings_total` / `suppressed` / `by_severity`) for the current-state counts; **recurring dismissals** — the same finding shape dismissed across features / runs — from `review-learnings.md` `RL-N` entries + the climbing `suppressed` counts, reported as **promote-to-`review-policy.md` candidates**. Read-only — surfaced under *Signals worth a look*; the human promotes, `/ce-retro` never writes either file |
| **Complexity-vs-actual drift** | `complexity_drift[]` (per feature: planned `final_complexity` vs built `task_count` + `retries`) |
| **Gate pass/fail** | `metrics.gates` (`pass` / `fail`) |
| **Model-tier attestation** | each gate / `attestation` event's `model` field (read from `.metrics.jsonl` — a signal the export does not yet carry) mapped through `model-policy.json` `tier_patterns`: a model matching the `strong` list ran **on policy**; one matching a below-`strong` tier's list **ran below policy tier** — surface it as an *accepted degradation* (loudest first); one matching **no** list, or `model:null`, is **`unattested`** (reported as a finding, never assumed fine). This is the runtime check on "judgment/gate stages always use the strongest model" |

## Stage 2 — Report

Render the report **to the conversation** (read-only — no file written). Lead with
the signals that suggest where the process strained (escalation hotspots, parks,
high `manual:judgment` rates, complexity drift, **below-policy-tier or `unattested`
model runs**). Use the template below.

**Audience render.** Load `${CLAUDE_SKILL_DIR}/audiences.md` and follow the template
for the audience resolved at Stage 0 (`sprint-review` is the default and *is* the
template below). An audience re-orders and filters the **same Stage-1 numbers** — it
never computes a new one, never a ratio, a cost, or an ROI figure, because none of
those is a field on disk. That is why the audience lives in Stage 2 and the
deterministic floor in Stage 1: the JSON is identical whoever is reading.

## Report Template (conversation output)

```text
# Retro — <slug>  (<N> runs · <date range>)

## Testability
auto <a>% · manual:harness-gap <h>% · manual:judgment <j>%   (over <T> test cases)

## Escalation hotspots
<feature> → <target> ×<n>   (loudest first)

## Autonomy (auto-build)
parks <p> · retries <r> · circuit-breaks <c>   over <F> features

## HITL attestation  (confirm vs override)
confirms <c> · overrides <o> · edits <e> · loops <l>
<gate>: confirm <n> / override <n> / edit <n> / loop <n>   (loudest override-rate first)

## Review findings
<lens>: escalated <e> / deferred <d> / dismissed <x>

## Model-tier attestation  (runtime check: gate stages run on the strongest model)
attested <a> / unattested <u>   (over <G> gate + attestation events carrying a model)
below policy tier — accepted degradation (loudest first):
  <stage>/<gate> ran <model>  ×<n>   (policy tier strong · recorded <tier>)
unattested (no tier_patterns match, or model:null — hook-less run):
  <stage>/<gate> ×<n>

## Complexity drift
<feature>: planned <Simple|Moderate|Complex> vs <tasks> tasks, <retries> retries

## Express patch activity  (repo-wide report only)
accepted entries <n>   ·   latest accepted date <date|no data>

## Signals worth a look
- <plain-English observation, each tied to a number above>
```

## Audit Export (optional, consented, human-invoked)

`scripts/audit-export.py` compiles a plan's pipeline evidence — plan.json,
per-feature spec/tasks/verification/review artifact state, the metrics stream
(with unparseable lines counted, never skipped), run reports, and any legacy
patch `eligibility.json` still present — into **one structured JSON** an external reviewer or
compliance process can consume:

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/audit-export.py" docs/plans/<slug> \
  --out docs/plans/<slug>/audit-export/<date>-audit-export.json
```

Run it **only on explicit human request** (the consented exception in the
Execution Contract); default output is stdout, and the dated `--out` convention
keeps exports from colliding (one per day per plan). The script **refuses an
`--out` that would overwrite a source it reads** (plan.json, `.metrics.jsonl`,
`shared-context.md`, anything under `specs/`) — exit 1 — so the generated
artifact can never destroy a source of truth. The export is **evidence
compilation, not a compliance attestation** — it proves which artifacts exist
and what the pipeline recorded; it renders no judgment, and its own
`honest_limitations` field says so machine-readably.

## Evidence Pack (optional, consented, human-invoked)

Where the audit export compiles *this skill's* signals, `scripts/evidence-pack.py`
composes the **whole pipeline's** recorded evidence into one auditor-consumable
bundle — the audit-export compilation and the raw metrics stream, the hash-chained
guard log (with its `guard_log.py --verify` result and out-of-band chain head), the
`gate_runner.py` merge verdict (policy sha256 + base/head SHAs) when supplied, the
human attestations (verification report + attestation-telemetry rollup), per-stage
model identity with below-tier flags, the review-dismissal records, and the
**finding-disposition register** — plus verbatim, sha256-stamped copies of every
cited artifact:

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/evidence-pack.py" docs/plans/<slug> \
  --guard-log .claude/ce-guard-log.jsonl \
  --merge-verdict merge-verdict.json \
  --out docs/plans/<slug>/evidence-pack/<date>
```

**The accepted-risk register (`finding_dispositions`).** An advisory merge-bar gate
*suppresses* a finding a human consciously accepted in `.merge-bar/dispositions.json`
rather than re-alarming on every PR. That suppression must never be invisible to
whoever reads the pack, so the section renders each entry — its gate, match, reason,
`accepted_by`, and expiry — split **active** vs **expired**. An **absent** ledger
means *nothing accepted*: reported as `present: false`, never a gap. An **expired**
entry is listed *and* raises a gap (its finding is already re-alarming through the
gate, and `disposition-lint` fails CI on it). An **unreadable** ledger is a gap — the
pack cannot tell "nothing accepted" from "the register is broken", and never guesses.
The ledger is discovered by walking up from the plan dir; `--dispositions FILE`
overrides.

Run it **only on explicit human request** (the second consented write; default
output is stdout). The dated `evidence-pack/<date>/` convention is **never
overwritten** — one pack per day per plan, so a release's evidence is frozen at cut
time — and `--out` **refuses** a target that would land on a source it reads (the
plan root or `specs/`) — exit 1. Every section is **populated or gap-listed** (an
absent source lands in `gaps[]`, never a silent zero), and a **broken guard chain
fails loudly inside the pack** (the `guard_decisions.verify` field), it is not
hidden. `--merge-verdict` points at the CI verdict for a per-merge pack; omit it
when none exists. `/ce-ship-release` generates the per-release pack as a stage step.

The pack is **evidence COMPILATION, not attestation and not a conformity
assessment** — it gathers and hashes what the pipeline recorded and renders no
compliance judgment (its own `honest_limitations` field says so). Its sections map
to EU AI Act Art 11/12/18 record-keeping and technical-documentation vocabulary and
to SLSA provenance vocabulary — see `docs/ENTERPRISE-HARDENING.md`
§ *Regulatory Mapping — EU AI Act* for the article-by-article control map. A human
or external process reads the pack; the framework compiles evidence, it does not
sign for the organization.

## Escalation

Recurring review dismissals route to human-owned `review-policy.md`; repeated
planning drift routes to `/ce-plan-audit` or `/ce-plan`; persistent verification or
review hotspots route to `/ce-debug`, `/ce-verify`, or `/ce-review` depending on the
signal. This skill reports trends and optional exports only.

## Honest Limitations

- **Descriptive, not evaluative.** Signals over the model's own outputs, not ground truth. A low `manual:judgment` rate isn't "good"; it's a number to interpret.
- **As complete as the stream.** Metrics emission is best-effort and never gates a run, so a run that crashed mid-stage may be under-counted. Missing data reads as "no data", never a silent zero.
- **Estimates are estimates.** Token / duration figures are `chars/4`-class approximations the producers label as such — never billing-grade.
- **Read-only by design.** Writes nothing — *except* the consented, human-requested **audit export** (a new dated JSON file that mutates no source artifact); if you want a durable retro, copy the output yourself. Observability must never become a second source of truth over the artifacts.
- **A window only reaches the stream, and only by the day.** `--since` / `--until` filter the dated `.metrics.jsonl` events and nothing else: testability, evidence freshness, per-feature review state, complexity drift, and the patch lane are **current on-disk state**, reported as-of-now under any window (the export's `windowing.as_of_now_blocks` names them). `complexity_drift.retries` stays **lifetime** even in a windowed run — joining a windowed retry count to a lifetime task count would make drift *shrink* as the window narrows. The stream's `ts` carries no time, so bounds are inclusive and day-granular: a sprint boundary falling mid-day is unrepresentable, and two adjacent windows sharing an endpoint both count that day. A line with a missing or malformed `ts` is excluded from the window, **counted** under `window.stream_lines.undated`, and reported in `gaps[]` — never dropped silently.
- **An audience reorders; it never derives.** `standup` / `sprint-review` / `handoff` change what the report leads with, from the identical Stage-1 JSON. No audience introduces a ratio, a cost, a velocity, or an ROI figure — the artifacts carry no such field, and a retro that invents one has stopped being evidence.
- **The evidence pack is never windowed.** `evidence-pack.py` invokes this export with no window, by design: a release/compliance record must be the full stream, not a sprint's slice.
