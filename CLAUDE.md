# vg-coding plugins

A Claude Code marketplace with the `core-engineering` and `product-discovery`
plugins. Each plugin's skills are the source of truth and the public
slash-invocation surface; plugin-shipped custom agents wrap selected skills.

## Repository Structure

```
├── plugins/
│   ├── core-engineering/            #   the primary plugin — skills, agents, hooks
│   │   ├── .claude-plugin/plugin.json
│   │   ├── agents/                  #   Claude Code custom agents → skills (spec-author, spec-impl)
│   │   ├── skills/<name>/           #   the workflows; SKILL.md + optional stage files + scripts/
│   │   ├── hooks/                   #   lifecycle safety, egress, integrity, and model-attestation hooks
│   │   ├── model-policy.json        #   machine-readable model-tier policy (check.py §7)
│   │   ├── merge-policy.json        #   machine-readable merge bar (check.py §14 · scripts/gate_runner.py)
│   │   └── fork-manifest.json       #   forked gate-script registry (check.py §5 · fork_sync.py)
│   └── product-discovery/           #   companion plugin — the upstream idea/market trio (ce-idea-scout · ce-idea-score · ce-market-scan)
│       ├── .claude-plugin/plugin.json
│       ├── skills/<name>/           #   ce-idea-scout · ce-idea-score (score-lint.py) · ce-market-scan (scan-lint.py)
│       └── model-policy.json        #   its own model-tier policy (check.py §7 demands one per skill plugin)
├── .claude-plugin/
│   └── marketplace.json             #   marketplace manifest — registers core-engineering + product-discovery
├── action/
│   ├── merge-bar/                   #   composite GitHub Action — the merge bar as a 3-line adoption (action.yml + README; self-tested by .github/workflows/action-selftest.yml)
│   └── test-integrity/              #   standalone test-weakening guard action
├── templates/
│   └── adopter-ci/                  # checksum-pinned copy-in PR-gate workflows (GitHub, GitLab, Azure ports)
├── tests/                           # offline unittest suite for the repo + gate scripts (CI-run)
├── evals/                           # behavior eval scenarios, fixture repos, golden artifacts
└── scripts/                         # check.py, corpus_lint.py, authoring_check.py, fork_sync.py, portability_check.py, product_layer_check.py, supply_chain_check.py, gate_runner.py, eval_check.py, eval_run.py, version_bump.py, print-pin-block.sh, print_pin_block.py, gen_popular_packages.py
```

Run `python3 scripts/check.py` before committing. It parses manifests, verifies
skill and leaf-agent frontmatter, checks every registered forked script against
its canonical copy, validates model and merge policies, and then runs the corpus,
authoring, product-layer, and supply-chain validators once. The skill-corpus
validators walk every marketplace plugin, not only `core-engineering`.

Run `python3 scripts/eval_check.py` for the behavior-eval catalog and coverage
ratchet, `python3 scripts/eval_run.py --profile smoke` for the dry-run invocation
path, and `python3 scripts/portability_check.py` for the stdlib-only gate/hook
guarantee. Skills live under `plugins/<plugin>/skills/`; edit the owning
canonical copy directly. For a script registered in
`plugins/core-engineering/fork-manifest.json`, edit the canonical and regenerate
copies with `python3 scripts/fork_sync.py --write`.

`check.py` also self-installs a `pre-commit` hook (`git config core.hooksPath .githooks` — no Husky/Node). The hook patch-bumps any plugin's `.claude-plugin/plugin.json` `version` so a branch ends up exactly one patch ahead of `main` (bumped once, not per commit — a plugin's `version` gates update delivery to already-installed users). The `version-bump` GitHub Action enforces the same rule on PRs as a backstop. Bypass a single commit with `git commit --no-verify`; bump logic lives in `scripts/version_bump.py`.

## Key Files

- `docs/README.md`: **Documentation index** — routes users, evaluators,
  operators, and contributors to the smallest relevant guide.
- `docs/HOW-IT-WORKS.md`: **Canonical framework overview** — the one-spine/two-genres shape, the artifact model, every skill, and the recurring disciplines. Start here to understand the system; keep it current (see *Documentation* below).
- `docs/GETTING-STARTED.md`: **First-session guide** — install, verify, first useful commands, safety boundaries, and troubleshooting.
- `docs/WORKFLOW-RECIPES.md`: **Operating recipes** — common end-to-end paths with expected artifacts, done states, and stop/escalation rules.
- `docs/USAGE-MATRIX.md`: **Quick router** — maps common developer intents to the right `ce-*` skill; owns the canonical Default Routes list.
- `docs/ENTERPRISE-HARDENING.md`: **Enterprise control map** — maps OWASP / SLSA / OpenSSF / SBOM vocabulary to concrete repo controls, enforcement surfaces, evidence artifacts, and gaps.
- `docs/BENCHMARKS.md` · `docs/EXAMPLES.md` · `docs/COMPARISON.md` · `docs/TEAM-ROLLOUT.md`: **Adopter evidence layer** — live-eval status + configured budget caps, captured historical outputs with explicit provenance limits, date-stamped positioning vs. alternatives, and the team pilot guide. Guarded by `product_layer_check.py`; refresh BENCHMARKS/EXAMPLES when a new live eval batch runs, and re-verify COMPARISON's claims when its "as of" date ages.
- `docs/contributing/HITL-GATE-STANDARD.md`: **HITL Gate Standard** — the five rules every interactive human-in-the-loop gate conforms to (decidable-in-the-dialog, evidence-first attestations, isolated material calls, triaged dense gates, located & labeled) + the shared consequence-glossary. A contributor discipline; see *HITL Gate Standard* below.
- `docs/contributing/SKILL-AUTHORING.md`: **Skill authoring standard** — one skeleton, the staged-disclosure threshold, the HITL heading vocabulary, shared-rule invariant cores, the router-cluster registry, and the forked-gate rules. The mechanical half is enforced by `scripts/authoring_check.py` (run by `check.py`); the rest is contributor discipline.
- `.claude-plugin/marketplace.json`: Marketplace manifest — registers both plugins with their source paths.
- `plugins/*/.claude-plugin/plugin.json`: Per-plugin metadata — name, description, version.
- `plugins/core-engineering/agents/*.md`: Claude Code custom agents shipped by the plugin; each is a leaf wrapper around one or more skills.
- `plugins/*/skills/*/SKILL.md`: The workflows; the heavy ones load stage files on demand (progressive disclosure).
- `.claude/settings.local.json`, `*.local.md`: User-specific configuration (gitignored).

## Development Workflow

1. Edit markdown files directly - changes take effect immediately
2. Test skills with their plugin-qualified syntax, e.g. `/core-engineering:ce-init`, `/core-engineering:ce-plan`, `/core-engineering:ce-spec`, `/core-engineering:ce-implement`, `/core-engineering:ce-probe-infra`.
3. Model-invocable skills may be selected automatically when their trigger
   conditions match; all skills remain directly callable, including the six
   safety-sensitive workflows that require explicit invocation.

## Naming — skill names are the public API

There are no command dispatchers. A plugin skill directory
`plugins/<plugin>/skills/<name>/SKILL.md` creates the public invocation
`/<plugin>:<name>`, and its `name:` frontmatter must match the directory. In this
marketplace, public skill names must start with `ce-` to avoid collisions with
other skills.
`check.py` enforces this, and the same name must appear in:

- the owning plugin's `model-policy.json`
- the README skill catalog
- `evals/scenarios.json` when the skill has an eval
- the router-cluster registry in `scripts/authoring_check.py`, when the new
  skill's intent overlaps an existing sibling (mutual contrastive clauses are
  lint-enforced)

Keep skill identifiers short and user-facing: `ce-plan`, `ce-spec`,
`ce-implement`, `ce-probe-sec`, `ce-ship-release`. Claude Code adds the owning
plugin namespace at invocation time, such as `/core-engineering:ce-plan`. Do not reintroduce a
`commands/` dispatcher layer for new workflows.

## Documentation — keep `docs/HOW-IT-WORKS.md` current

`docs/HOW-IT-WORKS.md` is the canonical, human-facing overview of the whole
framework — the one-spine/two-genres shape, the artifact model, every skill,
and the recurring disciplines. It is the first thing a new contributor (or a
future Claude) should read to understand the system.

**Rule:** when a change is significant enough to alter the framework's shape or
behavior, update `docs/HOW-IT-WORKS.md` in the **same** change. Significant means any of:

- adding, removing, or renaming a **skill** (update the counts, the §1
  diagram, and the relevant §3 / §5 entry);
- changing a **gate, lock, escalation path, or other named discipline**;
- changing an **artifact path or the `docs/` layout** (§2);
- changing **how layers hand off** (e.g. the brief→plan seam).

Mechanical refactors, typo fixes, and version bumps do **not** require a doc update.
When unsure, update it — a stale overview is worse than a verbose one. `check.py`
does not enforce this; it is a contributor discipline — and a standing instruction to
Claude: after any qualifying change, refresh `docs/HOW-IT-WORKS.md` before finishing.

## HITL Gate Standard — keep every decision decidable in place

Every interactive Human-in-the-Loop gate across the `/core-engineering:ce-brief → /core-engineering:ce-plan → /core-engineering:ce-spec →
/core-engineering:ce-implement` spine conforms to the five rules in
`docs/contributing/HITL-GATE-STANDARD.md`:
**decidable-in-the-dialog** (each option carries its consequence), **evidence-first
attestations** (never confirm a model-derived call — a threat-id, a data-class, an
additive-vs-breaking — without its basis + cost-if-wrong rendered), **isolate material
attestations** (own prompt, never a buried bullet), **triage dense gates** (lead with
*what needs your decision*, gloss vocabulary from the shared glossary), and **locate &
label** (`Gate N of M`). `/core-engineering:ce-spec`'s resolve-unknowns and `/core-engineering:ce-implement`'s manual-verdict
gates are the exemplars; the densest application is `/core-engineering:ce-plan`'s Reachability gate (§6.6).

Three rules are now machine-backed by `authoring_check.py`: A9 keeps the shared
consequence-glossary's two copies in sync (term parity + per-term anchor phrases in the
contributor mirror *and* the runtime Legend), and A10 requires any skill with `[material`
gates to state the R5 gate-locator discipline (a literal `Gate N of M` instruction).
A13 rejects decision tables with more than four options and prose that assigns more
than four questions to one `AskUserQuestion` round. The remaining rules (R1–R4
substance, including whether the named decision owner actually has enough evidence)
stay contributor discipline, and a standing
instruction to Claude: when you add or edit any gate that asks the human to choose,
make it conform, and **reuse the shared consequence-glossary verbatim** so a term never
gets two different glosses.

## Model-tier policy (guidance, not auto-behavior)

Every stage of the SDLC skills runs on the user's loaded model unless the user
explicitly opts a stage down. This is a **reviewable policy, never automatic
routing**. The policy is encoded machine-readably in each plugin's
`model-policy.json` and validated by `check.py` in both directions: every skill
must have an entry, and a skill may carry binding
`model:`/`effort:` frontmatter **only** if its entry says
`down_routable: true` — so changing who may route down is always a reviewable
policy-file diff, never a quiet frontmatter edit.

- **Judgment, gate, escalation, and evidence-gathering stages always use the
  strongest available model** — decomposition scoring, EARS authoring, the
  design-review judgment, the six-lens review, Scope-Lock reconciliation, and any
  on-disk gate's judgment. Never route these down.
- **`/core-engineering:ce-ship-backlog` is the one safe cheap-tier candidate** — a mechanical,
  human-reviewed transform that feeds nothing downstream (see its skill note).
- **`/core-engineering:ce-plan` Stage 1.2 (codebase profile) stays on the strong model** — it is an
  interpretive evidence-builder feeding `shared-context.md`, not a mechanical
  transform.
- **auto-build never couples model tier to its token budget.** Any future
  per-subagent model hint must be a consented Stage-0 choice, default to the
  strong model for spec / implement / review / reconciliation /
  decomposition, be recorded in the ledger, and surface at the end-review as an
  accepted degradation — never silent.
