# Security Policy

## Supported versions

Security fixes target the current `main` branch for both plugins, the composite
actions, and the adopter templates. When a repository release is published,
only the latest release is supported. Older plugin versions and releases do
not receive backports; update through Claude Code's plugin update flow.

## Reporting a vulnerability

Use **GitHub private vulnerability reporting** on this repository
(Security → Report a vulnerability). Please include the plugin version, the
skill or script involved, and a minimal reproduction. The maintainer aims to
acknowledge reports within seven days. If the private-reporting button is not
available, open an issue that asks for a private contact channel but contains
no vulnerability details. Please do not disclose exploitable findings in a
public issue before a fix ships.

## What is in scope

- **Gate and hook bypasses beyond the documented limits** — e.g. a way to make
  `git-guard.py` miss a push/PR/protected-branch commit, or `env-guard.py`
  miss a vector it claims to cover. (The *documented* non-coverage in
  [`plugins/core-engineering/hooks/README.md`](./plugins/core-engineering/hooks/README.md)
  — env-var expansion, interpreter one-liners, the Managed-Agent surface — is
  a known limit, not a vulnerability.)
- **Prompt-injection paths** that make a read-only skill write, a probe
  exfiltrate secrets, or any skill act outside its stated execution contract
  when processing hostile repository content.
- **Vulnerabilities in the shipped scripts themselves** (hooks, gate scripts,
  the deploy script) — e.g. command injection through crafted file paths.
- **Supply-chain issues** in this repo's CI (unpinned actions, checksum
  bypass).

## What the framework does and does not guarantee

The hooks are **guardrails, not a sandbox**: they raise the cost of the
highest-stakes mistakes on the Claude Code surface, and their honest
non-coverage is documented rather than implied away. Skills run with your
model authority and your filesystem permissions; artifacts are staged for
human review, and you own what enters shared history and production. Managed-
agent deployments load **no hooks** — host-side controls are the boundary
there (see the per-cookbook READMEs).
