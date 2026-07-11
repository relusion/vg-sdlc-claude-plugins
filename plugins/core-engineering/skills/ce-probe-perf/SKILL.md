---
name: ce-probe-perf
description: |
  Profile a running target's performance — latency, throughput, resource use, hotspots — observe tier by default, load/soak behind opt-in. Refuses production; the only tool that can prove a numeric NFR breach (records, doesn't block).
  Triggers: performance-test/profile/load-test/measure latency or throughput. For vulnerabilities use /ce-probe-sec.
argument-hint: "[target (url | command | path)] [--type http|cli|browser|library] [--against <spec-id>]"
allowed-tools: Read, Write, Glob, Grep, Bash, AskUserQuestion, Skill
disable-model-invocation: true
---

# Probe Perf

**Invocation input:** Target to profile (and optional --type / --against): $ARGUMENTS


Measure how a running target *performs* — and where it spends its time. This is the
**dynamic** performance tool: it exercises a live instance or binary. For *static*,
code-level review of inefficiency, use `/ce-review`'s **Performance
lens** (the boundary below).

Sister to `/ce-probe-sec` and `/ce-ux-audit`: same evidence-bound finding *discipline*
(every finding cited, triaged, escalated — though each tool's finding fields and
evidence-state vocabulary differ), same consent-first discipline, same escalate-up chain. **Not a benchmark suite or an SLA
certification** — a first cut that surfaces measurements and hotspots as leads;
mature load generators and profilers do the deep work where installed.

## Boundary — dynamic vs static

- **`/ce-probe-perf`** (this tool) — *dynamic*: measures a running target under real load.
- **`/ce-review` Performance lens** — *static*: reads code for structural inefficiency
  (algorithmic complexity, N+1, unbounded loads) without running it.

They mirror security's split (`/ce-probe-sec` dynamic · `/ce-review` Security lens static).
A static lens *suspects*; `/ce-probe-perf` *quantifies* and finds what reading can't (real
latency under concurrency). Only `/ce-probe-perf` can prove a numeric NFR breach — and it
**records** it, it does not block. Don't duplicate — route accordingly.

## Architecture — a same-shape sister, surfaces inline

Like `/ce-probe-sec` and `/ce-ux-audit`, `/ce-probe-perf` is a **separate** discovery skill that shares
the consent / evidence / triage **shape**, not a shared spine. Its per-surface
measurement detail is thin enough to stay **inline** here (unlike `/ce-probe-sec`, which
externalized two heavy probe taxonomies into modules). If a surface grows its own
gate or a heavy probe set, split it into a `measures-<surface>.md` module the way
`/ce-probe-sec` does — until then, inline is the recorded choice.

## Sister tools

| | `/ce-ux-audit` | `/ce-probe-sec` | `/ce-probe-perf` |
|---|---|---|---|
| Mode | Verification (journey-walk) **or** Discovery (adversarial UX, plan-free) | Discovery (security, dynamic) | Discovery (performance, dynamic) |
| Targets | Web | Web / API / CLI | Web / API / CLI / browser / library |
| Production | (deployed) journey-walk · Discouraged plan-free | **Refused** (remote) | **Refused** (load can degrade it) |
| Local exec | — | **sandboxed** (possibly-hostile binary) | own / trusted code, throwaway workdir (see Limitations) |
| Output | `docs/plans/<slug>/ux-findings.md` **or** `docs/ux-audits/<date>-<slug>.md` | `docs/sec-probes/<date>-<slug>.md` | `docs/perf-profiles/<date>-<slug>.md` |

## Surfaces

| Surface | Detect by | Measures | Orchestrates (where installed) |
|---|---|---|---|
| **http** | URL (or `--type http`) | latency p50/p95/p99, throughput (RPS), error rate under concurrency | `wrk` · `hey` · `k6` · `autocannon` · `ab` (curl-class single-request timing is a permitted primitive) |
| **cli** | a command/binary (or `--type cli`) | wall-clock + variance per invocation, startup cost | `hyperfine` · `/usr/bin/time` |
| **browser** | URL + `--type browser` | page-load, Core Web Vitals, main-thread time | Lighthouse · the browser MCP |
| **library** | a path/module + `--type library` | per-operation time + allocations via a scratch microbenchmark | language bench harness · a profiler |

A language **profiler** (`py-spy` · `perf` · `pprof` · `clinic` · async-profiler)
attributes time to hotspots where installed. *(Serverless / cold-start profiling is a
deliberate v1 non-goal — see Honest Limitations.)*

## Runtime Inputs

- **Target (required):** a URL, a command/binary, or a path/module. If absent, ask.
- **`--type`** (optional): `http | cli | browser | library`. Overrides detection.
- **`--against <spec-id>`** (optional): a spec whose performance acceptance criteria (latency / throughput / limit, with real numbers) the run measures against — turning raw numbers into a criterion-backed signal.
- **Tier opt-ins (required):** Observe on by default · Load one opt-in · Soak one opt-in, each bounded by the consent gate's intensity.
- **Scope (optional):** a route, subcommand, operation, or page; default is the reachable surface.

## Preconditions

- The surface is determined and the target reachable.
- The **Consent Gate** has passed (environment + authorization, + intensity for Load/Soak).
- Load / profiling tools are detected; the workflow offers only what's installed and reports degraded tiers (a missing load generator caps the run at Observe — recorded, never silently skipped).

## Execution Contract

*Gate locator (HITL R5):* print `Gate N of M — <name>` at every interactive gate; compute M from the gates that actually fire this run, never a hardcoded constant.

0. **Session write lease (structural, first act).** `python3 "${CLAUDE_SKILL_DIR}/scripts/write-lease.py" --set --skill ce-probe-perf --allow 'docs/perf-profiles/**'` — only the dated profile + evidence are writable, and the write guard now enforces that. Last act: `python3 "${CLAUDE_SKILL_DIR}/scripts/write-lease.py" --restore-baseline`. A denied write mid-session means this contract and the action disagree — reconcile; never edit or delete the lease to proceed.
1. **Consent first.** No measurement before the Consent Gate passes (environment + authorization). Production / shared targets are refused; intensity is bounded to what the human authorizes. No re-prompting mid-run.
2. **Non-destructive load only.** Generate read-path / idempotent load by default; write/mutating load only on an explicit per-target opt-in against a target the human confirms is disposable. Never load-test a target that mutates real data without that opt-in.
3. **Three-State Evidence.** Each finding is `measured | observed | inferred` — `measured` (reproducible under the run), `observed` (a single-sample / single-stream reading), `inferred` (attributed by a sampling profiler / heuristic — correlational, not proof of cause). No conflation. This is **profiling-evidence strength**, this skill's own axis; on the shared evidence scale defined by the Skill Authoring Standard: `measured`→demonstrated, `observed`→read, `inferred`→inferred.
4. **Findings, Not Verdicts.** Report measurements and hotspots; the human triages. Never "the app is fast / slow" — and a number without a target (`--against`) is a *measurement*, not a pass/fail.
5. **Orchestrate, Don't Reinvent.** Installed load generators and profilers do the deep work; this skill drives them and synthesizes. (Curl-class single-request timing is a permitted primitive, not reinvention.)
6. **Read-only on the project; bounded scratch.** Write only the dated report and `evidence/`. A library-surface scratch microbenchmark is written **only** under `docs/perf-profiles/evidence/<date>-<slug>/` (or a throwaway temp dir) — **never** into the project source tree, and **never** committed. Never patch, commit, or deploy — a fix is an escalation.
7. **Output:** `docs/perf-profiles/<date>-<slug>.md` + `docs/perf-profiles/evidence/<date>-<slug>/`.

## Consent Gate — Environment, Authorization & Intensity  [material]

Asked via `AskUserQuestion`; stops on "not sure"; consent is at the gate, not negotiable mid-run.

**Q1 — Environment:** What is this target?

| Answer | Result |
|---|---|
| local / dev | Continue (subject to Q2) |
| staging (dedicated, disposable) | Continue **only** with the Q2 authorization attestation — the env label alone is not enough |
| production / shared / I'm not sure | **Stop.** A load test can degrade a shared service — profile a local or dedicated instance instead. |

**Q2 — Authorization (every tier, including Observe):** Are you authorized to load / measure this target right now, and — for Load / Soak — is it dedicated to you for the run window, not shared with teammates? → no / unsure = **Stop.**

**Q3 — Intensity & blast radius (Load / Soak only):** the max concurrency, request rate, and duration you authorize; that the target and its dependencies (DBs, third parties) can absorb it; and that the load path is non-mutating (or the target is disposable). Observe needs only Q1 + Q2.

## Cross-cutting rule — Findings, Not Verdicts

A finding is `{surface, tier, state, severity, target, metric, value, baseline?, against?, hotspot?, observation, evidence, suggested escalation}`. The human triages:

| Triage | Result |
|---|---|
| **Escalate** | `/ce-implement <id>` (code is inefficient; spec exists) · `/ce-spec <id>` — add or amend the feature's performance acceptance criteria, **after** a measured number shows a risky path with no target (or `/ce-plan` if no owning feature exists — a cross-feature NFR) · `/ce-review` (confirm the static cause of a measured hotspot) · "review" (plan-less) |
| **Defer** | Record as a known limitation |
| **Dismiss** | Noise / environmental; drop |

## Cross-cutting rule — Stuck or Ambiguous → Ask, Don't Guess

If a run needs a credential, a target seems to be shared after all, load produces errors that look like damage, or a result is ambiguous → **stop and ask** one short question. Record in *Open Questions / Stops*.

## Human-in-the-Loop

- **Stage 0 (material)** — the Consent Gate (Q1 + Q2 always; Q3 for Load / Soak) + tier opt-ins.
- **Mid-run (Stuck rule)** — ambiguity or a suspected shared target.
- **Stage 3 (tiered)** — triage (see Stage 3.2).

---

## Stage 0 — Surface, Consent, Setup

1. Resolve the target (argument / conversation / ask) and the surface (detect / `--type` / ask).
2. Run the **Consent Gate** (Q1 + Q2; Q3 if Load / Soak opted in). Stop on any refusal.
3. Detect load generators + profilers for the surface; report availability and degraded tiers. For **http** with no installed load generator **and** no browser MCP, Observe degrades to *reachability + status only, no latency* (recorded) — curl-class single-request timing is used where the primitive exists.
4. If `--against <spec-id>`, load the spec's performance acceptance criteria as the targets to measure against.
5. **Tier opt-ins** (material): Observe auto-on; Load / Soak each opt-in with a one-line intensity description. Resolve scope and `<slug>`. *Proceed / Abort.*

## Stage 1 — Observe (passive — always on)

Measure the target under **light, single-stream** use: a handful of requests / invocations, a baseline latency and resource snapshot (CPU, memory, where available). Findings are state `observed`. This establishes the baseline; it is not load.

## Stage 2 — Load / Soak (opted-in) + Hotspot Attribution

- **Load** (opt-in): drive the authorized concurrency / rate; capture the latency curve (p50/p95/p99), throughput ceiling, error rate under saturation. Findings `measured`.
- **Soak** (opt-in): sustain authorized load over the authorized duration; watch for drift — growing latency, leaking memory, degrading throughput.
- **Library** measurement: write the scratch microbenchmark **under `docs/perf-profiles/evidence/<date>-<slug>/`** (or a temp dir), exercise the built library, capture per-operation timings — never write into the source tree.
- **Hotspot attribution:** where a profiler is installed, sample under load and attribute time to functions / queries; these findings are `inferred` (correlational). Capture evidence (raw tool output, flame graph, latency histogram) to `docs/perf-profiles/evidence/<date>-<slug>/F-N.*`.

Walk all opted-in tiers to completion — no early-exit on the first slow path.

## Stage 3 — Triage and Report

### 3.1 Categorize and Score  *(severity is objective — a number needs a target)*

- **High:** a **measured** breach of an `--against` performance criterion; or an unambiguous failure of the run itself under authorized non-mutating load (the target crashes / errors out) — labelled `observed`, not a verdict.
- **Medium:** a strong hotspot attributable to one function / query; a p95/p99 well outside the baseline with a likely cause; a latency cliff / error storm / soak leak **with no `--against` criterion to grade it** — reported with the observation "no criterion to grade against; confirm whether this breaches an intended target (a missing target is itself a `/ce-spec` escalation)."
- **Low:** minor observed overhead; environmental variance.

A latency cliff or leak **without** an `--against` criterion is never High — it is a measurement awaiting a target, not a proven breach.

### 3.2 Triage  [tiered]
Batched by severity × tier with evidence. Measured-high / ambiguous → material; clear-cut observations → batch approve-with-veto.

### 3.3 Write the Report
Write `docs/perf-profiles/<date>-<slug>.md`. Dated snapshot — never overwrite a prior run.

---

## Report Template — `docs/perf-profiles/<date>-<slug>.md`

````markdown
# Performance Profile — <date> · <slug>

> Target: <url-or-command>   ·   Surface: http | cli | browser | library
> Consent: env <local|dev|staging> · authorized <yes>   ·   Intensity: <concurrency / rate / duration | observe-only>
> Tiers run: observe [+ load] [+ soak]
> Tools used: <list>   ·   Measured against: <spec-id criteria | none>
> Findings: <T>  (<H> high · <M> medium · <L> low)
> States: <Me> measured · <Ob> observed · <In> inferred

## Baseline (Observe)
| Metric | Value |
|---|---|
| latency p50 / p95 / p99 | … |
| throughput (single stream) | … |
| resource (CPU / mem) | … |

## Findings

### F-N — <short title>  [severity]
- **Surface / Tier / State:** <e.g. http · load · measured>
- **Metric:** <p99 latency | RPS ceiling | hotspot | memory growth>  ·  **Value:** <number>
- **Baseline:** <observe-tier value | n/a>   ·   **Against:** <spec-id AC-x criterion | none>
- **Hotspot:** <function / query @ file:line>  *(inferred — from the profiler)*
- **Observation:** <what the numbers show>
- **Evidence:** `evidence/<date>-<slug>/F-N.{txt,json,svg,png}`
- **Suggested action:** <skill or "review">
- **Triage:** Escalate / Defer / Dismiss — <date>

## Open Questions / Stops
| # | When | Question | Answer | Effect |
|---|---|---|---|---|

## Triaged
| ID | Surface | Tier | State | Sev | Triage | Action | Date |
|---|---|---|---|---|---|---|---|
````

---

## Closing

```text
Performance Profile complete: <slug> — <date>  (<surface>)
Consent:   env <env> · authorized · intensity <concurrency/rate/duration | observe-only>
Tiers run: observe [+ load] [+ soak]
Findings:  <total> (<high> high, <med> medium, <low> low)
States:    <Me> measured · <Ob> observed · <In> inferred
Report:    docs/perf-profiles/<date>-<slug>.md
```

Name any escalation skill. A measured hotspot is a lead — confirm its static
cause via `/ce-review` before optimizing, so a fix targets the real bottleneck.

## Escalation

Measured criteria breaches route to `/ce-spec` when the target is missing or wrong,
to `/ce-review` when static cause confirmation is needed, and to `/ce-implement`
when an owned feature needs a fix. Cross-feature performance obligations route to
`/ce-plan`. This skill records measurements; it does not optimize.

## Honest Limitations

- **This environment, this load — not production scale.** Numbers measured on a dev /
  staging box under a synthetic load do not predict production behavior; they surface
  relative hotspots and obvious cliffs, not an SLA.
- **Not a benchmark suite, and no regression gating.** A first cut; rigorous,
  statistically-controlled benchmarking is a separate exercise, and runs are dated
  snapshots — never compared across runs, so this does not gate perf regressions.
- **No auto-optimization.** It measures and escalates; it never edits code to make a
  number better — a fix is an `/ce-implement` (or `/ce-spec`) escalation.
- **Runs your own, trusted code.** Unlike `/ce-probe-sec` (which sandboxes a
  possibly-hostile binary), `/ce-probe-perf` measures code you own and trust and only bounds
  its scratch to a throwaway dir — it does not security-sandbox local execution. Don't
  point it at code you don't trust.
- **No serverless / cold-start surface (v1).** Cold-start exists only in the deployed
  cloud env and a local invoke hits real backing services or needs a deploy (refused);
  measuring it needs a function-specific gate this version doesn't ship.
- **Hotspots are correlational.** Sampling profilers attribute time, they don't prove
  cause — an `inferred` finding is a lead, confirmed by `/ce-review` + a fix that moves
  the number.
- **Orchestrates installed tools.** No load generator → Observe-only (http with no
  client and no MCP → reachability + status, no latency); depth is the tooling's, and
  false negatives are expected.
- **A number without a target is just a number.** Without `--against` perf criteria,
  the run reports measurements, not pass/fail — and the missing criterion is itself a
  `/ce-spec` escalation.
- **Snapshots, not history.** Dated reports; runs never overwrite prior runs.
