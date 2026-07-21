---
name: ce-init
description: |
  Bootstrap core-engineering in a repository: profile languages, package managers, build/test commands, CI, API/data/security surfaces, then write starter repo SDLC artifacts under docs/plans without overwriting human policy silently.
  Triggers: first-run setup, initialize this framework in a repo, generate vc-policy/review-policy/patterns/repo profile before planning.
argument-hint: "[--write] [--force] [--readiness]"
allowed-tools: Read, Write, Glob, Grep, Bash, AskUserQuestion, Skill
---

# Init

**Invocation input:** Bootstrap request and optional flags: $ARGUMENTS


Bootstrap the `core-engineering` framework in the current repository. This skill
turns a cold repo into a usable SDLC workspace by producing the starter artifacts
that later skills expect: repository profile, version-control policy, review
policy, and known-patterns seed.

This is a **setup skill**, not a planner. It detects facts, proposes defaults,
and writes starter policy only after surfacing what is inferred vs missing. It
does not decompose features, implement code, review code, modify production
files, install packages, or connect to trackers.

## Runtime Inputs

- **Repository root:** current working directory.
- **Optional `--write`:** write missing starter artifacts under `docs/plans/`.
  Without it, run as a dry profile and show the proposed outputs.
- **Optional `--force`:** overwrite existing starter artifacts only after an
  explicit human confirmation in this invocation. Existing human-authored policy
  is never replaced silently.
- **Optional `--readiness`:** add a deterministic adoption view that separates
  locally detectable workflow prerequisites from repository-host controls that
  require administrator verification. It executes no build, test, or CI job and
  is not a compliance attestation.
- **Optional context from the human:** team branching policy, protected branch,
  review bar, known flaky tests, forbidden paths, deployment constraints, and
  security-sensitive surfaces.

## Execution Contract

1. Run the deterministic scanner:

   ```bash
   python3 "${CLAUDE_SKILL_DIR}/scripts/repo-profile.py" --root . --json
   ```

   For an adoption check, include the local readiness view:

   ```bash
   python3 "${CLAUDE_SKILL_DIR}/scripts/repo-profile.py" --root . --readiness --json
   ```

   Use `--write` only when the human requested writes:

   ```bash
   python3 "${CLAUDE_SKILL_DIR}/scripts/repo-profile.py" --root . --write
   ```

2. Treat scanner output as a floor, not ground truth. Confirm uncertain or
   missing high-impact items before writing policy: test command, protected
   branch, release branch/profile, review calibration, generated-code paths,
   secret-bearing files, and deployment targets.
3. Write only setup artifacts:
   - `docs/plans/repo-profile.json`
   - `docs/plans/vc-policy.md`
   - `docs/plans/review-policy.md`
   - `docs/plans/patterns.md`
   - `.claude/ce-write-scope.json` (write-scope baseline; see Stage 2)
   - `.claude/ce-net-policy.json` (egress allowlist; see Stage 2)
4. Preserve human policy. If any target exists, read it and ask before
   overwriting. Prefer appendable notes or "left existing" over replacement.
5. End with a concise handoff: artifacts written or skipped, commands detected,
   unresolved setup questions, readiness blockers when requested, and next
   recommended skill.

## Workflow

### Stage 0 - Profile

Run `repo-profile.py` and inspect the generated JSON. Validate the important
signals by reading the files the scanner cites, especially:

- package manifests and build files;
- CI workflow files;
- `CODEOWNERS`, contribution docs, and existing agent instructions;
- route/API files, OpenAPI files, migrations, and infrastructure manifests;
- security-sensitive file names and environment examples.

### Stage 1 - Fill Gaps

Ask at most one grouped setup question if material facts are missing. Keep it
decidable:

- protected branch / release base;
- canonical test, lint, build, and start commands;
- review calibration (high bar, generated paths, nit policy);
- known recurring hazards or flaky suites;
- whether existing policy files may be created or updated.

If the human is absent, proceed with conservative defaults, label them
`inferred`, and do not overwrite existing policy.

### Stage 2 - Write Starter Artifacts

When writes are permitted, write missing artifacts under `docs/plans/`:

- `repo-profile.json`: machine-readable scan, git identity, commands, surfaces,
  and confidence notes.
- `vc-policy.md`: protected branch, release profile, commit/push boundaries,
  dirty-tree handling, and release handoff defaults.
- `review-policy.md`: review bar, generated/third-party skip paths, severity
  calibration, finding dismissal policy, and convergence rules.
- `patterns.md`: seeded known pitfalls, unverified assumptions, and repo hazards.
- `.claude/ce-write-scope.json`: the deny-only write-scope baseline — always-true
  denials only, so the write guard has a standing floor that never fights a
  writing skill. Seed exactly:

  ```json
  {
    "schema_version": 1,
    "enabled": true,
    "mode": "deny-only",
    "reason": "core-engineering baseline (seeded by ce-init): git internals and the write-scope lease are not agent-writable",
    "deny": [".git/**", ".claude/ce-write-scope.json"]
  }
  ```

  Write it via Bash (the guard denies Write/Edit on the lease file itself, by
  design). Never overwrite an existing policy file — a session lease or team
  policy may be active; report it and leave it. Ensure the target repo
  gitignores `.claude/ce-write-scope.json`,
  `.claude/ce-write-scope.session.json`, `.claude/ce-guard-log.jsonl`, and
  `.claude/ce-session-model.json` (append if missing — runtime guard/session
  state, not repo content).

- `.claude/ce-net-policy.json`: the egress checkpoint's allowlist — `net-guard.py`
  ASK-tiers outbound network to non-allowlisted hosts and confirms/denies upload
  flags (the send-side complement to `env-guard`'s read-side confinement). It is
  **inert until this file exists**, so seed a conservative starter only after
  asking the human which hosts the repo legitimately reaches (package registries,
  its own APIs). Seed exactly (tune `allow_hosts` to the repo):

  ```json
  {
    "schema_version": 1,
    "enabled": true,
    "allow_hosts": ["api.github.com", "*.githubusercontent.com"],
    "tiers": {"non_allowlisted": "ask", "upload": "ask"}
  }
  ```

  Loopback hosts always pass. Leave any existing policy untouched and report it.
  Gitignore `.claude/ce-net-policy.json` alongside the other runtime guard state.

Do not create a plan slug. `/core-engineering:ce-plan` owns feature/project plans.

### Stage 3 - Handoff

When `--readiness` was requested, lead with the two separate outcomes:

- `core_workflows`: whether starter artifacts and a test command are locally
  available;
- `team_quality_bar`: whether CI, CODEOWNERS, and a SHA-pinned merge-bar are
  locally configured, while preserving `host_enforcement:
  external-unverified` until an administrator confirms required checks and
  review/ruleset settings.

Do not turn a detected workflow file into a claim that it ran, passed, or is a
required check.

Recommend the next command:

- `/core-engineering:ce-ask` for immediate code questions;
- `/core-engineering:ce-impact` for a pasted work item;
- `/core-engineering:ce-brief` then `/core-engineering:ce-plan` for a new feature;
- `/core-engineering:ce-patch` for one small bounded change;
- `/core-engineering:ce-probe-infra` if infrastructure manifests were detected.

## Escalation

- If the repo has no discoverable build/test path, record a setup blocker and
  recommend adding one before `/core-engineering:ce-auto-build`.
- If protected branch or release policy is unknown, write a conservative
  `vc-policy.md` draft only with `inferred` labels, or skip writing if the human
  does not consent.
- If scanner output conflicts with user-provided policy, the human policy wins;
  record the scanner conflict in `patterns.md`.

## Honest Limitations

- Static scanning is heuristic. It detects common files and conventions; it does
  not prove the application can build, deploy, or pass tests.
- It cannot infer private release rules, compliance obligations, ownership, or
  production environments without human input.
- Readiness cannot query branch protection, rulesets, required reviewers, or
  required status checks; those remain `external-unverified` until a repository
  administrator supplies evidence.
- It writes starter policy, not a compliance attestation.
- It does not connect to issue trackers, CI providers, registries, cloud
  accounts, or observability systems.

## Closing

End with:

- `Artifacts:` paths written or skipped.
- `Detected commands:` test/lint/build/start, with confidence.
- `Open setup questions:` unresolved items or `none`.
- `Next:` recommended skill invocation.
