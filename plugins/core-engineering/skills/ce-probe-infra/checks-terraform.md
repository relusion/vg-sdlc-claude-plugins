# Infra-Review module — Terraform (`.tf` / `.tf.json`)

Loaded by `ce-probe-infra`'s spine at Stage 0 when `formats_detected.terraform > 0`. The
**spine** owns the lenses, evidence model, redaction rule, triage, and report; **this
module** owns Terraform's detect signature, the scanner orchestration, and the per-check
taxonomy. Read it by its `${CLAUDE_SKILL_DIR}` absolute path, never by bare name.

## Detect by
Extension: `*.tf` (HCL — hand-scanned) and `*.tf.json` (the JSON variant — `json`-parseable).
`infra-lint.py` classifies these by extension alone (no content sniff needed).

## Orchestrate (prefer where installed) → fallback
| Scanner | Adds | Invoke offline | Fallback when absent |
|---|---|---|---|
| **tfsec** | provider-aware misconfig rules (open SGs, unencrypted resources, public ACLs) with rule ids + severities | `tfsec --no-color --format json <dir>` (no remote checks) | floor pattern subset, Medium ceiling |
| **checkov** | broad cross-resource policy pack (CKV ids), incl. Terraform | `checkov -d <dir> -o json --compact` (no `--download-external-modules`) | floor pattern subset |
| **trivy config** | unified IaC misconfig db | `trivy config --offline-scan <dir>` (**no** `--update`) | floor pattern subset |

Record any missing scanner as **degraded coverage** in the report — never a silent skip.

## Floor checks (`infra-lint.py`, parser-free, `manifest-read` / Medium unless noted)
| Check | Catches | Lens | State | Ceiling |
|---|---|---|---|---|
| `P-WILDCARD-IAM` | `"Action"/"Resource"/"Principal": "*"`, `actions/resources = ["*"]` | least-privilege | manifest-read | Medium |
| `P-OPEN-INGRESS` | a `0.0.0.0/0` or `::/0` CIDR | network-exposure | manifest-read | Medium |
| `P-UNENCRYPTED` | `encrypted = false` / `storage_encrypted = false` | config-hygiene | manifest-read | Medium |
| `P-PLAINTEXT-SECRET` | a credential signature in a value (redacted) | secrets-exposure | manifest-read | Medium |

## Model-judged (no scanner / not on the floor — the lens does it, never a binary FAIL)
- **`X-VAR` (advisory):** a `var.<x>` / `module.<m>.<out>` reference with no matching
  `variable`/`module` definition in the swept set. **Needs HCL interpolation parsing the
  floor refuses to fake — so it is advisory, never a HARD FAIL**, and **advisory-only** when
  `overlay_context` is set (a value injected by a wrapper the static read cannot see).
- **Least-privilege *reasoning*:** is a broad grant load-bearing, or careless? Read the
  resource's usage before calling a wildcard a finding.
- **Missing encryption / public exposure** beyond the literal flags (e.g. an S3 bucket with
  no `server_side_encryption_configuration`, a public `acl`), and **state-backend** secrets
  (an unencrypted remote backend) — `inferred` where the real exposure depends on the
  deployed account; route those to `/core-engineering:ce-probe-sec`.

## Module limitations (layered on the spine's)
- HCL is hand-scanned, not parsed: `for_each`, `dynamic` blocks, locals, and computed
  interpolations are invisible to the floor — the orchestrated scanner and the model cover
  them. `.tf.json` is JSON-parseable but rare; treated the same as HCL for the pattern set.
- No `terraform plan` is ever run (that would reach providers and require credentials) — this
  is pure static manifest reading.
