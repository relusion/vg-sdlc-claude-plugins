# Infra-Review module — Dockerfile (`Dockerfile` / `Containerfile` / `*.Dockerfile`)

Loaded by `ce-probe-infra`'s spine at Stage 0 when `formats_detected.dockerfile > 0`. The
**spine** owns the lenses, evidence model, redaction rule, triage, and report; **this module**
owns the Dockerfile detect signature, scanner orchestration, and the per-check taxonomy. Read
it by its `${CLAUDE_SKILL_DIR}` absolute path, never by bare name.

## Detect by
Filename: `Dockerfile`, `Containerfile`, `Dockerfile.<suffix>` (e.g. `Dockerfile.prod`), or
`*.Dockerfile`. Name-only — no content sniff. Dockerfiles are line-oriented, which is why this
family carries the floor's only HARD check.

## Orchestrate (prefer where installed) → fallback
| Scanner | Adds | Invoke offline | Fallback when absent |
|---|---|---|---|
| **hadolint** | best-practice lint (DL rule ids) — pinned tags, apt-cache cleanup, `USER`, layer hygiene | `hadolint -f json <file>` | floor checks below |
| **trivy config** | Dockerfile misconfig + secret rules | `trivy config --offline-scan <file>` (**no** `--update`) | floor checks below |

Record any missing scanner as **degraded coverage** — never a silent skip.

## Floor checks (`infra-lint.py`, line-oriented)
| Check | Catches | Lens | State | Ceiling |
|---|---|---|---|---|
| **`X-COPY`** | a `COPY`/`ADD` of a **local** source path that exists under **neither** the Dockerfile dir nor the scope root — a broken build reference | cross-manifest | **scanner-confirmed** | **High (HARD FAIL → exit 1)** |
| `P-LATEST` | a `FROM` pinned `:latest` or left untagged (excludes `scratch` and `AS`-stage aliases) | config-hygiene | manifest-read | Medium |
| `P-NO-USER` | no `USER` directive anywhere — the container runs as root | workload-hardening | manifest-read | Medium |
| `P-PLAINTEXT-SECRET` | a credential in `ENV` / `ARG` (redacted) | secrets-exposure | manifest-read | Medium |

`X-COPY` exemptions (so a fact stays a fact): a `--from=<stage>` build-stage ref, a `://` URL,
a glob (`*?[]{}`), and `.`/empty are all skipped. A source found under **either** the Dockerfile
directory **or** the scope root clears the check — the build context is an honest static unknown,
so the check fires only when the source exists in **no** reasonable location.

## Model-judged (the lens does it)
- **Secrets via build args** that persist into layers, `ADD` of a remote URL (supply-chain),
  running services as root past the entrypoint, missing `HEALTHCHECK`, and over-broad `RUN`
  privilege — `manifest-read` Medium leads where the floor/hadolint do not already cover them.

## Module limitations (layered on the spine's)
- **Build-context caveat:** `COPY` paths resolve against the `docker build` **context**, which
  is a build-time argument invisible to a static read. `X-COPY` mitigates this by clearing a
  source found under either the Dockerfile dir or the scope root, and firing only when it
  exists nowhere — but a context rooted somewhere exotic could still produce a false positive,
  which the human dismisses at triage. This is the one place the floor asserts HARD; it is
  deliberately narrow for exactly this reason.
- No image is built or pulled (no registry/network access) — base-image freshness/EOL beyond a
  literal `:latest`/untagged tag is `inferred` and routed to a scanner, not proven here.
