#!/usr/bin/env python3
"""Validate the framework's product-facing documentation layer.

The engineering core already has manifest, corpus, eval, portability, and
hardening checks. This script guards the adoption surface: first-run docs,
workflow recipes, usage routing, doc-link integrity, and CI visibility.

It deliberately checks structure and coverage, not prose quality.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

DEFAULT_ROOT = Path(__file__).resolve().parents[1]
COMMAND_RE = re.compile(
    r"(?<![\w/.-])/([A-Za-z_][A-Za-z0-9_-]*):(ce-[A-Za-z0-9-]+)\b"
)

PRODUCT_DOCS = {
    "README.md": [
        "docs/README.md",
        "docs/GETTING-STARTED.md",
        "docs/WORKFLOW-RECIPES.md",
        "docs/USAGE-MATRIX.md",
        "docs/HOW-IT-WORKS.md",
        "docs/BENCHMARKS.md",
        "docs/EXAMPLES.md",
        "docs/COMPARISON.md",
        "docs/TEAM-ROLLOUT.md",
        "CONTRIBUTING.md",
        # The repositioned merge-bar front door (WS7-T9): the wedge-led README
        # leads with the control-plane pitch and demotes the full skill catalog
        # below a "Week one — eight verbs" table. This needle drift-guards that
        # week-one section heading so the front door cannot silently lose it.
        "## Week one",
    ],
    "CLAUDE.md": [
        "docs/README.md",
        "docs/GETTING-STARTED.md",
        "docs/WORKFLOW-RECIPES.md",
        "docs/USAGE-MATRIX.md",
    ],
    "docs/GETTING-STARTED.md": [
        "# Getting Started",
        "## Prerequisites",
        "## Install",
        "## First 10 Minutes",
        "## Common First Runs",
        "## What It Costs",
        "## Safety Boundaries",
        "## Troubleshooting",
        "## Contributing to the Framework",
        "claude plugin install core-engineering@vg-coding",
        "BENCHMARKS.md",
        "CONTRIBUTING.md",
        "/core-engineering:ce-ask",
        "/core-engineering:ce-impact",
        "/core-engineering:ce-init",
        "/core-engineering:ce-brief",
        "/core-engineering:ce-plan",
        "/core-engineering:ce-patch",
    ],
    "CONTRIBUTING.md": [
        "# Contributing",
        "python3 scripts/check.py --no-install-hooks",
        "python3 scripts/eval_check.py",
        "python3 scripts/portability_check.py",
        "python3 -m unittest discover -s tests",
        "docs/contributing/SKILL-AUTHORING.md",
        "docs/contributing/HITL-GATE-STANDARD.md",
        "CHANGELOG.md",
    ],
    "docs/README.md": [
        "# Documentation",
        "## Use the plugins",
        "## Evaluate or adopt the project",
        "## Contribute",
        "GETTING-STARTED.md",
        "USAGE-MATRIX.md",
        "WORKFLOW-RECIPES.md",
        "HOW-IT-WORKS.md",
        "evals/README.md",
        "contributing/SKILL-AUTHORING.md",
    ],
    "docs/BENCHMARKS.md": [
        "# Benchmarks & Evaluation Budgets",
        "## Historical successful-run budget caps",
        "## What is *not* yet measured",
        "eval_run.py",
        "--max-budget-usd",
        "EVAL-001",
    ],
    "docs/EXAMPLES.md": [
        "# Real Outputs",
        "Provenance",
        "Reproduce",
        "evals/golden/EVAL-005",
    ],
    "docs/TEAM-ROLLOUT.md": [
        "# Team Rollout",
        "review-policy.md",
        "BENCHMARKS.md",
        "## Rolling back",
        "metrics_report.py",
    ],
    "docs/COMPARISON.md": [
        "# Choosing a Spec-Driven Toolchain",
        "spec-kit",
        "Kiro",
        "aider",
        "as of",
    ],
    "docs/WORKFLOW-RECIPES.md": [
        "# Workflow Recipes",
        "## Recipe 1: Answer A Codebase Question",
        "## Recipe 2: Refine A Work Item",
        "## Recipe 3: Plan A New Feature",
        "## Recipe 4: Build One Planned Feature",
        "## Recipe 5: Review And Verify Before Handoff",
        "## Recipe 6: Handle A Small Fix",
        "## Recipe 7: Investigate A Failure",
        "## Recipe 8: Probe Risk",
        "## Recipe 9: Prepare A Release Handoff",
        "## Recipe 10: Run The Full Spine Autonomously",
        "## Recipe 11: Learn A Built System",
        "## Recipe 12: Shape Product Direction",
        "## Recipe 13: Make A Technical Decision",
        "## Recipe 14: Audit Planning And Process",
        "## Recipe 15: Check Planned UX",
        "## Recipe 16: Export Work Items",
        "## Recipe 18: Bootstrap A Repository",
        "## Recipe 19: Return To A Plan Mid-Flight",
        "## Recipe 20: Operate An Unattended Run",
        "Expected artifacts",
        "Stop or escalate",
        "--resume",
        "STATUS.md",
    ],
    "plugins/core-engineering/skills/ce-init/SKILL.md": [
        ".claude/ce-write-scope.json",
        ".claude/ce-write-scope.session.json",
        ".claude/ce-guard-log.jsonl",
        ".claude/ce-session-model.json",
    ],
}

RUNTIME_STATE_IGNORES = (
    ".claude/ce-write-scope.json",
    ".claude/ce-write-scope.session.json",
    ".claude/ce-guard-log.jsonl",
    ".claude/ce-session-model.json",
)

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


def skill_names(root: Path) -> set[str]:
    # Union across every marketplace plugin, so USAGE-MATRIX / WORKFLOW-RECIPES
    # may route to a second plugin's skills (e.g. the idea trio in
    # product-discovery) without tripping "unknown skill(s)".
    return {
        path.parent.name
        for path in sorted((root / "plugins").glob("*/skills/*/SKILL.md"))
    }


def skill_commands(root: Path) -> set[str]:
    return {
        f"/{path.parents[2].name}:{path.parent.name}"
        for path in sorted((root / "plugins").glob("*/skills/*/SKILL.md"))
    }


def commands_in(text: str) -> set[str]:
    return {
        f"/{match.group(1)}:{match.group(2)}"
        for match in COMMAND_RE.finditer(text)
    }


def check_docs(root: Path, errors: list[str]) -> int:
    checked = 0
    for doc_rel, needles in PRODUCT_DOCS.items():
        path = root / doc_rel
        text = read(root, path, errors)
        checked += 1
        for needle in needles:
            if needle not in text:
                errors.append(f"{doc_rel}: missing product-layer text {needle!r}")
    return checked


def check_runtime_state_ignores(root: Path, errors: list[str]) -> int:
    """Runtime guard/session sidecars must not enter an adopter commit.

    Exported/minimal fixture trees used by downstream checks may deliberately
    omit both Git metadata and a .gitignore; there is no commit boundary to
    guard in that shape. A real checkout must carry the file and every runtime
    entry, while a copied tree that does include .gitignore is checked too.
    """
    path = root / ".gitignore"
    if not path.exists():
        if (root / ".git").exists():
            errors.append(".gitignore: missing from a Git checkout")
        return 1
    text = read(root, path, errors)
    for needle in RUNTIME_STATE_IGNORES:
        if needle not in text:
            errors.append(f".gitignore: missing runtime-state entry {needle!r}")
    return 1


def check_usage_matrix(root: Path, errors: list[str]) -> int:
    path = root / "docs/USAGE-MATRIX.md"
    text = read(root, path, errors)
    names = skill_names(root)
    if not names:
        errors.append("structure: no skills found under any plugins/*/skills")
        return 1
    expected = skill_commands(root)
    listed = commands_in(text)
    missing = sorted(expected - listed)
    extra = sorted(listed - expected)
    if missing:
        errors.append(
            f"docs/USAGE-MATRIX.md: missing shipped skill(s): {', '.join(missing)}"
        )
    if extra:
        errors.append(
            f"docs/USAGE-MATRIX.md: lists unknown skill(s): {', '.join(extra)}"
        )
    return 1


def check_recipes(root: Path, errors: list[str]) -> int:
    path = root / "docs/WORKFLOW-RECIPES.md"
    text = read(root, path, errors)
    listed = commands_in(text)
    expected = skill_commands(root)
    missing = sorted(expected - listed)
    if missing:
        errors.append(
            f"docs/WORKFLOW-RECIPES.md: recipes missing command(s): {', '.join(missing)}"
        )
    return 1


CE_GO_SKILL_REL = "plugins/core-engineering/skills/ce-go/SKILL.md"
ROUTING_TABLE_START = "<!-- routing-table:start -->"
ROUTING_TABLE_END = "<!-- routing-table:end -->"


def check_front_door_parity(root: Path, errors: list[str]) -> int:
    """The namespaced ce-go front-door router's routing table must route to exactly the
    skills docs/USAGE-MATRIX.md routes to — a two-way parity lint (excluding
    /core-engineering:ce-go itself), the same shape as check_usage_matrix.

    ce-go exists so a user need not learn ~30 skill names or the plan-existence
    splits between them; that promise is only true if its table stays complete.
    So a skill added to the matrix without a ce-go route fails here (missing),
    and a ce-go route naming a skill the matrix does not fails too (extra). The
    routing section is bounded by HTML-comment markers so only the table — not
    an Escalation or Honest-Limitations mention of a sibling — counts.
    """
    matrix = read(root, root / "docs/USAGE-MATRIX.md", errors)
    skill = read(root, root / CE_GO_SKILL_REL, errors)
    if ROUTING_TABLE_START not in skill or ROUTING_TABLE_END not in skill:
        errors.append(
            f"{CE_GO_SKILL_REL}: missing {ROUTING_TABLE_START} / "
            f"{ROUTING_TABLE_END} routing-table markers — the front-door parity "
            "lint cannot bound the routing section"
        )
        return 1
    block = skill.split(ROUTING_TABLE_START, 1)[1].split(ROUTING_TABLE_END, 1)[0]
    self_cmd = "/core-engineering:ce-go"
    matrix_cmds = {cmd for cmd in commands_in(matrix) if cmd != self_cmd}
    routed = {cmd for cmd in commands_in(block) if cmd != self_cmd}
    missing = sorted(matrix_cmds - routed)
    extra = sorted(routed - matrix_cmds)
    if missing:
        errors.append(
            f"{CE_GO_SKILL_REL}: routing table missing skill(s) "
            f"docs/USAGE-MATRIX.md routes to: {', '.join(missing)} — add a "
            "routing row so the front door stays complete"
        )
    if extra:
        errors.append(
            f"{CE_GO_SKILL_REL}: routing table names skill(s) not in "
            f"docs/USAGE-MATRIX.md: {', '.join(extra)} — add them to the matrix "
            "or remove the stale routing row"
        )
    return 1


AS_OF_RE = re.compile(r"as of\s+\*{0,2}(\d{4}-\d{2}-\d{2})\*{0,2}")
AS_OF_MAX_AGE_DAYS = 90


def check_comparison_freshness(root: Path, errors: list[str]) -> int:
    """COMPARISON.md's 'as of' date must be parseable and younger than the cap.

    The substring check above proves the phrase exists; this proves the claim
    has not quietly aged past usefulness — a dated positioning doc older than
    ~a quarter is stale evidence, not evidence.
    """
    from datetime import date

    path = root / "docs/COMPARISON.md"
    text = read(root, path, errors)
    dates = AS_OF_RE.findall(text)
    if not dates:
        errors.append(
            "docs/COMPARISON.md: no parseable 'as of YYYY-MM-DD' date — "
            "the freshness cap cannot be checked"
        )
        return 1
    try:
        newest = max(date.fromisoformat(d) for d in dates)
    except ValueError as exc:
        errors.append(f"docs/COMPARISON.md: unparseable 'as of' date: {exc}")
        return 1
    age = (date.today() - newest).days
    if age > AS_OF_MAX_AGE_DAYS:
        errors.append(
            f"docs/COMPARISON.md: newest 'as of' date {newest} is {age} days old "
            f"(cap {AS_OF_MAX_AGE_DAYS}) — re-verify the competitor claims and re-date"
        )
    return 1


SUPPORTED_SURFACE_RE = re.compile(
    r"\((\d+) skills across (\d+) plugins\)"
)


def check_supported_surface_claims(root: Path, errors: list[str]) -> int:
    """Keep product docs aligned with the shipped, intentionally small surface.

    The simplification removed the delivery workflow while retaining the front
    door, usage matrix, and recipes.  Count the actual plugin/skill inventory
    and reject the retired delivery vocabulary at the few product surfaces
    that previously drifted.
    """
    comparison_rel = "docs/COMPARISON.md"
    enterprise_rel = "docs/ENTERPRISE-HARDENING.md"
    init_rel = "plugins/core-engineering/skills/ce-init/SKILL.md"
    debug_rel = "plugins/core-engineering/skills/ce-debug/SKILL.md"
    implement_rel = "plugins/core-engineering/skills/ce-implement/SKILL.md"
    comparison = read(root, root / comparison_rel, errors)
    enterprise = read(root, root / enterprise_rel, errors)
    init_skill = read(root, root / init_rel, errors)
    debug_skill = read(root, root / debug_rel, errors)
    implement_skill = read(root, root / implement_rel, errors)

    plugin_count = sum(
        1 for path in (root / "plugins").glob("*/.claude-plugin/plugin.json")
        if path.is_file()
    )
    skill_count = sum(
        1 for path in (root / "plugins").glob("*/skills/*/SKILL.md")
        if path.is_file()
    )
    inventory = SUPPORTED_SURFACE_RE.search(comparison)
    expected = (skill_count, plugin_count)
    if inventory is None:
        errors.append(
            f"{comparison_rel}: missing machine-checkable supported inventory "
            f"'({skill_count} skills across {plugin_count} plugins)'"
        )
    elif tuple(map(int, inventory.groups())) != expected:
        errors.append(
            f"{comparison_rel}: supported inventory says {inventory.group(1)} "
            f"skills across {inventory.group(2)} plugins, but the shipped surface "
            f"contains {skill_count} skills across {plugin_count} plugins"
        )

    retired_claims = {
        comparison_rel: (comparison, ("backlog/delivery",)),
        enterprise_rel: (
            enterprise,
            (
                "docs/plans/<slug>/delivery/",
                "release/delivery prompts",
                "release/delivery fixture",
            ),
        ),
        init_rel: (init_skill, ("delivery base", "delivery profile")),
        debug_rel: (
            debug_skill,
            ("Diagnose Gate", "`/core-engineering:ce-auto-build` invokes debug"),
        ),
        implement_rel: (
            implement_skill,
            ("`specs/<id>/diagnosis.md` (auto-build)",),
        ),
    }
    for rel, (text, needles) in retired_claims.items():
        for needle in needles:
            if needle in text:
                errors.append(
                    f"{rel}: retired surface claim {needle!r} must not return; "
                    "keep the simplified supported workflow terminology"
                )

    duplicate_supply_chain = re.compile(
        r"scripts/check\.py --no-install-hooks\s*\n\s*"
        r"python3 scripts/supply_chain_check\.py"
    )
    if duplicate_supply_chain.search(enterprise):
        errors.append(
            f"{enterprise_rel}: lists supply_chain_check.py immediately after "
            "the umbrella check.py command, which already delegates to it"
        )
    return 1


AUTO_BUILD_RECIPE_HEADING = "## Recipe 10: Run The Full Spine Autonomously"


def check_autobuild_recipe_routes_plan_audit(root: Path, errors: list[str]) -> int:
    """The auto-build recipe section must route through namespaced ce-plan-audit.

    A substring needle over the whole file cannot prove this (Recipe 14 also
    mentions the skill), so slice Recipe 10's section — the auto-build recipe —
    up to the next `## ` heading and assert the pre-run audit step is named
    where the unattended run is taught.
    """
    text = read(root, root / "docs/WORKFLOW-RECIPES.md", errors)
    start = text.find(AUTO_BUILD_RECIPE_HEADING)
    if start == -1:
        errors.append(
            "docs/WORKFLOW-RECIPES.md: auto-build recipe heading not found "
            f"({AUTO_BUILD_RECIPE_HEADING!r})"
        )
        return 1
    end = text.find("\n## ", start + len(AUTO_BUILD_RECIPE_HEADING))
    section = text[start : end if end != -1 else len(text)]
    if "/core-engineering:ce-plan-audit" not in section:
        errors.append(
            "docs/WORKFLOW-RECIPES.md: the auto-build recipe (Recipe 10) must "
            "mention /core-engineering:ce-plan-audit as the pre-run audit step"
        )
    return 1


def check_ci(root: Path, errors: list[str]) -> int:
    path = root / ".github/workflows/plugin-validate.yml"
    text = read(root, path, errors)
    if "python3 scripts/check.py --no-install-hooks" not in text:
        errors.append(
            ".github/workflows/plugin-validate.yml: missing umbrella validation step"
        )
    return 1


# --- doc-link integrity ------------------------------------------------------
# check_doc_links resolves two reference forms across README.md + docs/**/*.md:
#   (a) markdown links [...](relpath) — #fragment stripped, resolved relative
#       to the citing file (GitHub semantics); external schemes skipped;
#   (b) backtick-quoted repo paths (`docs/...`, `scripts/...`, ...) — resolved
#       from the repo root. The purged-`docs/ROADMAP.md` citations that CI
#       never noticed were form (b); this is the check that would have caught
#       them.
#
# Skip rules — deliberately small and reviewable; extend these lists rather
# than special-casing a call site:
#   * fenced code blocks (``` / ~~~) are never scanned — they carry example
#     output, planned layouts, and command transcripts, not live references;
#   * tokens containing a placeholder/glob character (LINK_PLACEHOLDER_CHARS)
#     are templates (`docs/plans/<slug>/`, `plugins/*/hooks/*.py`), not paths;
#   * LINK_SKIP_PREFIXES — adopter-side artifact roots the skills create in
#     *consuming* repos, plus gitignored runtime output: legitimately absent
#     from this repository;
#   * a backtick token is trimmed to its first whitespace-delimited word
#     (command form: `scripts/fork_sync.py --write`) and loses any trailing
#     `:line` citation suffix before resolving.
DOC_LINK_RE = re.compile(r"!?\[[^\]]*\]\(([^)\s]+)\)")
REPO_PATH_TICK_RE = re.compile(
    r"`((?:action|docs|templates|evals|scripts|plugins|tests)"
    r"/[^`\n]*)`"
)
FENCE_RE = re.compile(r"^\s*(?:```|~~~)")
LINK_PLACEHOLDER_CHARS = frozenset("<>*{}")
LINK_SKIP_PREFIXES = (
    # adopter-side artifact roots (the skills write these in consuming repos)
    "docs/plans/",
    # where a human promotes /core-engineering:ce-decide's proposed ADR; the canonical ADR root the
    # skill corpus already cites 23 times, and an adopter-side path like the rest.
    "docs/adr/",
    "docs/briefs/",
    "docs/decisions/",
    "docs/idea-scores/",
    "docs/idea-scout/",
    "docs/infra-reviews/",
    "docs/investigations/",
    "docs/market-scans/",
    "docs/perf-profiles/",
    "docs/plan-audits/",
    "docs/sec-probes/",
    "docs/ux-audits/",
    # gitignored runtime output — present locally, absent in a fresh checkout
    "evals/runs/",
)
DANGLING_REMEDY = (
    "fix the reference or delete it — a dangling pointer at a caveat is a "
    "credibility defect"
)


def prose_lines(text: str) -> list[str]:
    """Return the lines of *text* that sit outside fenced code blocks."""
    lines, in_fence = [], False
    for line in text.splitlines():
        if FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        if not in_fence:
            lines.append(line)
    return lines


def link_skipped(token: str) -> bool:
    if LINK_PLACEHOLDER_CHARS & set(token):
        return True
    return any(
        token.startswith(prefix) or token == prefix.rstrip("/")
        for prefix in LINK_SKIP_PREFIXES
    )


def check_doc_links(root: Path, errors: list[str]) -> int:
    """Every repo-file reference in README.md + docs/**/*.md must resolve.

    Two forms: (a) markdown links, resolved relative to the citing file, and
    (b) backtick-quoted repo paths, resolved from the repo root. The skip
    rules are the module-level constants above — reviewable by design.
    """
    import os

    checked = 0
    doc_paths = [root / "README.md"] + sorted((root / "docs").glob("**/*.md"))
    for path in doc_paths:
        doc_rel = rel(root, path)
        if not path.is_file():
            continue  # a missing README/doc is check_docs' finding, not ours
        checked += 1
        text = "\n".join(prose_lines(read(root, path, errors)))
        for match in DOC_LINK_RE.finditer(text):
            raw = match.group(1)
            if raw.startswith(("http://", "https://", "mailto:", "#")):
                continue
            target = raw.split("#", 1)[0]
            if not target or LINK_PLACEHOLDER_CHARS & set(target):
                continue
            resolved = Path(os.path.normpath(path.parent / target))
            try:
                target_rel = str(resolved.relative_to(root))
            except ValueError:
                target_rel = str(resolved)  # escapes the repo — always dead
            if link_skipped(target_rel):
                continue
            if not resolved.exists():
                errors.append(
                    f"{doc_rel}: dead markdown link ({raw}) — {target_rel} "
                    f"does not exist; {DANGLING_REMEDY}"
                )
        for match in REPO_PATH_TICK_RE.finditer(text):
            # first word only (command form), minus any :line citation suffix
            token = match.group(1).split()[0].split(":")[0]
            if link_skipped(token):
                continue
            if not (root / token).exists():
                errors.append(
                    f"{doc_rel}: dead repo path `{match.group(1)}` — {token} "
                    f"does not exist; {DANGLING_REMEDY}"
                )
    return checked


BENCH_SCENARIO_ROW_RE = re.compile(r"^\|\s*(EVAL-\d+)\s*\|", re.MULTILINE)
GIT_SHA_RE = re.compile(r"^[0-9a-fA-F]{40}(?:[0-9a-fA-F]{24})?$")
EVAL_RECEIPT_CONTRACT_PATHS = (
    "evals/scenarios.json",
    "scripts/eval_run.py",
    "scripts/eval_check.py",
)

# Capture the cited run date so provenance and recency can bind the claim to the
# receipt's completion day and the contract's real last-change date.
BENCH_PASS_DATE_RE = re.compile(
    r"\|\s*(EVAL-\d+)\s*\|.*\|\s*pass\s*\((\d{4}-\d{2}-\d{2})\)\s*\|")

RECENCY_FETCH_DEPTH_FIX = (
    "the ratchet reads full git history; set `fetch-depth: 0` on the checkout "
    "(actions/checkout) so `git log` sees each skill's real last-change date"
)


def check_live_eval_provenance(root: Path, errors: list[str]) -> int:
    """Every BENCHMARKS row claiming `pass (DATE)` must resolve to a committed
    live-run summary under evals/results/. A promotable receipt must record a
    successful model process, a successful deterministic grade, a clean source
    tree, a full commit id, and a run id unique to its run/batch.

    The audit found ten 'pass (2026-06-27)' rows with zero committed evidence.
    This makes an uncited pass row (or a curated summary that does not actually
    record the scenario passing) a CI failure, so the evidence layer can only
    claim what a committed run record backs.
    """
    import json

    bench = read(root, root / "docs/BENCHMARKS.md", errors)
    claimed = BENCH_PASS_DATE_RE.findall(bench)
    if not claimed:
        return 1  # no live-pass claims to back (honest all-design-verified state)

    candidates: dict[str, list[dict]] = {}
    receipt_owners: dict[str, set[str]] = {}
    contract_commits: dict[str, str] = {}
    contract_paths_by_id: dict[str, list[str]] = {}
    try:
        catalog = json.loads((root / "evals/scenarios.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        catalog = {}
    for scenario in catalog.get("scenarios", []) if isinstance(catalog, dict) else []:
        if not isinstance(scenario, dict) or not isinstance(scenario.get("id"), str):
            continue
        skill = scenario.get("skill")
        fixture = scenario.get("fixture")
        skill_paths = [
            str(path.relative_to(root))
            for path in root.glob(f"plugins/*/skills/{skill}")
            if isinstance(skill, str) and path.is_dir()
        ]
        relevant = [*EVAL_RECEIPT_CONTRACT_PATHS, *skill_paths]
        if isinstance(fixture, str) and fixture:
            relevant.append(f"evals/fixtures/{fixture}")
        contract_paths = scenario.get("contract_paths", [])
        if isinstance(contract_paths, list):
            relevant.extend(
                path for path in contract_paths if isinstance(path, str) and path
            )
        contract_paths_by_id[scenario["id"]] = relevant
        code, output, _ = _git_out(root, "log", "-1", "--format=%H", "--", *relevant)
        if code == 0 and output.strip():
            contract_commits[scenario["id"]] = output.strip().splitlines()[0]
    results_dir = root / "evals" / "results"
    for summary in sorted(results_dir.glob("*.json")):
        summary_rel = str(summary.relative_to(root))
        if (
            _git_out(root, "ls-files", "--error-unmatch", summary_rel)[0] != 0
            or _git_out(root, "diff", "--quiet", "HEAD", "--", summary_rel)[0] != 0
        ):
            continue
        try:
            data = json.loads(summary.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            errors.append(f"evals/results/{summary.name}: unreadable/invalid JSON: {exc}")
            continue
        if data.get("dry_run") is not False:
            continue  # a summary must be a real (non-dry) run to count as evidence
        top_run_id = data.get("run_id")
        if isinstance(top_run_id, str) and top_run_id.strip():
            receipt_owners.setdefault(top_run_id, set()).add(f"{summary.name}:batch")
        top_git_head = data.get("git_head")
        top_source_clean = data.get("source_clean")
        top_grade_status = data.get("grade_status")
        top_grade_returncode = data.get("grade_returncode")
        top_graded_scenarios = data.get("graded_scenarios")
        top_completed_at = data.get("completed_at")
        top_graded_ids = (
            {item for item in top_graded_scenarios if isinstance(item, str)}
            if isinstance(top_graded_scenarios, list)
            else set()
        )
        for index, scenario in enumerate(data.get("scenarios", [])):
            if not isinstance(scenario, dict):
                continue
            scenario_run_id = scenario.get("run_id")
            run_id = scenario_run_id or top_run_id
            scenario_id = scenario.get("id")
            owner = (
                f"{summary.name}:scenario:{index}"
                if scenario_run_id
                else f"{summary.name}:batch"
            )
            if isinstance(run_id, str) and run_id.strip():
                # Identity belongs to the run/batch, regardless of its outcome.
                # A failed second record cannot safely reuse a passing receipt id.
                receipt_owners.setdefault(run_id, set()).add(owner)
            if not (
                isinstance(scenario_id, str)
                and scenario.get("status") == "pass"
                and type(scenario.get("returncode")) is int
                and scenario.get("returncode") == 0
                and isinstance(run_id, str)
                and run_id.strip()
            ):
                continue
            candidates.setdefault(scenario_id, []).append({
                "run_id": run_id,
                "owner": owner,
                "git_head": scenario.get("git_head") or top_git_head,
                "source_clean": (
                    scenario.get("source_clean")
                    if "source_clean" in scenario
                    else top_source_clean
                ),
                "grade_status": scenario.get("grade_status") or top_grade_status,
                "grade_returncode": (
                    scenario.get("grade_returncode")
                    if "grade_returncode" in scenario
                    else top_grade_returncode
                ),
                "graded": (
                    scenario.get("graded")
                    if "graded" in scenario
                    else scenario_id in top_graded_ids
                ),
                "completed_at": scenario.get("completed_at") or top_completed_at,
            })

    for eval_id, run_date in claimed:
        proven = any(
            candidate.get("grade_status") == "pass"
            and type(candidate.get("grade_returncode")) is int
            and candidate.get("grade_returncode") == 0
            and candidate.get("graded") is True
            and candidate.get("source_clean") is True
            and isinstance(candidate.get("git_head"), str)
            and GIT_SHA_RE.fullmatch(candidate["git_head"])
            and _git_out(
                root, "cat-file", "-e", f"{candidate['git_head']}^{{commit}}"
            )[0] == 0
            and _git_out(
                root, "merge-base", "--is-ancestor", candidate["git_head"], "HEAD"
            )[0] == 0
            and eval_id in contract_commits
            and _git_out(
                root, "merge-base", "--is-ancestor",
                contract_commits[eval_id], candidate["git_head"],
            )[0] == 0
            and _git_out(
                root, "diff", "--quiet", candidate["git_head"], "HEAD", "--",
                *contract_paths_by_id.get(eval_id, []),
            )[0] == 0
            and isinstance(candidate.get("completed_at"), str)
            and candidate["completed_at"][:10] == run_date
            and receipt_owners.get(candidate["run_id"]) == {candidate["owner"]}
            for candidate in candidates.get(eval_id, [])
        )
        if not proven:
            errors.append(
                f"docs/BENCHMARKS.md: {eval_id} is marked 'pass (DATE)' but no "
                f"committed evals/results/*.json records a promotable live pass "
                f"(tracked and unchanged receipt, model exit 0, scenario-bound "
                f"deterministic grade pass, matching completion date, exact current "
                f"contract, clean full git_head, and unique run_id) — cite a "
                f"complete receipt or label it "
                f"'design-verified, not live-run'"
            )
    return 1


def check_benchmark_inventory(root: Path, errors: list[str]) -> int:
    """Every catalog scenario must have exactly one BENCHMARKS status row."""
    import json

    bench = read(root, root / "docs/BENCHMARKS.md", errors)
    try:
        catalog = json.loads(
            (root / "evals/scenarios.json").read_text(encoding="utf-8")
        )
        scenarios = catalog.get("scenarios", [])
        expected = {
            scenario.get("id")
            for scenario in scenarios
            if isinstance(scenario, dict) and isinstance(scenario.get("id"), str)
        }
    except (OSError, ValueError, AttributeError) as exc:
        errors.append(
            f"evals/scenarios.json: unreadable ({exc}) — cannot verify the "
            "BENCHMARKS scenario inventory"
        )
        return 1

    rows = BENCH_SCENARIO_ROW_RE.findall(bench)
    listed = set(rows)
    missing = sorted(expected - listed)
    unknown = sorted(listed - expected)
    duplicates = sorted({eval_id for eval_id in rows if rows.count(eval_id) > 1})
    if missing:
        errors.append(
            "docs/BENCHMARKS.md: missing catalog scenario row(s): "
            + ", ".join(missing)
        )
    if unknown:
        errors.append(
            "docs/BENCHMARKS.md: lists unknown scenario row(s): "
            + ", ".join(unknown)
        )
    if duplicates:
        errors.append(
            "docs/BENCHMARKS.md: duplicate scenario row(s): "
            + ", ".join(duplicates)
        )
    return 1


def _git_out(root: Path, *args: str) -> tuple[int, str, str]:
    """Run a git command under ``root`` and return (returncode, stdout, stderr).

    A returncode of -1 signals the git binary itself could not be executed
    (missing, timed out) — distinct from git running and reporting an error.
    """
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except FileNotFoundError:
        return -1, "", "git executable not found on PATH"
    except (OSError, subprocess.SubprocessError) as exc:
        return -1, "", str(exc)
    return proc.returncode, proc.stdout, proc.stderr


def check_benchmark_recency(root: Path, errors: list[str]) -> int:
    """Recency ratchet: a BENCHMARKS ``pass (DATE)`` row is only honest while the
    skill that produced it is unchanged.

    For every ``pass (DATE)`` row, resolve the EVAL id to its skill (and fixture)
    via evals/scenarios.json and read the committed git last-change date of the
    skill directory (plus the fixture directory — a fixture edit invalidates the
    run just as a skill edit does). When that date is after the cited run, the
    row must degrade to ``design-verified, not live-run`` until a fresh run is
    recorded. Judged from committed git history alone — no model, no API — so the
    2026-* pass claims self-expire as the skills evolve instead of being cited
    forever.

    Fails loud (never silently green) on a shallow clone or an unrunnable git,
    so CI cannot pass a claim it could not actually verify. A checkout that is
    not a git working tree at all (an exported tarball, a copied test fixture)
    has no history to consult, so recency is skipped there rather than failed —
    CI always runs inside a real repo, where the shallow guard covers the only
    truncation risk that would let a stale row slip through.
    """
    import json

    bench = read(root, root / "docs/BENCHMARKS.md", errors)
    rows = BENCH_PASS_DATE_RE.findall(bench)
    if not rows:
        return 1  # no live-pass claims to keep current (honest all-design-verified)

    rc, out, err = _git_out(root, "rev-parse", "--is-shallow-repository")
    if rc == -1:
        errors.append(
            "docs/BENCHMARKS.md recency ratchet: git could not be run "
            f"({err.strip() or 'unavailable'}), so the 'pass (DATE)' rows could "
            "not be checked for staleness — refusing to pass silently; run "
            "inside a git checkout with git installed."
        )
        return 1
    if rc != 0:
        if "not a git repository" in err.lower():
            return 1  # no VCS history to consult; recency is inapplicable here
        errors.append(
            "docs/BENCHMARKS.md recency ratchet: `git rev-parse` failed "
            f"({err.strip() or rc}) — cannot verify pass-row currency."
        )
        return 1
    if out.strip() == "true":
        errors.append(
            "docs/BENCHMARKS.md recency ratchet: shallow clone — git history is "
            "truncated, so 'pass (DATE)' currency cannot be verified; "
            f"{RECENCY_FETCH_DEPTH_FIX}."
        )
        return 1

    try:
        scenarios = json.loads((root / "evals" / "scenarios.json").read_text(encoding="utf-8"))
        by_id = {
            s.get("id"): s
            for s in scenarios.get("scenarios", [])
            if isinstance(s, dict)
        }
    except (OSError, ValueError) as exc:
        errors.append(
            f"evals/scenarios.json: unreadable ({exc}) — cannot resolve "
            "BENCHMARKS 'pass (DATE)' rows to skills for the recency ratchet."
        )
        return 1

    for eval_id, run_date in rows:
        scenario = by_id.get(eval_id)
        if scenario is None:
            errors.append(
                f"docs/BENCHMARKS.md: {eval_id} is a 'pass (DATE)' row but no "
                "scenario in evals/scenarios.json carries that id — cannot "
                "verify its recency."
            )
            continue
        skill = scenario.get("skill") or ""
        fixture = scenario.get("fixture") or ""
        skill_dirs = sorted((root / "plugins").glob(f"*/skills/{skill}"))
        if not skill_dirs:
            errors.append(
                f"docs/BENCHMARKS.md: {eval_id}'s skill '{skill}' resolves to no "
                "plugins/*/skills/<name> directory — cannot verify its recency."
            )
            continue
        paths = [str(skill_dirs[0].relative_to(root))]
        fixture_dir = root / "evals" / "fixtures" / fixture
        if fixture and fixture_dir.is_dir():
            paths.append(str(fixture_dir.relative_to(root)))
        contract_paths = scenario.get("contract_paths", [])
        if isinstance(contract_paths, list):
            paths.extend(
                path for path in contract_paths if isinstance(path, str) and path
            )

        rc, out, err = _git_out(root, "log", "-1", "--format=%cs", "--", *paths)
        last_change = out.strip()
        if rc != 0 or not last_change:
            errors.append(
                f"docs/BENCHMARKS.md recency ratchet: could not read the git "
                f"last-change date for {eval_id} ({', '.join(paths)}) "
                f"({err.strip() or 'no committed history'}) — refusing to pass "
                "silently; commit the skill/fixture or repair history."
            )
            continue
        if last_change > run_date:
            trailer = f"' or fixture '{fixture}'" if len(paths) > 1 else "'"
            errors.append(
                f"docs/BENCHMARKS.md: {eval_id} claims 'pass ({run_date})' but its "
                f"skill '{skill}{trailer} last changed {last_change} — skill "
                "changed after its cited run; re-run live or relabel "
                "'design-verified, not live-run'."
            )
    return len(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check product-layer docs and routing")
    parser.add_argument("--root", default=str(DEFAULT_ROOT), help="repository root")
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()

    errors: list[str] = []
    checked = 0
    checked += check_docs(root, errors)
    checked += check_runtime_state_ignores(root, errors)
    checked += check_usage_matrix(root, errors)
    checked += check_recipes(root, errors)
    checked += check_front_door_parity(root, errors)
    checked += check_autobuild_recipe_routes_plan_audit(root, errors)
    checked += check_doc_links(root, errors)
    checked += check_ci(root, errors)
    checked += check_comparison_freshness(root, errors)
    checked += check_supported_surface_claims(root, errors)
    checked += check_benchmark_inventory(root, errors)
    checked += check_live_eval_provenance(root, errors)
    checked += check_benchmark_recency(root, errors)

    if errors:
        print(
            f"product-layer: FAIL - {len(errors)} issue(s) across {checked} check(s):",
            file=sys.stderr,
        )
        for error in errors:
            print(f"  x {error}", file=sys.stderr)
        return 1
    print(f"product-layer: OK - {checked} check(s), 0 issues.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
