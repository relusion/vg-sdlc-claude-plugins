# Contributing

The shipped hooks and gates are markdown, JSON, and stdlib-only Python, with no
build step. Maintainer validation uses two small Python development
dependencies. This page is for people changing the framework itself; if you
just want to *use* the plugins, start at
[docs/GETTING-STARTED.md](./docs/GETTING-STARTED.md).

## Prerequisites

- `git` and `python3` (3.10+).
- Python `pyyaml` for the umbrella validator and `jsonschema` for the complete
  test suite (`python3 -m pip install pyyaml jsonschema`). The gates shipped to
  adopters remain standard-library-only.
- Claude Code CLI — only needed for `claude plugin validate --strict` and for
  executing live evals; all other checks run without it (that's the
  portability guarantee, proven by `scripts/portability_check.py`).
- `jq` — only if you work on the managed-agent deploy path.

## The validation battery

`python3 scripts/check.py` is the umbrella local gate (it also self-installs
the version-bump pre-commit hook). The full battery, as CI runs it:

```bash
python3 scripts/check.py --no-install-hooks
python3 scripts/managed_agent_check.py
python3 scripts/product_layer_check.py
python3 scripts/docs_drift.py
python3 scripts/supply_chain_check.py
python3 scripts/eval_check.py
python3 scripts/eval_run.py --profile smoke --out-dir /tmp/vg-eval-smoke-dry-run
python3 scripts/eval_run.py --profile benchmark --out-dir /tmp/vg-eval-benchmark-dry-run
python3 scripts/metrics_report.py --json
python3 scripts/enterprise_evidence.py --json
python3 scripts/portability_check.py
python3 -m unittest discover -s tests -v
bash scripts/test-cookbooks.sh
claude plugin validate --strict .claude-plugin/marketplace.json
claude plugin validate --strict plugins/core-engineering
claude plugin validate --strict plugins/product-discovery
```

The separate commands exist because they make failures easier to localize
while editing; `check.py` already invokes the corpus, authoring, supply-chain,
managed-agent, and product-layer checks itself.

## The standards you are expected to follow

- **[CLAUDE.md](./CLAUDE.md)** — repository ground rules: skill naming
  (`ce-` prefix, name = directory), the model-tier policy, and the
  doc-currency rule (a change that alters the framework's shape updates
  `docs/HOW-IT-WORKS.md` in the same change).
- **[Skill Authoring Standard](./docs/contributing/SKILL-AUTHORING.md)** — the one skeleton,
  the 400-line staged-disclosure cap, the HITL heading vocabulary, shared-rule
  invariant cores, router-cluster registry, and the forked-gate rules
  (`fork-manifest.json`; edit the canonical, run
  `python3 scripts/fork_sync.py --write`, never hand-edit a copy).
- **[HITL Gate Standard](./docs/contributing/HITL-GATE-STANDARD.md)** — the five
  rules every interactive gate conforms to when you add or edit one.

## Versioning and changelog

The pre-commit hook patch-bumps the `.claude-plugin/plugin.json` for each plugin
changed on a branch, so its version ends up ahead of `main` (plugin versions
gate update delivery to already-installed users); `version_bump.py --check`
enforces this on PRs. A deliberate minor/major bump set by hand is respected —
the hook only bumps when the version is not already ahead. Add a line to
`CHANGELOG.md` under `## Unreleased` for any user-visible plugin change.

## Adding things

- **New skill** → `plugins/<plugin>/skills/<name>/SKILL.md`; the same name must
  appear in the owning plugin's `model-policy.json`, the README catalog, the
  usage matrix and recipes, `evals/scenarios.json` when it has an eval, and the
  router-cluster registry in `scripts/authoring_check.py` when its intent
  overlaps a sibling. `check.py` enforces most of this; the naming rules live
  in CLAUDE.md.
- **New plugin agent** → a leaf custom agent at the owning plugin's
  `agents/<name>.md` path (no nested `Task`).
- **New managed-agent cookbook** → `managed-agent-cookbooks/<slug>/`
  (`agent.yaml`, `system.md`, `README.md`, `steering-examples.json`).
- **New eval** → scenario in `evals/scenarios.json` + fixture. Generated run
  outputs under `evals/runs/` are gitignored and stay local: promote distilled
  lessons into deterministic output/artifact checks, and minimized artifacts
  into `evals/golden/` — never commit raw run outputs.

## Licensing of contributions (DCO)

Unless explicitly stated otherwise, contributions intentionally submitted for
inclusion are licensed under Apache-2.0 as described in section 5 of
[LICENSE](./LICENSE). Sign off every commit (`git commit -s`, which appends a
`Signed-off-by:` trailer) under the
[Developer Certificate of Origin 1.1](https://developercertificate.org/) to
certify that you have the right to submit the change. Contributions and
sign-offs are retained in public git history, so use identity information you
are comfortable publishing.

No Contributor License Agreement (CLA) is currently required. You retain
copyright in your contribution and provide the grants set out in Apache-2.0;
the DCO sign-off does not transfer copyright to the maintainer. See
[COMMERCIAL.md](./COMMERCIAL.md) for the project's licensing and commercial
policy.

Maintainers verify DCO trailers during review; CI does not currently enforce
them automatically.

## Pull requests

Before opening one: run the battery above, update the changelog, and keep
`docs/HOW-IT-WORKS.md` + `README.md` current with any shape change (skills,
gates, controls, product routes, artifact paths). CI re-runs the same gates —
a PR that fails them will not merge.
