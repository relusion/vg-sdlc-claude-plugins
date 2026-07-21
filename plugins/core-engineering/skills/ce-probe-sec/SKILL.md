---
name: ce-probe-sec
description: |
  Security-probe a running target — web/API apps or CLI binaries — passive recon by default; smell-test and active-exploit tiers behind explicit opt-in. Twice-attested consent; refuses production; sandboxes binaries; findings, not verdicts.
  Triggers: security-test/sec-scan/probe a running app for vulnerabilities. Never production. For performance use /core-engineering:ce-probe-perf.
argument-hint: "[target-url-or-binary] [--type http|cli]"
allowed-tools: Read, Write, Glob, Grep, Bash, AskUserQuestion, Skill
disable-model-invocation: true
---

# Probe Sec

**Invocation input:** Target (URL for web/API, or a binary/command for CLI): $ARGUMENTS


Probe a running target for security issues. This is the **dynamic** security tool
— it exercises a live instance or binary. For *static*, code-level review of
pending changes, use `/core-engineering:ce-review`'s Security lens (see the boundary below).

Sister to `/core-engineering:ce-ux-audit`: same evidence-bound finding *discipline* (every finding cited,
triaged, escalated — though each tool's finding fields and evidence-state vocabulary
differ), same triage discipline, same escalate-up chain. **Not a pentest** — a first cut that surfaces leads for a
human security professional; mature scanners do the deep work where installed.

## Architecture — spine + per-type modules

This skill (`SKILL.md`) is the **spine**: it owns the workflow arc, the consent
gates, the evidence model, triage, and the report. The **per-type probe content**
lives in modules loaded on demand at Stage 0:

| Target type | Detect by | Load module | Consent gate |
|---|---|---|---|
| Web / API | argument is a URL (or `--type http`) | `${CLAUDE_SKILL_DIR}/probes-http.md` | Gate A — Remote-Target Attestation |
| CLI / console | argument is a binary/command (or `--type cli`) | `${CLAUDE_SKILL_DIR}/probes-cli.md` | Gate B — Local-Execution Sandbox |
| (ambiguous) | — | ask the human | — |

Load exactly one module per run. Adding a type later = a new `${CLAUDE_SKILL_DIR}/probes-<type>.md` +
one row here; the spine never changes.

**The probe modules named above are bundled in this skill's own directory.** Read the
selected one at `${CLAUDE_SKILL_DIR}/probes-<type>.md` — `${CLAUDE_SKILL_DIR}` is the
environment variable that resolves to this skill's directory regardless of the current
working directory. Resolve it once if needed (`ls "${CLAUDE_SKILL_DIR}"`) and read the
module by its resulting absolute path; **never load a companion module by bare name** —
in an installed plugin the working directory is the user's project, so a bare name finds
nothing and triggers a filesystem search.

## Sister tools

| | `/core-engineering:ce-ux-audit` | `/core-engineering:ce-probe-sec` |
|---|---|---|
| Mode | Verification (journey-walk) **or** Discovery (adversarial, plan-free) | Discovery (security, dynamic) |
| Targets | Web | Web / API / CLI |
| Production allowed | (deployed) journey-walk · Discouraged plan-free | **Refused** (remote) · **sandbox only** (local) |
| Output | `docs/plans/<slug>/ux-findings.md` **or** `docs/ux-audits/<date>-<slug>.md` | `docs/sec-probes/<date>-<slug>.md` |

## Boundary — dynamic vs static

- **`/core-engineering:ce-probe-sec`** (this tool) — *dynamic*: probes a running target (web / API / CLI).
- **`/core-engineering:ce-review` Security lens** — *static*: reviews source / pending changes for vulnerabilities.

Anything that's "analyze the code for vulns" belongs to `/core-engineering:ce-review`. This
tool exercises a live target. Don't duplicate; route accordingly.

## Runtime Inputs

- **Target (required):** a URL (web/API) or a binary/command (CLI). If absent, ask.
- **`--type`** (optional): `http` | `cli`. Overrides detection.
- **Tier opt-ins (required):** `recon` on by default · `smell`-test one opt-in · `active` **per category** opt-in. The loaded module defines each tier's probes. (The `recon` tier yields `passive`-state findings — tier and state are distinct; see Three-State Evidence.)
- **Credentials / sandbox details (conditional):** per the module's consent gate.
- **Scope (optional):** a path, route, subcommand, or area; default is the reachable surface.

## Preconditions (generic — the module adds its own)

- The target type is determined and its module loaded.
- The module's consent gate has passed (Gate A or Gate B).
- The module's required scanners/tools are detected; the workflow offers only what's installed and reports degraded tiers.

## Execution Contract

0. **Session write lease (structural, first act).** `python3 "${CLAUDE_SKILL_DIR}/scripts/write-lease.py" --set --skill ce-probe-sec --allow 'docs/sec-probes/**'` — only the dated report + evidence are writable, and the write guard now enforces that. Last act: `python3 "${CLAUDE_SKILL_DIR}/scripts/write-lease.py" --restore-baseline`. A denied write mid-session means this contract and the action disagree — reconcile; never edit or delete the lease to proceed.
1. **Consent first.** No probing before the module's consent gate passes. Remote targets refuse production; local targets run sandboxed only. No re-prompting mid-run.
2. **Non-Destructive PoC Only.** Even active exploits use non-destructive proof: timing, read-only disclosure, controlled crash, reverted DOM mutation. **Never** destroy data, delete files, mutate roles, or make uncontrolled network calls. Classes confirmable only destructively are reported **suspected, not attempted**.
3. **Three-State Evidence.** Each finding is `confirmed | suspected | passive` (a finding-**state** — `passive` is a state here, **distinct from the always-on `recon` tier** that produces such findings). On the shared evidence scale defined by the Skill Authoring Standard: `confirmed`→demonstrated, `passive`→read, `suspected`→inferred. No conflation.
4. **Findings, Not Verdicts.** The agent reports; the human triages. Never "the app is secure."
5. **Stuck or Ambiguous → Ask, Don't Guess.** Especially probes bordering on "is this allowed."
6. **Orchestrate, Don't Reinvent.** Mature scanners/fuzzers do the deep work where installed.
7. **Read-only on code and existing artifacts.** Write only the dated report and `evidence/`.
8. **Output:** `docs/sec-probes/<date>-<slug>.md` + `docs/sec-probes/evidence/<date>-<slug>/`.
   Resolve a same-day collision before writing: use `<date>-<slug>` first, then
   `<date>-<slug>-2`, `-3`, and so on for report and evidence together; never
   overwrite or split one run across keys.

## Consent Gates

The module declares which gate it uses. Both are asked via `AskUserQuestion`, both
stop on "not sure," and **consent is at the gate, not negotiable mid-run.**

### Gate A — Remote-Target Attestation  *(web / API)*

**Q1 — Environment:** What environment is this target?

| Answer | Result |
|---|---|
| local / dev / staging | Continue |
| production | **Stop.** |
| I'm not sure | **Stop.** |

**Q2 — Authorization:** Do you have authorization to probe-sec this target right now? → no / unsure = **stop**.

### Gate B — Local-Execution Sandbox  *(CLI / console)*

Running a binary with adversarial input on the local machine is dangerous. Three questions:

**Q1 — Binary identity:** What exact binary/command am I probing? Confirm it is the build you intend — not a system tool, not a production-deployed copy.

**Q2 — Sandbox:** May I run it sandboxed? Confirm: throwaway working dir · scrubbed env (no real secrets) · controlled or no network · **never as root** · resource-limited (CPU, memory, processes, time).

- **Preferred:** a container (docker/podman) — no network, read-only mounts except a throwaway workdir, non-root, resource-limited.
- **Fallback:** a constrained subprocess — `ulimit`, fresh temp CWD, scrubbed env, `timeout`. **Weaker isolation — the human must acknowledge it explicitly.**

**Q3 — Authorization:** Do you have authorization to probe-sec this binary? → no / unsure = **stop**.

## Cross-cutting rule — Findings, Not Verdicts

A finding is `{category, tier, state, severity, target, payload?, observation, evidence, cwe?, suggested escalation}`. The agent never declares pass/fail. The human triages:

| Triage | Result |
|---|---|
| **Escalate** | `/core-engineering:ce-implement <id>` (spec exists) · `/core-engineering:ce-spec <id>` (spec gap) · `/core-engineering:ce-plan` (structural) · "review" (plan-less) |
| **Defer** | Record as a known limitation |
| **Dismiss** | False positive; drop |

## Cross-cutting rule — Stuck or Ambiguous → Ask, Don't Guess

Mid-run, if the workflow needs a credential or sandbox detail it lacks, is unsure a
payload is appropriate, hits a persistent unexpected response, or finds an
ambiguous result → **stop and ask one short, direct question.** Resume on the
answer; record in *Open Questions / Stops*.

## Human-in-the-Loop

- **Stage 0 (material)** — the module's consent gate (Gate A: ×2 · Gate B: ×3) + tier opt-ins (active per-category).
- **Mid-run (Stuck rule)** — ambiguity during probing.
- **Stage 3 (tiered)** — triage (see Stage 3.2).

---

## Stage 0 — Type, Consent, Setup

1. Resolve the target (argument / conversation / ask).
2. **Determine the target type** per the architecture table (URL → http · binary/command → cli · `--type` overrides · ask if ambiguous). **Load `probes-<type>.md`.**
3. Run the module's **consent gate** (Gate A or Gate B). Stop on any refusal.
4. Detect the module's scanners/tools; report availability and degraded tiers (browser MCP for http per its table; sandbox mechanism for cli).
5. **Tier opt-ins** (material): `recon` auto-on; `smell` one opt-in; `active` per-category, each with a one-line description of what fires and what it cannot damage.
6. Resolve the module's tier dependencies — http: browser-MCP-dependent categories (skip / smell-only / abort); cli: sandbox mechanism (container vs acknowledged fallback).
7. Confirm credentials / scope. **If the target is a planned app with a `docs/plans/<slug>/threat-model.md`, read it to focus the probe** — prioritize active-tier opt-ins toward the documented trust boundaries and `sensitive`-data flows, and let it inform Stage 3.1 severity (an exploit reaching a documented sensitive surface scores higher). It **focuses, never replaces** the module's probe taxonomy — an *undocumented* surface is still probed (a gap the threat model missed is itself a finding). Record in the Stage 0 summary that scope was narrowed by the threat model — **never a silent narrowing**. Resolve `<slug>`. *Proceed / Abort.*

## Stage 1 — Reconnaissance (`recon` tier — always on)

Run the **`recon` probe set from the loaded module**. Its findings are evidence-state
`passive` — facts about the target, not exploits. (The `recon` tier is *how* the
finding was obtained; `passive` is *what kind of evidence* it is.)

## Stage 2 — Tiered Probing (smell + opted-in active)

Run the **smell and active probe taxonomy from the loaded module**, honoring each
tier's opt-in and the module's tool/MCP/sandbox dependencies. Capture evidence per
finding to `docs/sec-probes/evidence/<date>-<slug>/F-N.*`. **Walk all opted-in
probes to completion** — no early-exit on a single confirmation.

## Stage 3 — Triage and Report  *(shared — identical regardless of type)*

### 3.1 Categorize and Score

- **High:** confirmed active exploits; missing critical controls (no CSP/HSTS on HTTPS; CLI shelling unsanitized input or running as root); confirmed privilege/disclosure.
- **Medium:** suspected exploits with strong evidence, weak control values, smell-tier findings with response/behaviour deltas.
- **Low:** minor `passive`-state findings, low-impact disclosure.

### 3.2 Triage  [tiered]

Batched by severity × tier with evidence. Confirmed-high / ambiguous → material; clear-cut `passive`-state findings → batch approve-with-veto.

### 3.3 Write the Report

Write `docs/sec-probes/<date>-<slug>.md`. Dated snapshot — never overwrite a prior run.

---

## Report Template — `docs/sec-probes/<date>-<slug>.md`

````markdown
# Security Probe — <date> · <slug>

> Target: <url-or-binary>   ·   Type: http | cli   ·   Consent: Gate A (env) | Gate B (sandbox)
> Tiers run: recon [+ smell] [+ active: <categories>]
> Scanners / tools used: <list>
> Findings: <T>  (<H> high · <M> medium · <L> low)
> States: <C> confirmed · <S> suspected · <P> passive

## Surface Reconnaissance

(per-type recon summary)

## Findings

### F-N — <short title>  [severity]

- **Category / Tier / State:** <e.g. SQLi · active · confirmed>
- **CWE:** CWE-NNN (when applicable)
- **Target:** <url / arg / command>
- **Payload:** <what was sent>  *(omit for `passive`-state findings)*
- **Observation:** <what was observed>
- **Evidence:** `evidence/<date>-<slug>/F-N.{req,resp,png,txt}`
- **Suggested action:** <skill or "review">
- **Triage:** Escalate / Defer / Dismiss — <date>

## Open Questions / Stops

| # | When | Question asked | Human's answer | Effect on run |
|---|---|---|---|---|

## Triaged

| ID | Cat | Tier | State | Sev | Triage | Action | Date |
|---|---|---|---|---|---|---|---|
````

---

## Closing

```text
Sec Probe complete: <slug> — <date>  (<type>)
Consent:   Gate A (env: <env>) | Gate B (sandbox: <container | fallback>)
Tiers run: recon [+ smell] [+ active: <cats>]
Findings:  <total> (<high> high, <med> medium, <low> low)
States:    <C> confirmed · <S> suspected · <P> passive
Report:    docs/sec-probes/<date>-<slug>.md
```

Name any escalation skill. **Never commit; never patch; never deploy.** Confirmed
findings should reach a human security professional before remediation begins.

## Escalation

Static code follow-up routes to `/core-engineering:ce-review`'s Security lens; runtime confirmation
stays in `/core-engineering:ce-probe-sec`; infrastructure exposure routes to `/core-engineering:ce-probe-infra`; and
owned feature remediation routes to `/core-engineering:ce-spec` or `/core-engineering:ce-implement` through the plan's
normal locks. This skill records findings and consent, not fixes.

## Honest Limitations (shared)

- **Not a pentest.** A first cut; leads for a human professional, not a clean bill of health.
- **Application-layer only.** Network, infra, supply-chain (SCA) out of scope.
- **False negatives expected.** Dedicated scanners/fuzzers find what this misses.
- **Three-state evidence.** `suspected` ≠ `confirmed`; never conflate.
- **Per-type limits** are listed in the loaded module.
- **Snapshots, not history.** Dated reports; runs never overwrite prior runs.
