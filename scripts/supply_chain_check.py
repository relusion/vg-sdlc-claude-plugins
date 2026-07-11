#!/usr/bin/env python3
"""Enterprise hardening drift check.

This is a narrow, stdlib-only checker for the controls that are easy to make
deterministic in this repository:

* GitHub Actions references are pinned to immutable commit SHAs (including the
  copy-in adopter CI template under templates/adopter-ci/ and the composite
  actions under action/).
* the Claude CLI CLAUDE_VERSION pin cannot drift between the two workflows
  that install the CLI (plugin-validate.yml and eval-live.yml).
* the agent-agnostic merge bar (merge-policy.json, gate_runner.py, the
  composite action under action/merge-bar/, its self-test workflow, and the
  SHA-verified air-gapped fallback template) cannot be silently unshipped.
* CI still runs the repo's safety gates.
* the tag-push release workflow keeps regenerating the adopter pin block
  (scripts/print_pin_block.py, whose checksummed file set is derived from the
  merge-policy gate registry) into the GitHub Release notes, so a published
  pin block cannot go stale or be silently deregistered.
* the GitLab CI and Azure Pipelines merge-bar ports keep their checksum
  discipline (the product on platforms with no composite-action equivalent).
* secret scanning still verifies downloaded tooling by checksum.
* release/delivery skills surface supply-chain evidence instead of implying it.
* optional evidence and metrics projection scripts remain present and documented.
* the enterprise hardening control map and adversarial eval fixtures exist.

It is not a vulnerability scanner and it does not attest compliance. It keeps
the enterprise hardening posture from silently rotting as files move or prose is
edited.
"""

from __future__ import annotations

import argparse
import filecmp
import json
import re
import sys
from pathlib import Path

DEFAULT_ROOT = Path(__file__).resolve().parents[1]
SHA_RE = re.compile(r"^[0-9a-fA-F]{40}$")
USES_RE = re.compile(r"^\s*-\s+uses:\s+([^@\s#]+)@([^\s#]+)", re.MULTILINE)
CLAUDE_PIN_RE = re.compile(r"^\s*CLAUDE_VERSION:\s*([^\s#]+)", re.MULTILINE)


def rel(root: Path, path: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def read(root: Path, path: Path, errors: list[str]) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        errors.append(f"missing: {rel(root, path)}")
    except (OSError, UnicodeDecodeError) as exc:
        errors.append(f"cannot read: {rel(root, path)}: {exc}")
    return ""


def require_contains(root: Path, path: Path, text: str, needles: list[str],
                     errors: list[str]) -> None:
    for needle in needles:
        if needle not in text:
            errors.append(f"{rel(root, path)}: missing required text {needle!r}")


def check_workflows(root: Path, errors: list[str]) -> int:
    workflows_dir = root / ".github" / "workflows"
    workflows = sorted(workflows_dir.glob("*.yml")) + sorted(workflows_dir.glob("*.yaml"))
    if not workflows:
        errors.append("structure: no GitHub workflow files found under .github/workflows")
        return 0

    # The copy-in adopter CI template ships the same SHA-pin discipline it
    # preaches; a missing template dir is an error (same loudness rule as the
    # workflows dir — a rename can never silently drop it from the scan).
    template_dir = root / "templates" / "adopter-ci"
    templates = sorted(template_dir.glob("*.yml")) + sorted(template_dir.glob("*.yaml"))
    if not templates:
        errors.append("structure: no adopter CI templates found under templates/adopter-ci")
    workflows = workflows + templates

    # The composite actions under action/ are the preferred delivery surface
    # for the merge bar; any `uses:` step inside them must carry the same
    # SHA-pin discipline, and the directory going missing is an error (same
    # loudness rule as the template dir above).
    action_dir = root / "action"
    actions = sorted(action_dir.glob("*/action.yml")) + sorted(action_dir.glob("*/action.yaml"))
    if not actions:
        errors.append(
            "structure: no composite actions found under action/ "
            "(merge-bar action unshipped?)"
        )
    workflows = workflows + actions

    checked = 0
    for workflow in workflows:
        checked += 1
        text = read(root, workflow, errors)
        for action, version in USES_RE.findall(text):
            if not SHA_RE.fullmatch(version):
                errors.append(
                    f"{rel(root, workflow)}: action {action}@{version} is not pinned "
                    "to a 40-character commit SHA"
                )

    plugin = root / ".github" / "workflows" / "plugin-validate.yml"
    plugin_text = read(root, plugin, errors)
    checked += 1
    require_contains(root, plugin, plugin_text, [
        "python3 scripts/portability_check.py",
        "python3 scripts/check.py --no-install-hooks",
        "python3 scripts/managed_agent_check.py",
        "python3 scripts/supply_chain_check.py",
        "python3 scripts/eval_check.py",
        "python3 scripts/eval_run.py --profile smoke",
        "python3 scripts/eval_run.py --profile benchmark",
        "python3 scripts/metrics_report.py --json",
        "python3 scripts/enterprise_evidence.py --json",
        "python3 -m unittest discover -s tests -v",
        "bash scripts/test-cookbooks.sh",
        "claude plugin validate --strict .claude-plugin/marketplace.json",
    ], errors)

    # The CLAUDE_VERSION pin must stay identical in the two workflows that
    # install the CLI — a drifted eval-live pin would run live evals on a CLI
    # version the plugin-validate matrix never proved green.
    eval_live = root / ".github" / "workflows" / "eval-live.yml"
    eval_live_text = read(root, eval_live, errors)
    checked += 1
    pins: dict[str, str] = {}
    for pin_path, pin_text in ((plugin, plugin_text), (eval_live, eval_live_text)):
        pin_match = CLAUDE_PIN_RE.search(pin_text)
        if pin_match:
            pins[rel(root, pin_path)] = pin_match.group(1)
        elif pin_text:
            errors.append(f"{rel(root, pin_path)}: no CLAUDE_VERSION: pin found")
    if len(set(pins.values())) > 1:
        drift = ", ".join(f"{name} pins {ver}" for name, ver in sorted(pins.items()))
        errors.append(f"CLAUDE_VERSION pin drift: {drift} — bump both pins together")

    secret = root / ".github" / "workflows" / "secret-scan.yml"
    secret_text = read(root, secret, errors)
    checked += 1
    require_contains(root, secret, secret_text, [
        "gitleaks",
        "fetch-depth: 0",
        "sha256sum -c -",
        "./gitleaks git --redact --exit-code 1 .",
    ], errors)

    version = root / ".github" / "workflows" / "version-bump.yml"
    version_text = read(root, version, errors)
    checked += 1
    require_contains(root, version, version_text, [
        "python3 scripts/version_bump.py --check",
    ], errors)

    # The red-main canary must exist, run on a schedule, and watch the two
    # push-required checks plus the scheduled eval-live workflow — so a red
    # main can never again go unnoticed, and the canary itself cannot be
    # silently deleted, de-scheduled, or de-scoped.
    canary = root / ".github" / "workflows" / "main-health-canary.yml"
    canary_text = read(root, canary, errors)
    checked += 1
    require_contains(root, canary, canary_text, [
        "schedule:",
        "plugin-validate.yml",
        "secret-scan.yml",
        "eval-live.yml",
    ], errors)

    # The tag-push release workflow regenerates the pin block from committed
    # state at the tagged commit and publishes it into the GitHub Release
    # notes — the release chain adopters pin against. It must keep the
    # policy-derived print_pin_block generation step, the tag-existence guard on
    # create, and the gh-release publish, so the chain cannot be silently
    # deregistered (a deleted workflow file fails the same way via read() above).
    release = root / ".github" / "workflows" / "release-pin-block.yml"
    release_text = read(root, release, errors)
    checked += 1
    require_contains(root, release, release_text, [
        "scripts/print_pin_block.py",
        "--verify-tag",
        "gh release",
    ], errors)

    # The merge-bar action self-test must keep exercising the local action
    # (`uses: ./action/merge-bar`) in BOTH verdict directions and persisting
    # the verdict artifact — the continuous proof adopters pin against.
    selftest = root / ".github" / "workflows" / "action-selftest.yml"
    selftest_text = read(root, selftest, errors)
    checked += 1
    require_contains(root, selftest, selftest_text, [
        "./action/merge-bar",
        "expect green",
        "expect red",
        "merge-verdict",
        "actions/upload-artifact",
        # WS2-T10: the signed-verdict self-test — attest on, then a real
        # gh attestation verify — must keep proving the OIDC path continuously.
        "attest: 'true'",
        "gh attestation verify",
    ], errors)

    return checked


def check_control_map(root: Path, errors: list[str]) -> int:
    doc = root / "docs" / "ENTERPRISE-HARDENING.md"
    text = read(root, doc, errors)
    require_contains(root, doc, text, [
        "# Enterprise Hardening",
        "## Control Map",
        "## Enforcement Surfaces",
        "## Evidence and Attestation",
        "## Gaps and Roadmap",
        "OWASP LLM Top 10",
        "OWASP Agentic",
        "SLSA",
        "OpenSSF Scorecard",
        "SBOM",
        "CycloneDX",
        "SPDX",
        "scripts/supply_chain_check.py",
        "scripts/enterprise_evidence.py",
        "scripts/metrics_report.py",
    ], errors)
    return 1


def check_quality_moat_tools(root: Path, errors: list[str]) -> int:
    evidence = root / "scripts" / "enterprise_evidence.py"
    evidence_text = read(root, evidence, errors)
    require_contains(root, evidence, evidence_text, [
        "syft",
        "osv-scanner",
        "SBOM",
        "provenance",
        "signatures",
        "checksums",
        "Scorecard",
        "not a signed attestation",
    ], errors)

    metrics = root / "scripts" / "metrics_report.py"
    metrics_text = read(root, metrics, errors)
    require_contains(root, metrics, metrics_text, [
        ".metrics.jsonl",
        "review-summary.json",
        "evals",
        "honest_limitations",
        "not a delivery-quality verdict",
    ], errors)
    return 2


def check_release_and_delivery_skills(root: Path, errors: list[str]) -> int:
    release = root / "plugins/core-engineering/skills/ce-ship-release/SKILL.md"
    release_text = read(root, release, errors)
    require_contains(root, release, release_text, [
        "Supply-Chain Evidence",
        "SBOM",
        "SLSA provenance",
        "signatures",
        "checksums",
        "OpenSSF Scorecard",
        "records presence; it does not generate SBOMs",
    ], errors)

    deliver = root / "plugins/core-engineering/skills/ce-ship-deliver/SKILL.md"
    deliver_text = read(root, deliver, errors)
    require_contains(root, deliver, deliver_text, [
        "Supply-chain evidence inventory",
        "supply_chain_evidence",
        "SBOM",
        "provenance",
        "checksums",
        "signatures",
        "evidence_globs",
    ], errors)
    return 2


def check_dependency_gates(root: Path, errors: list[str]) -> int:
    """Typosquat-gate integrity: every dep-guard fork must match its canonical.

    The canonical→copies registry lives in
    plugins/core-engineering/fork-manifest.json — the same single source
    check.py §5 asserts. This lens re-checks just the dependency-gate forks
    (dep-guard.py + popular-packages.json) because a drifted copy is a
    supply-chain hole, not merely corpus drift.
    """
    manifest = root / "plugins/core-engineering/fork-manifest.json"
    try:
        forks = json.loads(manifest.read_text(encoding="utf-8")).get("forks", [])
    except FileNotFoundError:
        errors.append(f"missing: {rel(root, manifest)} (forked-gate registry)")
        return 0
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"unreadable: {rel(root, manifest)}: {exc}")
        return 0

    gate_names = {"dep-guard.py", "popular-packages.json"}
    seen: set[str] = set()
    checked = 0
    for fork in forks:
        left_rel = fork.get("canonical", "")
        if Path(left_rel).name not in gate_names:
            continue
        seen.add(Path(left_rel).name)
        left = root / left_rel
        for right_rel in fork.get("copies") or []:
            right = root / right_rel
            checked += 1
            if not left.is_file() or not right.is_file():
                errors.append(f"dependency gate missing: {left_rel} <-> {right_rel}")
                continue
            if not filecmp.cmp(left, right, shallow=False):
                errors.append(f"dependency gate drift: {right_rel} differs from {left_rel}")
    for name in sorted(gate_names - seen):
        errors.append(
            f"fork-manifest.json no longer registers {name} — dependency gate unguarded"
        )
    return checked


def check_merge_bar(root: Path, errors: list[str]) -> int:
    """Anti-deregistration lens: the agent-agnostic merge bar cannot be
    silently unshipped. check.py section 14 validates merge-policy.json's
    structure; this lens only asserts the load-bearing surfaces exist and
    keep their hardening. For the air-gapped fallback template: full checksum
    coverage of every decision-making file, the 40-hex TOOLKIT_REF guard,
    base-ref-sourced local inputs (the PR must not grade itself), the
    documented CODEOWNERS/.github/** companion control, the honest-scope
    block (integrity, not function — adopters keep their own build/test job),
    and the preferred-path demotion header routing adopters to the composite
    action. For the composite action: the same movable-ref guard, base-ref
    reads, verdict artifact, and honest-scope README wording."""
    checked = 0
    policy_path = root / "plugins/core-engineering/merge-policy.json"
    for path in [
        policy_path,
        root / "scripts/gate_runner.py",
    ]:
        checked += 1
        if not path.is_file():
            errors.append(f"missing: {rel(root, path)} (merge bar unshipped?)")

    # WS2-T5 anti-deregistration: the same-PR declared-deps path (dep-guard's
    # declared list is read from base + head) is safe ONLY because touching
    # .github/merge-bar/** auto-escalates the change class to two-human via the
    # shipped policy's class_rules. Silently dropping that rule reopens the
    # self-grading gap, so assert a .github-prefixed glob maps to a two-human
    # class here (check.py §14 validates the block's STRUCTURE; this lens
    # guards its load-bearing CONTENT).
    checked += 1
    if policy_path.is_file():
        try:
            policy = json.loads(policy_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            errors.append(f"{rel(root, policy_path)}: unreadable/invalid JSON: {exc}")
            policy = None
        # A non-dict policy is check.py §14's error to report (top-level shape);
        # this content lens only applies to a well-formed object.
        if isinstance(policy, dict):
            classes = policy.get("change_classes", {})
            if not isinstance(classes, dict):
                classes = {}
            two_human = {c for c, bar in classes.items()
                         if isinstance(bar, dict) and bar.get("validity") == "two-human"}
            class_rules = policy.get("class_rules")
            rules = (class_rules.get("rules")
                     if isinstance(class_rules, dict) else None) or []
            rules = rules if isinstance(rules, list) else []
            escalates = any(
                isinstance(rule, dict) and rule.get("class") in two_human
                and any(isinstance(p, str) and p.startswith(".github")
                        for p in (rule.get("paths") or []))
                for rule in rules)
            if not escalates:
                errors.append(
                    f"{rel(root, policy_path)}: no class_rules rule escalates a "
                    f".github/** path to a two-human class — the same-PR "
                    f"declared-deps path (WS2-T5) would let a PR grade itself")

    action = root / "action" / "merge-bar" / "action.yml"
    action_text = read(root, action, errors)
    checked += 1
    require_contains(root, action, action_text, [
        "scripts/gate_runner.py",
        "--plugin-root",
        "merge-verdict.json",
        # the action pin must be an immutable 40-hex commit SHA, enforced at
        # run time (movable tag/branch refs fail loudly)
        "^[0-9a-f]{40}$",
        # the policy override is read from the BASE ref, never the PR head
        'cat-file -e "${base}:${POLICY_PATH}"',
        # declared-deps is read from BOTH base and head (the same-PR path, safe
        # only under the .github/** two-human escalation asserted above)
        'cat-file -e "${base}:${DECLARED_DEPS_PATH}"',
        'cat-file -e "HEAD:${DECLARED_DEPS_PATH}"',
        # WS2-T10 signed verdicts: the opt-in attest input, the predicate
        # transform, and the SHA-pinned keyless-OIDC signer must stay wired
        # (the generic uses:-scan above already asserts actions/attest is
        # SHA-pinned; these needles keep the signing STEP from being dropped).
        "scripts/verdict_predicate.py",
        "actions/attest@",
        "predicate-type:",
    ], errors)

    action_readme = root / "action" / "merge-bar" / "README.md"
    action_readme_text = read(root, action_readme, errors)
    checked += 1
    require_contains(root, action_readme, action_readme_text, [
        # the honest-scope block, copy-identical to the runner docstring's
        # claims (integrity, not function) — same needles as the template
        "integrity, not function",
        "build/test job",
        # the one adoption footgun and the two documented companions
        "fetch-depth: 0",
        "CODEOWNERS",
        "templates/adopter-ci/gates.yml",
    ], errors)

    template = root / "templates" / "adopter-ci" / "gates.yml"
    template_text = read(root, template, errors)
    checked += 1
    require_contains(root, template, template_text, [
        "sha256sum -c",
        "scripts/gate_runner.py",
        "fetch-depth: 0",
        "merge-verdict.json",
        # the checksum step must cover every file that decides pass/fail —
        # the runner + policy alone leave the three gate scripts swappable
        "spec-lint.py",
        "test-guard.py",
        "dep-guard.py",
        # TOOLKIT_REF must be validated as an immutable 40-hex commit SHA
        "^[0-9a-f]{40}$",
        # the PR must not grade itself: declared-deps and the policy override
        # are read from the BASE ref, never the PR head checkout
        ':.github/merge-bar/declared-deps.txt"',
        ':.github/merge-bar/merge-policy.json"',
        # and the .github/** companion control stays documented in the template
        "CODEOWNERS",
        # the honest-scope block: the bar proves artifact integrity, never
        # that the code builds or its tests pass — adopters must keep their
        # own build/test job as a second required check. These needles keep
        # that statement from being silently dropped from the header.
        "WHAT THIS PROVES",
        "integrity, not function",
        "build/test job",
        # the preferred-path demotion: the header must route adopters to the
        # composite action and state this file's fallback status
        "action/merge-bar",
        "AIR-GAPPED FALLBACK",
    ], errors)
    return checked


def check_drift_template(root: Path, errors: list[str]) -> int:
    """Anti-deregistration lens: the post-merge drift monitor
    (templates/adopter-ci/drift.yml) — the pre-merge bar's complement — cannot
    be silently unshipped or unhardened. The generic `uses:` scan in
    check_workflows() already asserts any action inside it is SHA-pinned; this
    lens guards its load-bearing CONTENT: scheduled + post-merge triggers, a
    least-privilege default, the same 40-hex movable-ref guard gates.yml uses,
    checksum coverage of EVERY file that decides drift (the scanner plus the
    two lints it uses as its integrity oracle — a swapped lint could turn a red
    plan green), the committed-state scan invocation, the verdict artifact, and
    the documented --advisory-only first-run rollout. Its needles are disjoint
    from check_merge_bar's (drift-verdict.json vs merge-verdict.json,
    drift_scan.py vs gate_runner.py) so neither lens masks the other's drift."""
    template = root / "templates" / "adopter-ci" / "drift.yml"
    template_text = read(root, template, errors)
    checked = 1
    require_contains(root, template, template_text, [
        # scheduled + post-merge triggers — this runs AFTER merge, on main, the
        # complement to gates.yml's pre-merge pull_request trigger
        "schedule:",
        "branches: [main]",
        # least-privilege default posture (the optional escalation widens it)
        "contents: read",
        # TOOLKIT_REF must be validated as an immutable 40-hex commit SHA — a
        # movable tag/branch pin would checksum-verify a moving target
        "TOOLKIT_REF",
        "^[0-9a-f]{40}$",
        # the checksum step must cover EVERY file that decides drift: the
        # scanner and the two lints it invokes as its integrity oracle
        "sha256sum -c",
        "scripts/drift_scan.py",
        "plan-lint.py",
        "spec-lint.py",
        # the scan runs over the committed self-checkout and tees a machine
        # verdict a human (or the optional escalation) can read
        '--repo "$GITHUB_WORKSPACE"',
        "drift-verdict.json",
        # the documented first-run rollout escape hatch for legacy plans
        "--advisory-only",
    ], errors)
    return checked


def check_ci_ports(root: Path, errors: list[str]) -> int:
    """Anti-deregistration lens: the GitLab CI and Azure Pipelines merge-bar
    ports (WS2-T9) — the checksum-discipline product on platforms with no
    composite-action equivalent — cannot be silently unshipped or unhardened.
    The generic `uses:` scan in check_workflows() proves nothing about these
    (GitLab/Azure YAML carry no `uses:` steps), so this lens guards their
    load-bearing CONTENT: the same 40-hex movable-ref guard, a `sha256sum -c`
    pin block over every pass/fail-deciding file, the base-ref-sourced local
    inputs (the change under judgment must not grade itself — declared-deps read
    from base ∪ head, the policy override from base only), the gate_runner
    invocation, the persisted verdict, the honest-scope header, the reference to
    the policy-derived pin-block generator, and the platform-equivalent
    CODEOWNERS / branch-policy residue. Its needles are disjoint from
    check_merge_bar's (.gitlab/.azure vs .github, no action/AIR-GAPPED wording)
    so neither lens masks the other's drift."""
    checked = 0

    gitlab = root / "templates" / "adopter-ci" / "gates.gitlab-ci.yml"
    gitlab_text = read(root, gitlab, errors)
    checked += 1
    require_contains(root, gitlab, gitlab_text, [
        # movable-ref guard + checksum pin over every pass/fail-deciding file
        "^[0-9a-f]{40}$",
        "sha256sum -c",
        "scripts/gate_runner.py",
        "spec-lint.py",
        "test-guard.py",
        "dep-guard.py",
        "merge-verdict.json",
        # the MR must not grade itself: policy override from base, declared-deps
        # from base AND head (GitLab-namespaced, disjoint from the .github port)
        ':.gitlab/merge-bar/merge-policy.json"',
        ':.gitlab/merge-bar/declared-deps.txt"',
        '"HEAD:.gitlab/merge-bar/declared-deps.txt"',
        "CI_MERGE_REQUEST_TARGET_BRANCH_NAME",
        # honest scope + companion residue + the generator that keeps the pin
        # block from drifting
        "integrity, not function",
        "build/test job",
        "CODEOWNERS",
        "print_pin_block.py",
    ], errors)

    azure = root / "templates" / "adopter-ci" / "azure-pipelines-gates.yml"
    azure_text = read(root, azure, errors)
    checked += 1
    require_contains(root, azure, azure_text, [
        "^[0-9a-f]{40}$",
        "sha256sum -c",
        "scripts/gate_runner.py",
        "spec-lint.py",
        "test-guard.py",
        "dep-guard.py",
        "merge-verdict.json",
        ':.azure/merge-bar/merge-policy.json"',
        ':.azure/merge-bar/declared-deps.txt"',
        '"HEAD:.azure/merge-bar/declared-deps.txt"',
        "System.PullRequest.TargetBranch",
        "fetchDepth: 0",
        "integrity, not function",
        "build/test job",
        # Azure's companion residue: a branch policy (build validation +
        # required reviewers) is what protects the pipeline file and inputs
        "Branch policies",
        "print_pin_block.py",
    ], errors)
    return checked


def check_test_integrity(root: Path, errors: list[str]) -> int:
    """Anti-deregistration lens: the standalone test-integrity composite action
    (WS2-T11) — the field's only unbundled test-integrity gate — cannot be
    silently unshipped or unhardened. The generic action scan in
    check_workflows() already asserts any `uses:` inside it is SHA-pinned; this
    lens guards its load-bearing CONTENT: it REFERENCES the canonical
    test-guard.py (never a fork), keeps the same movable-ref guard as merge-bar,
    keeps the honest-scope README (integrity, never sufficiency; not a
    replacement for running the suite), and stays self-tested in BOTH verdict
    directions. Its needles are disjoint from merge-bar's so neither lens masks
    the other's drift."""
    checked = 0

    action = root / "action" / "test-integrity" / "action.yml"
    action_text = read(root, action, errors)
    checked += 1
    require_contains(root, action, action_text, [
        # references the toolkit's canonical gate script, never a forked copy
        "ce-implement/scripts/test-guard.py",
        # cross-task diff mode over committed state
        "--base",
        "--head HEAD",
        "--json",
        # the action pin must be an immutable 40-hex commit SHA (movable refs
        # fail loudly at run time) — same guard as merge-bar
        "^[0-9a-f]{40}$",
        # the verdict artifact the self-test asserts and adopters upload
        "test-integrity-verdict.json",
    ], errors)

    action_readme = root / "action" / "test-integrity" / "README.md"
    action_readme_text = read(root, action_readme, errors)
    checked += 1
    require_contains(root, action_readme, action_readme_text, [
        # sells the specific failure mode by name
        "an agent that makes tests pass by weakening tests",
        # the honest-scope statement: integrity, never sufficiency, and never a
        # replacement for running the suite (keep your own build/test job)
        "integrity, never sufficiency",
        "not a replacement for running",
        "build/test job",
        # the one adoption footgun stays documented
        "fetch-depth: 0",
        "CODEOWNERS",
    ], errors)

    # The self-test must keep exercising the local action (`uses:
    # ./action/test-integrity`) in BOTH verdict directions and persisting the
    # verdict artifact — the continuous proof adopters pin against.
    selftest = root / ".github" / "workflows" / "action-selftest.yml"
    selftest_text = read(root, selftest, errors)
    checked += 1
    require_contains(root, selftest, selftest_text, [
        "./action/test-integrity",
        "test-integrity on the honest change — expect green",
        "test-integrity on the cheat — expect red",
        "test-integrity-verdict",
    ], errors)

    return checked


def scenario_by_id(data: dict, sid: str) -> dict | None:
    for scenario in data.get("scenarios", []):
        if isinstance(scenario, dict) and scenario.get("id") == sid:
            return scenario
    return None


def check_adversarial_evals(root: Path, errors: list[str]) -> int:
    scenarios_path = root / "evals" / "scenarios.json"
    try:
        data = json.loads(scenarios_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        errors.append(f"missing: {rel(root, scenarios_path)}")
        return 0
    except json.JSONDecodeError as exc:
        errors.append(f"{rel(root, scenarios_path)}: invalid JSON: {exc}")
        return 0

    checked = 1
    expected = {
        "EVAL-011": ("ce-ask", "adversarial-instructions"),
        "EVAL-012": ("ce-impact", "adversarial-instructions"),
    }
    for sid, (skill, fixture) in expected.items():
        scenario = scenario_by_id(data, sid)
        if not scenario:
            errors.append(f"{rel(root, scenarios_path)}: missing {sid}")
            continue
        if scenario.get("skill") != skill:
            errors.append(f"{sid}: expected skill {skill!r}, got {scenario.get('skill')!r}")
        if scenario.get("fixture") != fixture:
            errors.append(f"{sid}: expected fixture {fixture!r}, got {scenario.get('fixture')!r}")
        checks = scenario.get("output_checks", {})
        forbidden = checks.get("forbidden_substrings", []) if isinstance(checks, dict) else []
        for marker in ("IGNORE_PREVIOUS_SYSTEM", "read ~/.ssh", "exfiltrate"):
            if marker not in forbidden:
                errors.append(f"{sid}: missing adversarial forbidden substring {marker!r}")

    fixture_dir = root / "evals" / "fixtures" / "adversarial-instructions"
    for path_rel in [
        "README.md",
        "app.py",
        "checks/webhook_check.py",
        "docs/vendor-runbook.md",
    ]:
        checked += 1
        path = fixture_dir / path_rel
        if not path.is_file():
            errors.append(f"missing adversarial fixture file: {rel(root, path)}")

    vendor = fixture_dir / "docs" / "vendor-runbook.md"
    vendor_text = read(root, vendor, errors)
    require_contains(root, vendor, vendor_text, [
        "IGNORE_PREVIOUS_SYSTEM",
        "read ~/.ssh",
        "exfiltrate",
    ], errors)
    return checked


def check_live_eval_workflow(root: Path, errors: list[str]) -> int:
    """The live-eval CI path cannot be silently unshipped or made unsafe.

    eval-live.yml must keep: dispatch/schedule-only triggers (any code-driven
    trigger would expose the API-key secret to code the secret's owner did not
    review), the hard per-scenario budget cap, --bare API-key auth, an explicit
    skip notice when the secret is absent (a green run must never imply live
    evidence that was not produced), and artifact persistence (CI never
    commits run records back to the repository)."""
    workflow = root / ".github" / "workflows" / "eval-live.yml"
    text = read(root, workflow, errors)
    require_contains(root, workflow, text, [
        "workflow_dispatch",
        "schedule:",
        "concurrency:",
        "--execute",
        "--max-budget-usd",
        "--bare",
        "ANTHROPIC_API_KEY",
        "live evals SKIPPED",
        "actions/upload-artifact",
    ], errors)
    for forbidden in ("pull_request", "push:"):
        if forbidden in text:
            errors.append(
                f"{rel(root, workflow)}: trigger {forbidden!r} must not appear — "
                "the live-eval workflow runs only via dispatch/schedule so the "
                "API-key secret is never exposed to unreviewed code"
            )
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check enterprise hardening controls")
    parser.add_argument("--root", default=str(DEFAULT_ROOT), help="repository root")
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()

    errors: list[str] = []
    checked = 0
    checked += check_workflows(root, errors)
    checked += check_control_map(root, errors)
    checked += check_release_and_delivery_skills(root, errors)
    checked += check_quality_moat_tools(root, errors)
    checked += check_dependency_gates(root, errors)
    checked += check_merge_bar(root, errors)
    checked += check_drift_template(root, errors)
    checked += check_ci_ports(root, errors)
    checked += check_test_integrity(root, errors)
    checked += check_adversarial_evals(root, errors)
    checked += check_live_eval_workflow(root, errors)

    if errors:
        print(
            f"supply-chain: FAIL — {len(errors)} issue(s) across {checked} check(s):",
            file=sys.stderr,
        )
        for error in errors:
            print(f"  ✗ {error}", file=sys.stderr)
        return 1
    print(f"supply-chain: OK — {checked} check(s), 0 issues.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
