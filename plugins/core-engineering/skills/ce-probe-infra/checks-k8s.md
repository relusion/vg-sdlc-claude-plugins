# Infra-Review module — Kubernetes (`.yaml` / `.yml` with `apiVersion` + `kind`)

Loaded by `ce-probe-infra`'s spine at Stage 0 when `formats_detected.k8s > 0`. The **spine**
owns the lenses, evidence model, redaction rule, triage, and report; **this module** owns the
Kubernetes detect signature, scanner orchestration, and the per-check taxonomy. Read it by its
`${CLAUDE_SKILL_DIR}` absolute path, never by bare name.

## Detect by
A `.yaml`/`.yml` file whose head has a top-level `apiVersion:` **and** `kind:` (content
sniff). Explicitly **excluded** (recorded as a coverage gap, not audited as k8s): a file under
a Helm `templates/` dir or containing `{{` (Helm template — `UNSUP:helm`), a `services:`-rooted
compose file (`UNSUP:compose`), and a CloudFormation template (`UNSUP:cloudformation`).
Multi-document files (`---`) are scanned line-wise by the floor.

## Orchestrate (prefer where installed) → fallback
| Scanner | Adds | Invoke offline | Fallback when absent |
|---|---|---|---|
| **kube-linter** | security/correctness lint — privileged, run-as-non-root, host namespaces, capabilities | `kube-linter lint <dir> --format json` | floor pattern subset, Medium ceiling |
| **kube-score** | object scoring — missing limits/requests, missing probes, PDB, image pull policy | `kube-score score --output-format json <files>` | model-judged (the floor does not prove block-scoped limits) |
| **checkov** | CKV policy pack for k8s | `checkov -d <dir> -o json --compact` | floor pattern subset |

Record any missing scanner as **degraded coverage** — never a silent skip.

## Floor checks (`infra-lint.py`, parser-free line scan, `manifest-read` / Medium)
| Check | Catches | Lens | State | Ceiling |
|---|---|---|---|---|
| `P-PRIVILEGED` | `privileged`/`hostNetwork`/`hostPID`/`hostIPC`/`allowPrivilegeEscalation` set to `true` | workload-hardening | manifest-read | Medium |
| `P-WILDCARD-IAM` | RBAC `verbs`/`resources`/`apiGroups: ["*"]` | least-privilege | manifest-read | Medium |
| `P-OPEN-INGRESS` | a `0.0.0.0/0` / `::/0` CIDR (NetworkPolicy, LB source ranges) | network-exposure | manifest-read | Medium |
| `P-LATEST` | a container `image:` pinned `:latest` or untagged | config-hygiene | manifest-read | Medium |
| `P-PLAINTEXT-SECRET` | a credential in env / `stringData`, or an inline `Secret.data` base64 value (redacted) | secrets-exposure | manifest-read | Medium |

## Model-judged (no scanner / not on the floor — the lens does it, never a binary FAIL)
- **`X-REF` (advisory):** a workload mounting / referencing a `ConfigMap` / `Secret` /
  `ServiceAccount` name defined nowhere in the swept set. **Needs YAML block + multi-doc
  parsing the floor refuses to fake — advisory, never a HARD FAIL**, and **advisory-only**
  under `overlay_context` (a Kustomize base / Helm subchart whose overlay supplies the name).
- **Missing resource limits / probes** — needs container-block structure; route to
  `kube-score` where installed, else a `manifest-read` Medium lead.
- **Missing `NetworkPolicy`** (default-allow), `runAsNonRoot` absent, **`automountServiceAccountToken`**
  defaults, **Ingress without TLS**, and **`Service type: LoadBalancer/NodePort`** exposure —
  the last is often `inferred` (real reachability depends on the cluster/cloud); route those to
  `/core-engineering:ce-probe-sec`.

## Module limitations (layered on the spine's)
- The floor reads YAML line-wise, not structurally: it cannot associate a setting with its
  enclosing block/kind reliably, so anything block-scoped (limits, probes, `Secret.data`
  attribution) is best-effort or model/scanner territory, never HARD.
- CRDs and operator-specific kinds are read generically (apiVersion+kind), not schema-validated.
- A Helm-templated k8s manifest is **not** rendered (no `helm template` is run) — it is recorded
  as a Helm coverage gap until the Helm module ships.
