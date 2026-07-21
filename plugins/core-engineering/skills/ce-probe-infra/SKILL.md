---
name: ce-probe-infra
description: |
  Statically audit Infrastructure-as-Code / Kubernetes / cloud manifests across a repo — least-privilege, workload hardening, secrets, exposure, hygiene, cross-manifest consistency. Orchestrates installed scanners (tfsec/checkov/kube-score/kube-linter/hadolint/trivy) and falls back to a stdlib infra-lint.py floor. Read-only on code; redacts secrets, never exfiltrates; findings, not verdicts.
  Triggers: audit/lint/review IaC, k8s, Helm, Dockerfile, compose, or cloud manifests for misconfig. Static & plan-free. For a live running target use /core-engineering:ce-probe-sec; for application-code review use /core-engineering:ce-review; for known-vulnerable dependency versions (SCA) use /core-engineering:ce-probe-deps.
argument-hint: "[path | scope (default: repo root)] [--format terraform|k8s|dockerfile] [--scope <subpath>]"
allowed-tools: Read, Write, Glob, Grep, Bash, AskUserQuestion, Skill
---

# Probe Infra

**Invocation input:** Scope to audit (a repo path, or empty for the whole repo): $ARGUMENTS


Audit Infrastructure-as-Code, Kubernetes, and cloud manifests **statically** — reading
the declarative resource graph on disk, not a running system. This is a **discovery**
tool: it runs on **any repo**, needs no plan or spec, writes a dated audit report, and
reports **findings, not verdicts** — every one cited to `file:line`, every actionable one
routed up the spine. **Not a CSPM and not a policy engine** — a first cut that surfaces
leads, with the deep work done by mature scanners where installed and a human owning the call.

Sister to `ce-probe-sec` and `ce-probe-perf`: same probe-family discipline — orchestrate
installed tools and degrade loudly, findings-not-verdicts, a tool-specific three-state
evidence axis, a dated never-overwritten report under `docs/`. The difference is the whole
point of the tool: those two exercise a **live** target; this one **parses files** and
runs nothing, so it inherits none of their consent/production machinery and instead carries
a **Secret-Redaction Rule**.

## Architecture — spine + per-format modules

This `SKILL.md` is the **spine**: it owns the workflow arc, the evidence model, the
redaction rule, the lenses, triage, the report, and Autonomous Mode. The **per-format
check content** lives in modules loaded on demand at Stage 0:

| Family (v1) | Detect by | Load module | Prefer scanner (where installed) |
|---|---|---|---|
| Terraform (`.tf` / `.tf.json`) | extension | `${CLAUDE_SKILL_DIR}/checks-terraform.md` | tfsec · checkov |
| Kubernetes (`.yaml`/`.yml` with `apiVersion`+`kind`) | content sniff | `${CLAUDE_SKILL_DIR}/checks-k8s.md` | kube-linter · kube-score · checkov |
| Dockerfile (`Dockerfile`/`Containerfile`/`*.Dockerfile`) | filename | `${CLAUDE_SKILL_DIR}/checks-dockerfile.md` | hadolint · trivy config |

Unlike `ce-probe-sec` (which loads **exactly one** module per run), this skill loads
**every module whose family is present** — a repo is commonly Terraform **and** Kubernetes
**and** Dockerfile at once, so the modules fan in. Adding Helm / docker-compose /
CloudFormation later = a new `${CLAUDE_SKILL_DIR}/checks-<family>.md` + one row here + one
classifier branch in `infra-lint.py`; **the spine never changes.**

**The modules and the lint script are bundled in this skill's own directory.** Read them at
`${CLAUDE_SKILL_DIR}/checks-<family>.md` and run the floor at
`${CLAUDE_SKILL_DIR}/scripts/infra-lint.py` — `${CLAUDE_SKILL_DIR}` resolves to this skill's
directory regardless of the working directory. Resolve it once if needed
(`ls "${CLAUDE_SKILL_DIR}"`) and use the resulting absolute path; **never load a companion
by bare name** — in an installed plugin the working directory is the user's project, so a
bare name finds nothing and triggers a filesystem search.

## Boundary — what this is NOT, and where else to route

- **vs `/core-engineering:ce-probe-sec` (dynamic security):** `probe:sec` probes a **live** target and its own
  scope note says *"Application-layer only. Network, infra, supply-chain (SCA) out of
  scope."* — that disclaimed region is exactly what `ce-probe-infra` fills, statically. A
  finding this tool can only **infer** statically (an exposed port that *may* be live-
  reachable, an IAM grant whose real blast radius depends on the deployed account) is routed
  **to `/core-engineering:ce-probe-sec`**, the dynamic confirmer. There is nothing live to refuse here, so this
  tool deliberately **drops the twice-attested consent gate** — inheriting it would be a
  category error — and adds the **Secret-Redaction Rule** instead.
- **vs `/core-engineering:ce-review` (application-code review):** `review` reasons about **application
  code** against a **spec**, is bounded to a feature's **diff + one hop**, refuses a
  whole-repo crawl, and requires an implemented feature to exist. `ce-probe-infra` inverts
  every one of those: it sweeps the **whole repo**, runs **plan-free**, and audits
  **infrastructure manifests**, not code.
- **vs `/core-engineering:ce-plan-audit` (plan validation):** `ce-plan-audit` lints **plan files** on disk;
  `ce-probe-infra` lints **infra manifests**. They share the *discipline* — a deterministic
  hard-referential lint + a model-judged layer + a severity ceiling that only lets a proven
  fact carry High — but read **disjoint artifacts**; neither reads the other's.

Anything "analyze the running system / cluster / reachable endpoint" → `/core-engineering:ce-probe-sec`.
Anything "review the application source" → `/core-engineering:ce-review`. This tool reads manifests.

## Runtime Inputs

- **Scope (optional):** a repo path or sub-path to audit. Default: the repo root. A
  `--scope <subpath>` narrows the sweep; `--format <family>` restricts to one family.
- **Mode (optional):** interactive (default) or **autonomous** (a gate caller — see
  *Autonomous Mode*).
- **Installed scanners (auto-detected):** tfsec, checkov, kube-score, kube-linter,
  hadolint, trivy config, cfn-lint — whichever are on `PATH`. None are required; their
  absence is a **recorded degradation**, never a silent skip.

## Preconditions

- The scope path exists and is readable (else `infra-lint.py` exits 2 and the run reports
  *could-not-run* loudly — never a clean green).
- At least one supported manifest is found — **zero is reported as a coverage result**
  (`status: no-files`), never a silent pass that reads as "infra is clean."

## Execution Contract

0. **Session write lease (structural, first act).** `python3 "${CLAUDE_SKILL_DIR}/scripts/write-lease.py" --set --skill ce-probe-infra --allow 'docs/infra-reviews/**'` — only the dated report + evidence are writable, and the write guard now enforces that. Last act: `python3 "${CLAUDE_SKILL_DIR}/scripts/write-lease.py" --restore-baseline`. A denied write mid-session means this contract and the action disagree — reconcile; never edit or delete the lease to proceed.
1. **Two layers, always.** Layer 1 is the deterministic floor: `infra-lint.py` (stdlib-only,
   offline) — it sweeps, classifies, and emits the HARD facts + parser-free pattern hits +
   the redacted-secret count + the detection table. Layer 2 is the **orchestrated scanners +
   the model's cross-manifest judgment** on top. Layer 1 **always runs**; Layer 2 enriches
   it. They never collapse into one self-attested pass.
2. **Orchestrate, Don't Reinvent.** Prefer an installed scanner (tfsec/checkov/kube-score/
   kube-linter/hadolint/trivy/cfn-lint) for each family present; the stdlib floor covers the
   structural + pattern subset when one is absent. **Always report which scanners ran and
   which were missing, and that coverage is degraded without them** — false negatives are
   expected on the floor alone.
3. **Scanners run offline.** Invoke every orchestrated scanner with its offline / no-update
   flag where one exists (e.g. `trivy config --offline-scan` and **no** `--update`;
   `checkov` without remote-graph calls). Scanner network egress is the **one sanctioned
   exception** to "never exfiltrates" and must be **suppressed by default** and surfaced if
   a scanner cannot run offline. `infra-lint.py` itself **never touches the network**.
4. **Three-State Evidence.** Each finding is `scanner-confirmed | manifest-read | inferred`
   (defined below). On the shared evidence scale defined by the Skill
   Authoring Standard:
   `scanner-confirmed`→demonstrated, `manifest-read`→read, `inferred`→inferred. No conflation.
5. **Findings, Not Verdicts.** The agent reports; the human triages. Never "the infra is
   secure / compliant." Only the floor's HARD lint (`X-*`) asserts a binary FAIL — because a
   broken reference is a fact.
6. **Read-only on code · Redact secrets · Never exfiltrate.** Write only the dated report and
   `evidence/`. Never edit, apply, `terraform plan/apply`, `kubectl apply`, build, push, or
   deploy a manifest (`Edit` is withheld). **Bash is used only to (a) invoke the named
   scanners offline and (b) run `infra-lint.py` — never to mutate repo files.** Any matched
   secret obeys the *Secret-Redaction Rule*.
7. **Stuck or Ambiguous → Ask, Don't Guess.**
8. **Output:** `docs/infra-reviews/<date>-<slug>.md` + `docs/infra-reviews/evidence/<date>-<slug>/`
   + a machine-readable `docs/infra-reviews/<date>-<slug>.summary.json`. Dated snapshot —
   never overwrite a prior run.
   Resolve a same-day collision before writing: use `<date>-<slug>` first, then
   `<date>-<slug>-2`, `-3`, and so on for the report, summary, and evidence
   together; never split one run across keys.

## Three-State Evidence

| State | Means | Severity ceiling |
|---|---|---|
| **`scanner-confirmed`** | an orchestrated scanner reported it with a rule id, **or** the floor's HARD lint (`X-*`) proved a referential/structural fact | **High allowed** |
| **`manifest-read`** | the model read the setting literally in the manifest and judged it (a `privileged: true`, a wildcard IAM action on the page) — no scanner corroborated it | **Medium** (the static read shares the model's blind spots; it cannot *prove* a defect) |
| **`inferred`** | the concern needs runtime / cross-account context the static read cannot establish (a LoadBalancer that *may* be internet-reachable) | **Medium**, and **routed to `/core-engineering:ce-probe-sec`** — only a live target confirms it |

## Secret-Redaction Rule  *(the static-distinction discipline that replaces a consent gate)*

`ce-probe-infra` may read secrets that have been committed into manifests. Because it acts on
**files, not a live system**, it needs no consent gate — but it carries a strict handling
rule instead:

- A matched credential is reported by **type + `file:line`** only, with the value replaced
  by **`[REDACTED]`** (fully opaque — the human opens the source to act; no entropy is
  written into an artifact that may itself be committed).
- The **raw value is never written** to the report, the `evidence/` dir, `summary.json`,
  stdout, or the network — including on the unparseable-file fallback path. `infra-lint.py`
  enforces this in code (it redacts before any value leaves the matching function); the
  agent must hold the same line for any scanner output it relays.
- Detection is **offline only** (entropy + signatures + best-effort base64 decode of k8s
  `Secret.data`). No registry/cloud confirmation is performed (the dep-guard **Network-
  Split** — live confirmation, if ever wanted, is an explicit agent step, never automatic).
- The floor's secret check is a **thin backstop** (current-file only, **not** git history,
  **not** gitleaks/trufflehog) — deep or historical secret-scanning is routed out, not
  promised here. Its dedicated home is the merge bar's `secrets-guard` advisory gate
  (`scripts/secrets-guard.py`), which scans the credential signatures a change ADDS
  between base and head and renders the merge-bar verdict; a whole-tree/historical sweep
  is the separate checksum-pinned gitleaks adapter (`.github/workflows/secret-scan.yml`).

## The lenses

The infra analog of `review`'s six lenses. Each module declares the per-family
checks; the spine owns the lens set and the both-sided over/under-build bias (flag an
over-grant **and** a missing-but-needed control only when the manifest itself evidences it).

1. **Least-privilege & access** — wildcard IAM/RBAC actions/resources/principals, world-open
   ingress (`0.0.0.0/0`), public ACLs, cluster-admin bindings.
2. **Workload hardening** — `privileged`, host namespaces, privilege-escalation, run-as-root /
   missing `runAsNonRoot`, added capabilities, missing `USER` in a Dockerfile.
3. **Secrets & data exposure** — plaintext/hardcoded credentials, inline k8s `Secret` data,
   missing encryption-at-rest. Drives the *Secret-Redaction Rule*.
4. **Network & exposure surface** — LoadBalancer/NodePort exposure, Ingress without TLS,
   absent NetworkPolicy (default-allow), wide egress, host-port bindings.
5. **Configuration hygiene & reliability** — `:latest`/untagged images, missing resource
   limits/requests, missing probes, disabled encryption flags.
6. **Cross-manifest consistency & referential integrity** — whole-repo coherence single-file
   scanners miss. **The floor proves only `X-COPY`** (a Dockerfile `COPY`/`ADD` of a local
   source that exists nowhere) as a HARD fact; the richer cross-references (a k8s workload
   mounting an undefined ConfigMap/Secret name `X-REF`, a Terraform `var.<x>`/module output
   with no definition `X-VAR`, a Helm `.Values.<x>` absent from `values.yaml` `X-VAL`) are
   **model-judged**, **never asserted as a binary FAIL by the script** — they need a real
   YAML/HCL/template parser the stdlib floor refuses to fake. **Under a detected Kustomize/
   Helm overlay** (the floor reports `overlay_context`), even the model treats `X-REF`/`X-VAL`
   as **advisory, not a fact** — a reference resolved by an overlay the static read cannot
   see is not a broken reference.

## Cross-cutting rule — Findings, Not Verdicts

A finding is `{lens, check, file:line, evidence-state, severity, observation, evidence,
suggested escalation}`. The agent never declares pass/fail. The human triages:

| Triage | Result |
|---|---|
| **Escalate** | `/core-engineering:ce-plan` (any manifest/IaC correction) · `/core-engineering:ce-decide` (a hard architectural fork) · `/core-engineering:ce-probe-sec` (an `inferred` exposure only a live target confirms) |
| **Defer** | Record as a known limitation |
| **Dismiss** | False positive; drop |

## Cross-cutting rule — Stuck or Ambiguous → Ask, Don't Guess

Mid-run, if a manifest is in an unsupported dialect you cannot safely classify, a scanner
emits something you cannot interpret, or scope is unclear → **stop and ask one short, direct
question.** Resume on the answer; record in *Open Questions / Stops*.

## Human-in-the-Loop — tiered

- **Stage 0 (material):** scope & format confirmation — the discovered format set + recorded
  coverage gaps, with `Proceed / Narrow scope / Abort`.
- **Mid-run (Stuck rule):** ambiguity during the sweep.
- **Stage 2 (tiered):** triage — `scanner-confirmed`-High and ambiguous findings are
  material (own prompt, evidence rendered first); clear-cut Low/`manifest-read` findings
  batch with approve-with-veto.

Each interactive gate conforms to the **HITL Gate Standard**:
decidable-in-the-dialog (every option states its consequence), evidence-first (a finding
renders its `file:line` + evidence-state **before** asking), isolated material calls, and
**`Gate N of M`** with **M computed after the sweep** — the normal path is `Gate 1 of 2`
(scope) then `Gate 2 of 2` (triage); a `no-files` run stops after `Gate 1 of 1`.

## Autonomous Mode

When invoked by an orchestrator or CI as a **pre-deploy gate** (parity with
`ce-plan-audit`): no interactive gates fire. Run `infra-lint.py --json` over the scope and
read `status`:

- **`status: "fail"`** (a HARD `X-*` referential break) → **the gate BLOCKS.** This is the
  only blocker — a provable fact.
- **`status: "pass"`** with `findings` → **advisory only.** Every model-judged / pattern /
  scanner finding informs the report and **never blocks** (it shares the model's blind spots
  or is a Medium-ceiling lead).
- **`status: "no-files"`** → not a pass and not a block; surfaced as *no manifests audited
  under scope* so a caller never mistakes an empty sweep for a clean one.
- **`status: "error"`** (exit 2) → could-not-run; the caller falls back to a scanner / manual
  review **loudly**, never treats it as a pass.

---

## Stage 0 — Sweep, Detect, Confirm Scope

1. Resolve the scope (argument / conversation / default repo root) and the `<slug>`.
2. **Run the floor:** `python3 "${CLAUDE_SKILL_DIR}/scripts/infra-lint.py" --root <repo> [--scope <subpath>] --json`.
   It returns the detection table (`formats_detected`), `unsupported_formats` (recognized
   but not v1 — a recorded coverage gap), `overlay_context`, `hard_failures`, the parser-free
   `findings`, `secrets_redacted_count`, and `files_scanned_capped` (true if the sweep hit
   `--max-files` and was truncated — **surface it as a coverage gap**, never a silent cap).
3. **Detect installed scanners** (`which tfsec checkov kube-score kube-linter hadolint trivy cfn-lint`); record which are present.
4. **Load the per-format module** for every family in `formats_detected`.
5. **Confirm scope [material — Gate 1 of M]:** present the discovered format counts, the
   recorded coverage gaps (unsupported families), the missing scanners (degraded coverage),
   and the overlay context. Options: **Proceed** (audit the detected families) / **Narrow
   scope** (re-sweep a sub-path) / **Abort** (write nothing). If `status: no-files`, report
   it and stop (`Gate 1 of 1`).

## Stage 1 — Lint, Orchestrate, Judge

For each detected family, in this order:

1. **Floor facts first** — carry forward `infra-lint.py`'s `hard_failures` (`X-COPY`, evidence
   `scanner-confirmed`) and pattern `findings` (`P-*`, evidence `manifest-read`, Medium ceiling).
2. **Orchestrate** — run each installed scanner for the family **offline** (per Contract §3),
   per the module's invocation notes; map each scanner result to a lens + `scanner-confirmed`
   state + its rule id. Record missing scanners as degraded coverage.
3. **Model judgment** — apply the module's lens taxonomy to read the manifests for what neither
   the floor nor a scanner caught: cross-manifest references (`X-REF`/`X-VAR`/`X-VAL` —
   advisory, never a FAIL; advisory-only under `overlay_context`), least-privilege *reasoning*
   (is a broad grant load-bearing?), and exposure that is `inferred` (route to `/core-engineering:ce-probe-sec`).
4. Capture evidence per finding to `docs/infra-reviews/evidence/<date>-<slug>/F-N.*` (redacted).

## Stage 2 — Triage and Report

### 2.1 Categorize & score
- **High:** only `scanner-confirmed` (a scanner rule id) or a HARD `X-*` lint fact.
- **Medium:** `manifest-read` model findings, pattern hits, `inferred` exposures.
- **Low:** minor hygiene, informational.

### 2.2 Triage [tiered] — per the Findings-Not-Verdicts table.

### 2.3 Write the report + `summary.json` (below). Dated; never overwrite.

---

## Report Template — `docs/infra-reviews/<date>-<slug>.md`

````markdown
# Infra Review — <date> · <slug>

> Scope: <path>   ·   Families: terraform=<n> k8s=<n> dockerfile=<n>
> Scanners used: <list>   ·   Missing (degraded): <list>
> Coverage gaps (unsupported v1): <helm/compose/cfn counts>   ·   Overlays: <kustomize/helm roots>
> Findings: <T>  (<H> high · <M> medium · <L> low)   ·   States: <SC> scanner-confirmed · <MR> manifest-read · <I> inferred
> Secrets redacted: <n> (values never emitted)

## Coverage & degradation
(what ran, what was missing, what families were recognized-but-unsupported — never a silent skip)

## Findings

### F-N — <short title>  [severity]
- **Lens / Check / State:** <e.g. least-privilege · P-WILDCARD-IAM · manifest-read>
- **Location:** `path:line`
- **Observation:** <what the manifest says> (secrets shown as `[REDACTED]`)
- **Evidence:** `evidence/<date>-<slug>/F-N.*` (scanner output / excerpt)
- **Suggested action:** `/core-engineering:ce-plan` | `/core-engineering:ce-decide` | `/core-engineering:ce-probe-sec` | review
- **Triage:** Escalate / Defer / Dismiss — <date>

## Open Questions / Stops
| # | When | Question | Answer | Effect |
|---|---|---|---|---|

## Triaged
| ID | Lens | Check | State | Sev | Triage | Action | Date |
|---|---|---|---|---|---|---|---|
````

### Companion — `docs/infra-reviews/<date>-<slug>.summary.json`

```json
{
  "slug": "<slug>", "date": "<date>", "scope": "<path>", "status": "pass|fail|no-files|error",
  "blocking_hard": 0,
  "formats_detected": {"terraform": 0, "k8s": 0, "dockerfile": 0},
  "scanners_used": [], "scanners_missing": [],
  "unsupported_formats": [], "overlay_context": [], "files_scanned_capped": false,
  "counts": {"high": 0, "medium": 0, "low": 0},
  "states": {"scanner-confirmed": 0, "manifest-read": 0, "inferred": 0},
  "secrets_redacted_count": 0
}
```
`blocking_hard` mirrors `infra-lint.py`'s HARD `X-*` count — the only field an Autonomous-Mode
caller treats as a blocker.

---

## Escalation

Findings **route, never act** — the same escalate-up chain as the rest of the toolset; never
patch/commit/apply/deploy a manifest.

- any manifest or IaC correction (a missing `USER`, a `:latest` pin, an over-broad
  security-group rule, cross-file RBAC, NetworkPolicies, or a secrets layer) →
  `/core-engineering:ce-plan` (then `/core-engineering:ce-implement` per feature); infrastructure findings are not
  pre-cleared for the express patch lane
- a missing-policy / no-contract gap (no encryption standard, no resource-limit baseline) → `/core-engineering:ce-plan` (or `/core-engineering:ce-brief` first if the requirement is unshaped)
- a hard architectural fork (managed-secrets vs sealed-secrets, VPC topology) → `/core-engineering:ce-decide` for an ADR
- an `inferred` exposure only a live target can confirm → `/core-engineering:ce-probe-sec`
- on a plan-free repo with no spine, route to **review** as the plan-less terminal (as `ce-probe-perf` / `ce-probe-sec` do).

## Honest Limitations

- **Static-only.** It reads manifests on disk — it cannot see RBAC as the API server resolves
  it, admission-controller mutation, runtime drift between manifest and cluster, or the real
  cloud account's subnet/route topology. An `inferred` exposure is a lead for `/core-engineering:ce-probe-sec`,
  never proof.
- **Not a CSPM, not a policy engine.** A first cut, not OPA/Sentinel/a posture-management
  product. A clean run means the manifests are well-formed and free of the patterns checked —
  **never** that the infra is secure or compliant.
- **Findings, not verdicts.** Only `infra-lint.py`'s `X-*` referential checks assert a binary
  FAIL, because a broken reference is a fact.
- **Floor is parser-free and conservative.** The stdlib floor proves only `X-COPY` as HARD and
  flags literal-token patterns; the real cross-reference checks (`X-REF`/`X-VAR`/`X-VAL`) are
  model-judged because the stdlib has no YAML/HCL/Go-template parser and a regex would
  manufacture false facts. False negatives are expected without the orchestrated scanners.
- **Secret detection is a thin offline backstop** — current-file only, not git history, **not**
  gitleaks/trufflehog. Deep/historical secret-scanning is routed out, not promised. Secrets are
  always **redacted** (`[REDACTED]` + `file:line`), never emitted.
- **Supported-format scope is bounded (v1: Terraform / Kubernetes / Dockerfile).** Helm /
  docker-compose / CloudFormation / Kustomize / Bicep / Pulumi are **recorded as coverage
  gaps**, never silently dropped — and arrive as a per-format module + one routing row.
- **Snapshots, not history.** Dated reports under `docs/infra-reviews/`; runs never overwrite.

## Closing

```text
Infra Review complete: <slug> — <date>
Scope:     <path>   ·   Families: terraform=<n> k8s=<n> dockerfile=<n>
Scanners:  used <list> · missing <list>   ·   Coverage gaps: <unsupported families>
Findings:  <total> (<high> high, <med> medium, <low> low)
States:    <SC> scanner-confirmed · <MR> manifest-read · <I> inferred
Secrets:   <n> redacted (values never emitted)
Report:    docs/infra-reviews/<date>-<slug>.md
```

Name any escalation skill. **Never patch; never apply; never deploy.** Confirmed findings
on a security boundary should reach a human owner before remediation begins.
