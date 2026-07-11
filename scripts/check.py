#!/usr/bin/env python3
"""
Lint plugin + managed-agent-cookbook manifests and verify cross-file references.

Checks:
  1. Every *.yaml under managed-agent-cookbooks/ parses.
  2. Every marketplace.json / plugin.json / steering-examples.json parses.
  3. Every skill (plugins/*/skills/*/SKILL.md) has `name:` + `description:`.
  3b. Every plugin-shipped custom agent (plugins/*/agents/*.md) has `name:` +
      `description:`, matches its filename, and declares a valid leaf toolset.
  4. Every system.file, skills[].path, callable_agents[].manifest in a cookbook
     agent.yaml / subagent yaml resolves to an existing file/dir.
  4c. Every marketplace.json plugin `source` resolves to a dir with a plugin.json.
  4d. Every plugins/*/.claude-plugin/plugin.json carries the install-point trust
      signals — homepage, repository, license, and non-empty keywords — so a
      shipped plugin can never regress to an anonymous name/version stub.
  5. Designated byte-identical script pairs (deliberately forked substrate-
     independent gates) have not drifted.
  5b. patch-lint.py's cross-skill import of spec-lint.py resolves — the target
     exists and the computed path literal is intact.
  5c. No UNREGISTERED fork exists: any plugins/*/skills/*/scripts/ file whose
     basename matches a fork-manifest canonical's basename must be that
     canonical or one of its registered copies — a hand-copied gate script
     that skipped fork-manifest.json fails here instead of drifting silently.
  5d. Hook self-integrity: every hooks/*.py + hooks.json matches the shipped
     hooks/integrity-manifest.json (via scripts/hook_manifest.py --check), so a
     guard edited without refreshing the manifest is CI-red. The SessionStart
     hook hooks/hook-integrity.py verifies the same manifest at runtime.
  6. Every managed-agent-cookbooks/<slug>/ has agent.yaml, README.md,
     steering-examples.json.
  7. plugins/*/model-policy.json is consistent with the skill corpus: every
     skill has an entry, every entry names a real skill, and a skill may set
     binding `model:`/`effort:` frontmatter only if its entry is down_routable.
  8. The README skill catalog and documented skill/agent counts match the
     core-engineering skill corpus on disk.
  9. The human-authored corpus passes scripts/corpus_lint.py: no stale public
     names, no unknown `/ce-*` references, required skill skeleton headings, and
     valid `${CLAUDE_SKILL_DIR}/...` companion-file references.
 10. Enterprise hardening controls pass scripts/supply_chain_check.py: pinned
     CI actions, checksum-verified secret scanning, release/delivery
     supply-chain evidence prompts, adversarial eval fixtures, and the control
     map cannot silently drift.
 11. Managed-agent controls pass scripts/managed_agent_check.py: cookbook
     inventory, steering examples, orchestration docs, and handoff allowlists
     cannot drift.
 12. Product-layer controls pass scripts/product_layer_check.py: first-run docs,
     workflow recipes, usage-matrix coverage, and CI visibility cannot drift.
 13. The skill corpus passes scripts/authoring_check.py: the closed HITL-suffix
     enum, gate-label sanity, concept canon, router-cluster contrastive
     clauses, and the SKILL.md / description caps cannot drift.
 14. plugins/*/merge-policy.json (the agent-agnostic merge bar consumed by
     scripts/gate_runner.py) is structurally sound: gate scripts resolve
     inside the plugin, arg placeholders come from the closed set, every bar's
     gates are registered, validity stays in the closed vocabulary (no
     'none'), and no registered gate is dead.
 15. The enforcement counts the product docs quote are DERIVED, never
     asserted: this run's own `checked` counter, the authoring_check.py
     check count, and the collected tests/ suite size must equal the
     committed docs/enforcement-counts.json. `--write-counts` refreshes that
     file AND rewrites the three doc claim sites (README.md,
     docs/COMPARISON.md, docs/BENCHMARKS.md) from the derived numbers.

A check whose glob root is absent fails LOUDLY rather than matching zero paths
and going silently green — a renamed/moved layout can never disable a check.

Exit 0 if clean, 1 otherwise (2 if a required dependency is missing). Requires: pyyaml.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

# --no-install-hooks: skip the git-config side-effect (for CI, which checks out
# clean and should not mutate config). Hand-parsed so check.py keeps zero
# argparse surface and a bare `python3 scripts/check.py` is unchanged.
INSTALL_HOOKS = "--no-install-hooks" not in sys.argv
# --write-counts: instead of comparing docs/enforcement-counts.json against
# this run's derived enforcement counts (§15), rewrite it — and the three doc
# claim sites — to match. Hand-parsed for the same reason as above.
WRITE_COUNTS = "--write-counts" in sys.argv

ROOT = Path(__file__).resolve().parents[1]
PLUGINS = ROOT / "plugins"
MANAGED = ROOT / "managed-agent-cookbooks"
errors: list[str] = []
checked = 0


def ensure_hooks_installed() -> None:
    """Point git at .githooks so the version-bump pre-commit runs.

    Native equivalent of Husky's `prepare`, piggybacked on the script
    everyone already runs before committing. Best-effort: never fatal.
    """
    want = ".githooks"
    try:
        cur = subprocess.run(
            ["git", "-C", str(ROOT), "config", "--get", "core.hooksPath"],
            capture_output=True, text=True,
        ).stdout.strip()
        if cur != want:
            subprocess.run(
                ["git", "-C", str(ROOT), "config", "core.hooksPath", want],
                check=True, capture_output=True,
            )
            print(f"[check.py] installed git hooks (core.hooksPath -> {want})")
    except (subprocess.SubprocessError, OSError):
        pass  # not a git checkout / git unavailable — ignore


# Install hooks before anything that can exit early (e.g. missing pyyaml),
# so a fresh checkout still gets the version-bump hook wired up.
if INSTALL_HOOKS:
    ensure_hooks_installed()

try:
    import yaml
except ImportError:
    print("ERROR: requires pyyaml (pip install pyyaml)", file=sys.stderr)
    sys.exit(2)


def err(msg: str) -> None:
    errors.append(msg)


def rel(p: Path) -> str:
    return str(p.relative_to(ROOT))


def require(paths: list, what: str) -> list:
    """Fail loudly if a check's glob root matched nothing.

    A check that silently iterates zero paths is worse than a missing check:
    it reads as green. Any layout rename that empties a glob trips this.
    """
    if not paths:
        err(f"structure: no files matched {what} — did the repository layout change?")
    return paths


# --- 1. YAML parse ----------------------------------------------------------
for yml in require(sorted(MANAGED.rglob("*.yaml")), "managed-agent-cookbooks/**/*.yaml"):
    checked += 1
    try:
        with open(yml) as f:
            yaml.safe_load(f)
    except yaml.YAMLError as e:
        err(f"YAML parse: {rel(yml)}: {e}")

# --- 2. JSON parse ----------------------------------------------------------
json_globs = [
    ".claude-plugin/marketplace.json",
    "plugins/**/.claude-plugin/plugin.json",
    "managed-agent-cookbooks/*/steering-examples.json",
]
for pat in json_globs:
    for jf in sorted(ROOT.glob(pat)):
        checked += 1
        try:
            json.loads(jf.read_text())
        except json.JSONDecodeError as e:
            err(f"JSON parse: {rel(jf)}: {e}")

# --- 2b. plugin hook config parses -------------------------------------------
# A syntactically-broken hooks.json is silently skipped by the harness, which
# would disable EVERY hook it registers (git-guard + env-guard) with no symptom
# — the fail-open failure mode applied to the hooks themselves. Parse it loudly,
# require()-wrapped so a moved/renamed hooks dir can never empty the check.
for hj in require(sorted(PLUGINS.glob("*/hooks/hooks.json")), "plugins/*/hooks/hooks.json"):
    checked += 1
    try:
        json.loads(hj.read_text())
    except json.JSONDecodeError as e:
        err(f"JSON parse: {rel(hj)}: {e}")


# --- 3. skill frontmatter ---------------------------------------------------
def frontmatter(md: Path):
    text = md.read_text()
    if not text.startswith("---"):
        err(f"frontmatter: {rel(md)}: missing leading ---")
        return None
    try:
        _, fm, _ = text.split("---", 2)
        return yaml.safe_load(fm) or {}
    except (ValueError, yaml.YAMLError) as e:
        err(f"frontmatter: {rel(md)}: {e}")
        return None


for md in require(sorted(PLUGINS.glob("*/skills/*/SKILL.md")), "plugins/*/skills/*/SKILL.md"):
    checked += 1
    meta = frontmatter(md)
    if meta is not None:
        for k in ("name", "description"):
            if k not in meta:
                err(f"frontmatter: {rel(md)}: missing '{k}'")
        name = meta.get("name")
        if isinstance(name, str) and name != md.parent.name:
            err(f"frontmatter: {rel(md)}: name '{name}' must match skill directory '{md.parent.name}'")
        if md.parents[2].name == "core-engineering" and not md.parent.name.startswith("ce-"):
            err(f"frontmatter: {rel(md)}: core-engineering skill directory must start with 'ce-'")


# --- 3b. plugin-shipped custom agent frontmatter ----------------------------
def parse_agent_tools(value) -> tuple[set[str], str | None]:
    if value is None:
        return set(), None
    if isinstance(value, str):
        tools = {x.strip() for x in value.split(",") if x.strip()}
        return tools, None if tools else "tools must name at least one tool"
    if isinstance(value, list):
        tools = set()
        for item in value:
            if not isinstance(item, str) or not item.strip():
                return set(), "tools list entries must be non-empty strings"
            tools.add(item.strip())
        return tools, None if tools else "tools must name at least one tool"
    return set(), "tools must be a comma-separated string or list"


for md in require(sorted(PLUGINS.glob("*/agents/*.md")), "plugins/*/agents/*.md"):
    checked += 1
    meta = frontmatter(md)
    if meta is None:
        continue
    for k in ("name", "description"):
        if k not in meta:
            err(f"agent: {rel(md)}: missing '{k}'")
    name = meta.get("name")
    if isinstance(name, str) and name != md.stem:
        err(f"agent: {rel(md)}: name '{name}' must match filename '{md.stem}'")
    description = meta.get("description")
    if not isinstance(description, str) or not description.strip():
        err(f"agent: {rel(md)}: description must be a non-empty string")
    tools, tool_error = parse_agent_tools(meta.get("tools"))
    if tool_error:
        err(f"agent: {rel(md)}: {tool_error}")
    if "Task" in tools:
        err(
            f"agent: {rel(md)}: plugin-shipped agents must be leaf agents; "
            f"omit Task unless check.py is updated with an explicit orchestrator exception"
        )


# --- 4. reference resolution -----------------------------------------------
def check_refs(yml: Path) -> None:
    try:
        data = yaml.safe_load(yml.read_text()) or {}
    except yaml.YAMLError:
        return  # already reported above
    base = yml.parent

    sys_spec = data.get("system")
    if isinstance(sys_spec, dict) and "file" in sys_spec:
        p = (base / sys_spec["file"]).resolve()
        if not p.is_file():
            err(f"ref: {rel(yml)}: system.file -> {sys_spec['file']} (not found)")

    for s in data.get("skills") or []:
        if isinstance(s, dict) and "path" in s:
            p = (base / s["path"]).resolve()
            if not p.exists():
                err(f"ref: {rel(yml)}: skills.path -> {s['path']} (not found)")
        if isinstance(s, dict) and "from_plugin" in s:
            p = (base / s["from_plugin"]).resolve()
            if not (p / "skills").is_dir():
                err(f"ref: {rel(yml)}: skills.from_plugin -> {s['from_plugin']} (no skills/ dir)")

    for c in data.get("callable_agents") or []:
        if isinstance(c, dict) and "manifest" in c:
            p = (base / c["manifest"]).resolve()
            if not p.is_file():
                err(f"ref: {rel(yml)}: callable_agents.manifest -> {c['manifest']} (not found)")


for yml in sorted(MANAGED.rglob("*.yaml")):
    check_refs(yml)

# --- 4c. marketplace source paths resolve ----------------------------------
mp = ROOT / ".claude-plugin" / "marketplace.json"
for p in json.loads(mp.read_text()).get("plugins", []):
    src = (ROOT / p["source"]).resolve()
    if not (src / ".claude-plugin" / "plugin.json").is_file():
        err(f"marketplace: {p['name']} source -> {p['source']} (no plugin.json)")

# --- 4d. plugin.json install-point trust signals ---------------------------
# Every shipped plugin manifest must carry the install-point trust signals —
# homepage, repository, license, and non-empty keywords — so a plugin can never
# regress to an anonymous name/version/description stub, and so any new plugin
# (product-discovery, etc.) inherits the same bar the day it lands. These are
# the standard plugin.json fields the official strict linter accepts;
# .github/workflows/plugin-validate.yml runs that linter over the same manifests
# at a pinned CLI version, so the schema half is a CI fact — this check guards
# the completeness half (the fields being present at all).
for pj in require(sorted(PLUGINS.glob("*/.claude-plugin/plugin.json")),
                  "plugins/*/.claude-plugin/plugin.json"):
    checked += 1
    try:
        pmeta = json.loads(pj.read_text())
    except json.JSONDecodeError:
        continue  # malformed JSON already reported in §2
    for k in ("homepage", "repository", "license"):
        v = pmeta.get(k)
        if not isinstance(v, str) or not v.strip():
            err(f"plugin: {rel(pj)}: missing/empty '{k}' (install-point trust signal)")
    kw = pmeta.get("keywords")
    if not isinstance(kw, list) or not kw or not all(
        isinstance(x, str) and x.strip() for x in kw
    ):
        err(f"plugin: {rel(pj)}: 'keywords' must be a non-empty list of non-empty strings")

# --- 5. forked-gate byte identity ------------------------------------------
# Some substrate-independent gates are deliberately DUPLICATED on disk: each
# skill must be able to run its own copy without depending on a sibling skill
# being reachable (the Managed-Agent cookbook bundles skills separately, and
# ${CLAUDE_PLUGIN_ROOT} is only guaranteed in hook/MCP contexts — not in skill
# Bash calls — so a share-by-reference path is not guaranteed across
# substrates). Duplication is correct; silent DRIFT is the bug. Assert
# byte-identity so a fork can never diverge into a behavioral difference
# unnoticed (the auto-build / spec spec-lint.py pair drifted exactly this way
# once — H3 guard missing on one side — which is why this gate exists).
# The canonical→copies registry is MACHINE-READABLE: it lives in
# plugins/core-engineering/fork-manifest.json (one reviewable place to add a
# consumer), and `python3 scripts/fork_sync.py --write` re-syncs the copies.
# supply_chain_check.py re-checks the dependency-gate forks from the same
# manifest, so no hand-maintained pair list exists anywhere.
import filecmp  # noqa: E402

FORK_MANIFEST = ROOT / "plugins/core-engineering/fork-manifest.json"
_forks: list = []
if not FORK_MANIFEST.is_file():
    err(f"identity: missing {rel(FORK_MANIFEST)} — the forked-gate registry is gone?")
else:
    try:
        _forks = json.loads(FORK_MANIFEST.read_text(encoding="utf-8")).get("forks", [])
    except json.JSONDecodeError as exc:
        _forks = []
        err(f"identity: {rel(FORK_MANIFEST)} is not valid JSON: {exc}")
    if not _forks:
        err(f"identity: {rel(FORK_MANIFEST)} registers no forks — registry emptied?")
    for _fork in _forks:
        _canonical_rel = _fork.get("canonical", "")
        _canonical = ROOT / _canonical_rel
        _copies = _fork.get("copies") or []
        if not _canonical.is_file():
            err(f"identity: canonical {_canonical_rel} missing from disk")
            continue
        if not _copies:
            err(f"identity: {_canonical_rel} registers no copies — dead manifest entry?")
        for _copy_rel in _copies:
            _copy = ROOT / _copy_rel
            if not _copy.is_file():
                err(
                    f"identity: registered copy {_copy_rel} missing — "
                    f"re-sync with `python3 scripts/fork_sync.py --write`"
                )
                continue
            checked += 1
            if not filecmp.cmp(_canonical, _copy, shallow=False):
                err(
                    f"identity: {_copy_rel} has drifted from {_canonical_rel} — "
                    f"re-sync with `python3 scripts/fork_sync.py --write` "
                    f"(forked gate must stay byte-identical)"
                )

# --- 5c. unregistered-fork detection -----------------------------------------
# §5 only guards files REGISTERED in fork-manifest.json. A contributor who
# hand-copies a canonical (say spec-lint.py) into a new skill's scripts/ dir
# without registering it creates an unguarded fork that drifts invisibly — the
# exact incident class §5 was born from. So: any skill script whose basename
# matches a registered canonical's basename must be that canonical or one of
# its registered copies. Nothing is exempt — a legitimately different
# same-named script must be renamed (that ambiguity is the hazard).
_registered_fork_paths: set[str] = set()
_canonical_by_basename: dict[str, str] = {}
for _fork in _forks:
    _canonical_rel = _fork.get("canonical", "")
    if _canonical_rel:
        _registered_fork_paths.add(_canonical_rel)
        _canonical_by_basename[Path(_canonical_rel).name] = _canonical_rel
    for _copy_rel in _fork.get("copies") or []:
        _registered_fork_paths.add(_copy_rel)
_skill_scripts = require(
    sorted(
        p for p in PLUGINS.glob("*/skills/*/scripts/*")
        if p.is_file() and "__pycache__" not in p.parts
    ),
    "plugins/*/skills/*/scripts/*",
)
for _script in _skill_scripts:
    _canonical_rel = _canonical_by_basename.get(_script.name)
    if _canonical_rel is None:
        continue
    checked += 1
    if rel(_script) not in _registered_fork_paths:
        err(
            f"identity: {rel(_script)} is an unregistered fork of "
            f"{_canonical_rel}: add it to fork-manifest.json and re-sync "
            f"with `python3 scripts/fork_sync.py --write`, or rename it"
        )

# --- 5b. cross-skill import path (patch-lint imports spec-lint) -------------
# patch's patch-lint.py IMPORTS ce-spec's spec-lint.py (single
# source for H1-H4 — see patch-lint's load_spec_lint), via a path computed in
# source: parents[2] / "ce-spec" / "scripts" / "spec-lint.py". That import
# is NOT a byte-twin, so IDENTICAL_PAIRS can't guard it — a layout rename would
# break it silently. Assert the target resolves AND patch-lint still computes
# the path it expects.
PATCH_LINT = ROOT / "plugins/core-engineering/skills/ce-patch/scripts/patch-lint.py"
SPEC_LINT_TARGET = ROOT / "plugins/core-engineering/skills/ce-spec/scripts/spec-lint.py"
if not PATCH_LINT.is_file():
    err(f"import: expected patch-lint at {rel(PATCH_LINT)} (not found) — did the layout change?")
else:
    checked += 1
    if not SPEC_LINT_TARGET.is_file():
        err(
            f"import: {rel(PATCH_LINT)} imports spec-lint.py but "
            f"{rel(SPEC_LINT_TARGET)} is missing"
        )
    if '"ce-spec" / "scripts" / "spec-lint.py"' not in PATCH_LINT.read_text():
        err(
            f"import: {rel(PATCH_LINT)} no longer computes the spec-lint.py path "
            f'(\'"ce-spec" / "scripts" / "spec-lint.py"\') — the cross-skill '
            f"import may have drifted; re-point it or update this guard"
        )

# --- 5d. hook self-integrity manifest freshness ------------------------------
# The guards cannot detect their own subversion — an in-session edit of
# env-guard.py silently disarms it. hooks/integrity-manifest.json records the
# sha256 of every hooks/*.py + hooks.json; the SessionStart hook
# hooks/hook-integrity.py verifies it at runtime, and this section enforces its
# freshness at commit time (the version-bump-hook pattern: a hook edited without
# `python3 scripts/hook_manifest.py --write` refreshing the manifest goes
# CI-red, so any drift is auditable in the reviewable diff — tamper-evidence,
# not tamper-proofing). Run the same `--check` mode the CI freshness gate uses.
HOOK_MANIFEST_SCRIPT = ROOT / "scripts" / "hook_manifest.py"
if not HOOK_MANIFEST_SCRIPT.is_file():
    err(f"hook-integrity: missing {rel(HOOK_MANIFEST_SCRIPT)} — the hook "
        f"self-integrity freshness gate is gone?")
else:
    checked += 1
    _hm = subprocess.run(
        [sys.executable, str(HOOK_MANIFEST_SCRIPT), "--check"],
        capture_output=True, text=True,
    )
    if _hm.returncode != 0:
        for _line in (_hm.stderr + _hm.stdout).splitlines():
            _line = _line.strip()
            if _line:
                err(f"hook-integrity: {_line}")

# --- 6. required files per managed-agent-cookbook --------------------------
for d in sorted(MANAGED.iterdir()):
    if not d.is_dir():
        continue
    for req in ("agent.yaml", "README.md", "steering-examples.json"):
        if not (d / req).is_file():
            err(f"missing: {rel(d)}/{req}")

# --- 7. model-policy <-> skill-corpus consistency ----------------------------
# plugins/<p>/model-policy.json is the machine-readable model-tier policy (the
# CLAUDE.md prose policy, encoded). Two-way completeness: every skill has an
# entry, every entry names a real skill. Dual-truth guard: a skill may carry
# binding `model:`/`effort:` frontmatter ONLY if its policy entry says
# down_routable, so the policy file and the frontmatter can never silently
# disagree about who is allowed to route down. The plugin set is derived from
# the skills/ dirs themselves (not the policy glob), so a plugin that ships
# skills but forgets a model-policy.json is caught, not skipped.
plugins_with_skills = sorted(
    p.parent for p in PLUGINS.glob("*/skills") if p.is_dir()
)
require(plugins_with_skills, "plugins/*/skills")
for plugin_dir in plugins_with_skills:
    policy_file = plugin_dir / "model-policy.json"
    skills_dir = plugin_dir / "skills"
    skill_names = {p.name for p in skills_dir.iterdir() if p.is_dir()}
    if not policy_file.is_file():
        err(f"model-policy: {rel(plugin_dir)} ships skills/ but has no "
            f"model-policy.json — every skill plugin needs one")
        continue
    checked += 1
    try:
        policy = json.loads(policy_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as e:
        err(f"model-policy: {rel(policy_file)}: could not read/parse: {e}")
        continue
    if not isinstance(policy, dict):
        err(f"model-policy: {rel(policy_file)}: top level must be a JSON object")
        continue
    if policy.get("schema_version") != 1:
        err(f"model-policy: {rel(policy_file)}: schema_version must be 1")
    entries = policy.get("skills")
    if not isinstance(entries, dict):
        err(f"model-policy: {rel(policy_file)}: missing 'skills' object")
        continue

    for missing in sorted(skill_names - set(entries)):
        err(f"model-policy: {rel(policy_file)}: skill '{missing}' has no entry")
    for orphan in sorted(set(entries) - skill_names):
        err(f"model-policy: {rel(policy_file)}: entry '{orphan}' names no existing skill")

    for name, entry in sorted(entries.items()):
        if not isinstance(entry, dict):
            err(f"model-policy: {rel(policy_file)}: '{name}' entry must be an object")
            continue
        tier = entry.get("tier")
        down = entry.get("down_routable")
        if tier not in ("strong", "cheap-ok"):
            err(f"model-policy: {rel(policy_file)}: '{name}' tier must be "
                f"'strong' or 'cheap-ok' (got {tier!r})")
        if not isinstance(down, bool):
            err(f"model-policy: {rel(policy_file)}: '{name}' down_routable must be a bool")
        if down is True and tier != "cheap-ok":
            err(f"model-policy: {rel(policy_file)}: '{name}' is down_routable "
                f"but tier is not 'cheap-ok' — a contradiction")

    # tier_patterns: the runtime attestation buckets. hooks/model-attest.py
    # records which model ACTUALLY executed; ce-retro maps that id through these
    # substring lists to surface any gate stage that ran below its policy tier.
    # Two-way, so the static tier vocabulary and the runtime matcher can never
    # drift: (a) every tier a skill entry uses must have a non-empty pattern
    # list, and (b) tier_patterns may not name a tier outside the closed
    # vocabulary. Underscore-prefixed keys are inline comments, skipped.
    VALID_TIERS = ("strong", "cheap-ok")
    patterns = policy.get("tier_patterns")
    if not isinstance(patterns, dict):
        err(f"model-policy: {rel(policy_file)}: missing 'tier_patterns' object — "
            f"every tier a skill uses needs a runtime model-id pattern list so "
            f"the tier promise is auditable at runtime, not only at commit time")
    else:
        checked += 1
        pattern_tiers = {k for k in patterns if not k.startswith("_")}
        used_tiers = {
            e.get("tier") for e in entries.values()
            if isinstance(e, dict) and e.get("tier") in VALID_TIERS
        }
        for tier in sorted(used_tiers):
            pats = patterns.get(tier)
            if not (isinstance(pats, list) and pats
                    and all(isinstance(p, str) and p for p in pats)):
                err(f"model-policy: {rel(policy_file)}: tier '{tier}' is used by a "
                    f"skill entry but tier_patterns has no non-empty string list "
                    f"for it — model-attest records can't be mapped to it")
        for tier in sorted(pattern_tiers - set(VALID_TIERS)):
            err(f"model-policy: {rel(policy_file)}: tier_patterns names unknown "
                f"tier '{tier}' (valid tiers: {', '.join(VALID_TIERS)})")

    # Dual-truth guard, skill side: a binding frontmatter needs policy consent.
    for skill_md in sorted(skills_dir.glob("*/SKILL.md")):
        meta = frontmatter(skill_md)
        if not isinstance(meta, dict):
            continue  # parse problems already reported by check 3
        binds = [k for k in ("model", "effort") if k in meta]
        if not binds:
            continue
        entry = entries.get(skill_md.parent.name)
        if not (isinstance(entry, dict) and entry.get("down_routable") is True):
            err(
                f"model-policy: {rel(skill_md)} sets {'/'.join(binds)} frontmatter "
                f"but {rel(policy_file)} does not mark it down_routable — "
                f"update the policy (a reviewable decision) before binding a tier"
            )

# --- 8. README / HOW skill catalog drift ------------------------------------
# The README is the adoption front door. It used to drift behind the actual
# workflow corpus (23 documented, 27 shipped), which made install-time discovery
# worse precisely when new users most needed orientation. Keep this check
# intentionally mechanical: derive the inventory from skill directories, then make
# README's bounded catalog block match exactly. The docs must also state the
# shipped skill/agent counts so plugin-surface changes are visible.
CORE = PLUGINS / "core-engineering"
README = ROOT / "README.md"
HOW = ROOT / "docs" / "HOW-IT-WORKS.md"
CATALOG_START = "<!-- skill-catalog:start -->"
CATALOG_END = "<!-- skill-catalog:end -->"


def skill_invocation(plugin_dir: Path, skill_md: Path) -> str:
    return f"/{skill_md.parent.name}"


if CORE.is_dir():
    skill_files = require(sorted((CORE / "skills").glob("*/SKILL.md")),
                          "plugins/core-engineering/skills/*/SKILL.md")
    agent_files = require(sorted((CORE / "agents").glob("*.md")),
                          "plugins/core-engineering/agents/*.md")
    # The bounded README catalog lists every marketplace plugin's skills (the
    # union), so a second plugin's skills stay in-catalog. The headline
    # "{skill_count} skills" needle below stays core-scoped — it describes
    # core-engineering specifically (a second plugin adds its own phrasing).
    all_skill_files = sorted(PLUGINS.glob("*/skills/*/SKILL.md"))
    expected_skills = {skill_invocation(p.parents[2], p) for p in all_skill_files}
    skill_count = len(skill_files)
    agent_count = len(agent_files)
    agent_phrase = (
        f"{agent_count} plugin-shipped custom agent"
        if agent_count == 1
        else f"{agent_count} plugin-shipped custom agents"
    )

    for doc in (README, HOW):
        if not doc.is_file():
            err(f"catalog: expected {rel(doc)} to exist")
            continue
        checked += 1
        text = doc.read_text(encoding="utf-8")
        if f"{skill_count} skills" not in text:
            err(f"catalog: {rel(doc)} does not mention current skill count "
                f"'{skill_count} skills'")
        if agent_phrase not in text:
            err(f"catalog: {rel(doc)} does not mention current agent count "
                f"'{agent_phrase}'")

    if README.is_file():
        text = README.read_text(encoding="utf-8")
        if CATALOG_START not in text or CATALOG_END not in text:
            err(f"catalog: {rel(README)} missing {CATALOG_START} / {CATALOG_END} block")
        else:
            checked += 1
            block = text.split(CATALOG_START, 1)[1].split(CATALOG_END, 1)[0]
            listed = re.findall(r"`(/ce-[^`]+)`", block)
            listed_set = set(listed)
            duplicate = sorted({x for x in listed if listed.count(x) > 1})
            missing = sorted(expected_skills - listed_set)
            extra = sorted(listed_set - expected_skills)
            if duplicate:
                err(f"catalog: {rel(README)} skill catalog duplicates: "
                    f"{', '.join(duplicate)}")
            if missing:
                err(f"catalog: {rel(README)} skill catalog missing skill(s): "
                    f"{', '.join(missing)}")
            if extra:
                err(f"catalog: {rel(README)} skill catalog lists non-existent skill(s): "
                    f"{', '.join(extra)}")

# --- 9. prose corpus lint ---------------------------------------------------
CORPUS_LINT = ROOT / "scripts" / "corpus_lint.py"
if not CORPUS_LINT.is_file():
    err(f"corpus-lint: expected {rel(CORPUS_LINT)} to exist")
else:
    checked += 1
    res = subprocess.run(
        [sys.executable, str(CORPUS_LINT), "--root", str(ROOT)],
        capture_output=True,
        text=True,
    )
    if res.returncode != 0:
        lines = (res.stderr or res.stdout).splitlines()
        for line in lines:
            if line.strip():
                err(f"corpus-lint: {line.strip()}")

# --- 10. enterprise hardening drift ----------------------------------------
SUPPLY_CHAIN_CHECK = ROOT / "scripts" / "supply_chain_check.py"
if not SUPPLY_CHAIN_CHECK.is_file():
    err(f"supply-chain: expected {rel(SUPPLY_CHAIN_CHECK)} to exist")
else:
    checked += 1
    res = subprocess.run(
        [sys.executable, str(SUPPLY_CHAIN_CHECK), "--root", str(ROOT)],
        capture_output=True,
        text=True,
    )
    if res.returncode != 0:
        lines = (res.stderr or res.stdout).splitlines()
        for line in lines:
            if line.strip():
                err(f"supply-chain: {line.strip()}")

# --- 11. managed-agent drift -----------------------------------------------
MANAGED_AGENT_CHECK = ROOT / "scripts" / "managed_agent_check.py"
if not MANAGED_AGENT_CHECK.is_file():
    err(f"managed-agent: expected {rel(MANAGED_AGENT_CHECK)} to exist")
else:
    checked += 1
    res = subprocess.run(
        [sys.executable, str(MANAGED_AGENT_CHECK), "--root", str(ROOT)],
        capture_output=True,
        text=True,
    )
    if res.returncode != 0:
        lines = (res.stderr or res.stdout).splitlines()
        for line in lines:
            if line.strip():
                err(f"managed-agent: {line.strip()}")

# --- 12. product-layer drift ------------------------------------------------
PRODUCT_LAYER_CHECK = ROOT / "scripts" / "product_layer_check.py"
if not PRODUCT_LAYER_CHECK.is_file():
    err(f"product-layer: expected {rel(PRODUCT_LAYER_CHECK)} to exist")
else:
    checked += 1
    res = subprocess.run(
        [sys.executable, str(PRODUCT_LAYER_CHECK), "--root", str(ROOT)],
        capture_output=True,
        text=True,
    )
    if res.returncode != 0:
        lines = (res.stderr or res.stdout).splitlines()
        for line in lines:
            if line.strip():
                err(f"product-layer: {line.strip()}")

# --- 13. authoring-standard conformance -------------------------------------
AUTHORING_CHECK = ROOT / "scripts" / "authoring_check.py"
AUTHORING_STDOUT = ""  # stashed for §15's authoring-check count derivation
if not AUTHORING_CHECK.is_file():
    err(f"authoring: expected {rel(AUTHORING_CHECK)} to exist")
else:
    checked += 1
    res = subprocess.run(
        [sys.executable, str(AUTHORING_CHECK), "--root", str(ROOT)],
        capture_output=True,
        text=True,
    )
    AUTHORING_STDOUT = res.stdout or ""
    if res.returncode != 0:
        lines = (res.stderr or res.stdout).splitlines()
        for line in lines:
            if line.strip():
                err(f"authoring: {line.strip()}")

# --- 14. merge-policy lint ---------------------------------------------------
# plugins/<p>/merge-policy.json is the agent-agnostic merge bar consumed by
# scripts/gate_runner.py (which re-validates the same rules at load time so an
# adopter-side --policy override is held to the identical standard). Structural
# rules: gate scripts must be relative, '..'-free, and resolve to real files
# INSIDE the plugin; arg placeholders come from a closed set; every bar
# (defaults + each change class) requires >= 1 registered gate; validity stays
# inside the closed vocabulary; and two-way completeness — a registered gate
# nothing references is dead weight ('remove it or use it'). Presence rule:
# a plugin shipping ce-auto-build must carry a merge bar.
# The merge-policy vocabulary and duplicate-key hook are imported from the
# runner that CONSUMES the policy — gate_runner.py is the single source of truth,
# so a placeholder or validity term added there updates this validator with no
# second edit and no drift (gate_runner is stdlib-only; same import shape as
# eval_run→eval_check). Put this script's own dir on sys.path first so the
# import resolves whether check.py is run as `scripts/check.py` or `-m
# scripts.check`. The alias keeps the section's local names intact.
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
from gate_runner import (  # noqa: E402 — deliberate: import a sibling script by name
    PLACEHOLDERS as MERGE_PLACEHOLDERS,
    VALIDITY_VOCAB as MERGE_VALIDITY_VOCAB,
    SPEC_LINT_SCOPE_VOCAB as MERGE_SPEC_LINT_SCOPE_VOCAB,
    PLACEHOLDER_RE as MERGE_PLACEHOLDER_RE,
    _reject_duplicate_keys as _merge_reject_duplicate_keys,
    _validate_class_rules as _merge_validate_class_rules,
)


def lint_merge_policy(policy_file: Path) -> None:
    global checked
    plugin_dir = policy_file.parent
    checked += 1
    try:
        policy = json.loads(policy_file.read_text(encoding="utf-8"),
                            object_pairs_hook=_merge_reject_duplicate_keys)
    except (ValueError, OSError) as e:  # ValueError covers JSONDecodeError,
        # UnicodeDecodeError, and the duplicate-key rejection above
        err(f"merge-policy: {rel(policy_file)}: could not read/parse: {e}")
        return
    if not isinstance(policy, dict):
        err(f"merge-policy: {rel(policy_file)}: top level must be a JSON object")
        return
    if policy.get("schema_version") != 1:
        err(f"merge-policy: {rel(policy_file)}: schema_version must be 1")

    gates = policy.get("gates")
    if not (isinstance(gates, dict) and gates):
        err(f"merge-policy: {rel(policy_file)}: 'gates' must be a non-empty object")
        gates = {}
    for gate_id, gate in sorted(gates.items()):
        if not isinstance(gate, dict):
            err(f"merge-policy: {rel(policy_file)}: gate '{gate_id}' must be an object")
            continue
        script = gate.get("script")
        if not (isinstance(script, str) and script):
            err(f"merge-policy: {rel(policy_file)}: gate '{gate_id}' 'script' "
                f"must be a non-empty string")
        else:
            script_path = Path(script)
            if script_path.is_absolute() or ".." in script_path.parts:
                err(f"merge-policy: {rel(policy_file)}: gate '{gate_id}' script "
                    f"'{script}' must be plugin-relative with no '..'")
            else:
                resolved = (plugin_dir / script_path).resolve()
                if not resolved.is_relative_to(plugin_dir.resolve()):
                    err(f"merge-policy: {rel(policy_file)}: gate '{gate_id}' "
                        f"script '{script}' escapes the plugin dir")
                elif not resolved.is_file():
                    err(f"merge-policy: {rel(policy_file)}: gate '{gate_id}' "
                        f"script '{script}' not found under {rel(plugin_dir)}")
        if not (isinstance(gate.get("proves"), str) and gate.get("proves")):
            err(f"merge-policy: {rel(policy_file)}: gate '{gate_id}' 'proves' "
                f"must be a non-empty string")
        args = gate.get("args")
        if not (isinstance(args, list) and all(isinstance(a, str) for a in args)):
            err(f"merge-policy: {rel(policy_file)}: gate '{gate_id}' 'args' "
                f"must be a list of strings")
            args = []
        for arg in args:
            for token in MERGE_PLACEHOLDER_RE.findall(arg):
                if token not in MERGE_PLACEHOLDERS:
                    err(f"merge-policy: {rel(policy_file)}: gate '{gate_id}' "
                        f"unknown placeholder {{{token}}} (closed set: "
                        f"{', '.join(sorted(MERGE_PLACEHOLDERS))})")

    classes = policy.get("change_classes")
    if not (isinstance(classes, dict) and classes):
        err(f"merge-policy: {rel(policy_file)}: 'change_classes' must be a "
            f"non-empty object")
        classes = {}
    defaults = policy.get("defaults")
    if not isinstance(defaults, dict):
        err(f"merge-policy: {rel(policy_file)}: missing 'defaults' object "
            f"(the fail-safe bar used when no change class is named)")
        defaults = None

    referenced: set[str] = set()
    bars = ([("defaults", defaults)] if defaults is not None else []) + sorted(classes.items())
    for bar_name, bar in bars:
        if not isinstance(bar, dict):
            err(f"merge-policy: {rel(policy_file)}: bar '{bar_name}' must be an object")
            continue
        required = bar.get("required_integrity_gates")
        if not (isinstance(required, list) and required
                and all(isinstance(g, str) for g in required)):
            err(f"merge-policy: {rel(policy_file)}: bar '{bar_name}' "
                f"'required_integrity_gates' must be a non-empty list of strings")
            required = []
        advisory = bar.get("advisory_gates", [])
        if not (isinstance(advisory, list)
                and all(isinstance(g, str) for g in advisory)):
            err(f"merge-policy: {rel(policy_file)}: bar '{bar_name}' "
                f"'advisory_gates' must be a list of strings")
            advisory = []
        for g in list(required) + list(advisory):
            if g not in gates:
                err(f"merge-policy: {rel(policy_file)}: bar '{bar_name}' "
                    f"references unregistered gate '{g}'")
            referenced.add(g)
        overlap = sorted(set(required) & set(advisory))
        if overlap:
            err(f"merge-policy: {rel(policy_file)}: bar '{bar_name}' lists "
                f"{', '.join(overlap)} as both required and advisory")
        validity = bar.get("validity")
        if validity not in MERGE_VALIDITY_VOCAB:
            err(f"merge-policy: {rel(policy_file)}: bar '{bar_name}' validity "
                f"must be one of {sorted(MERGE_VALIDITY_VOCAB)} (got "
                f"{validity!r}) — 'none' does not exist by design")

    for dead in sorted(set(gates) - referenced):
        err(f"merge-policy: {rel(policy_file)}: registered gate '{dead}' is "
            f"referenced by no bar — remove it or use it")

    # Optional cold-start scope (default 'all'; closed two-value vocabulary).
    scope = policy.get("spec_lint_scope", "all")
    if scope not in MERGE_SPEC_LINT_SCOPE_VOCAB:
        err(f"merge-policy: {rel(policy_file)}: spec_lint_scope must be one of "
            f"{sorted(MERGE_SPEC_LINT_SCOPE_VOCAB)} (got {scope!r})")

    # Optional path-based classifier — validated by the SAME shared function the
    # runner's load_policy calls, so the rule can never drift between the two
    # (a mandatory `fallback` plus every rule `class` naming a defined change
    # class; rules only SELECT AMONG validated bars). `classes` may have been
    # reset to {} above on an earlier structural error — pass what we have.
    _merge_validate_class_rules(
        policy.get("class_rules"), classes if isinstance(classes, dict) else {},
        lambda cond, msg: None if cond else err(
            f"merge-policy: {rel(policy_file)}: {msg}"))


for plugin_dir in plugins_with_skills:
    merge_policy_file = plugin_dir / "merge-policy.json"
    ships_auto_build = (plugin_dir / "skills" / "ce-auto-build").is_dir()
    if not merge_policy_file.is_file():
        if ships_auto_build:
            err(f"merge-policy: {rel(plugin_dir)} ships ce-auto-build but has "
                f"no merge-policy.json — the merge bar cannot be unshipped")
        continue
    lint_merge_policy(merge_policy_file)

# --- 15. enforcement-count derivation ----------------------------------------
# The enforcement counts the product docs quote (README.md, docs/COMPARISON.md,
# docs/BENCHMARKS.md) are DERIVED each run, never asserted:
#   repo_checks      — this script's own final `checked` counter;
#   authoring_checks — parsed from §13's authoring_check.py report;
#   tests            — unittest discovery over tests/ (collected, never run).
# The derived triple must equal the committed docs/enforcement-counts.json,
# which product_layer_check.py in turn holds the three doc claim sites to —
# so no published number can drift from measured reality without CI going red.
# `--write-counts` refreshes counts.json AND rewrites the doc claim sites
# mechanically, using the exact anchors product_layer_check keys on (imported
# from it below — one anchor set, both directions, no drift; same sibling-
# import shape as the §14 gate_runner import, so the sys.path insert above
# already covers it).
from product_layer_check import (  # noqa: E402 — deliberate sibling import
    BENCH_COUNT_ROWS,
    COUNT_CLAIM_RE,
    COUNTS_FILE_REL,
    COUNTS_KEYS,
    WRITE_COUNTS_REMEDY,
)

COUNTS_FILE = ROOT / COUNTS_FILE_REL
AUTHORING_OK_RE = re.compile(r"OK — (\d+) check\(s\)")


def derive_authoring_count() -> int | None:
    m = AUTHORING_OK_RE.search(AUTHORING_STDOUT)
    return int(m.group(1)) if m else None


def derive_test_count() -> int | None:
    """Collect (never execute) the tests/ suite in a clean subprocess.

    A subprocess keeps the ~30 test modules out of this process's import
    graph; loader.errors makes an unimportable test module a loud failure
    instead of a silently wrong count.
    """
    res = subprocess.run(
        [sys.executable, "-c",
         "import sys, unittest\n"
         "loader = unittest.TestLoader()\n"
         "suite = loader.discover(sys.argv[1])\n"
         "if loader.errors:\n"
         "    sys.stderr.write('\\n'.join(loader.errors))\n"
         "    raise SystemExit(1)\n"
         "print(suite.countTestCases())\n",
         str(ROOT / "tests")],
        capture_output=True, text=True,
    )
    out = res.stdout.strip()
    return int(out) if res.returncode == 0 and out.isdigit() else None


def renumber_claim(match: re.Match, values: tuple) -> str:
    """Rebuild a COUNT_CLAIM_RE match with fresh numbers, prose untouched."""
    out, last = [], match.start()
    for group_index, value in enumerate(values, start=1):
        out.append(match.string[last:match.start(group_index)])
        out.append(str(value))
        last = match.end(group_index)
    out.append(match.string[last:match.end()])
    return "".join(out)


def write_counts(derived: dict) -> None:
    """Rewrite counts.json + the three doc claim sites from *derived*."""
    payload = {
        "_comment": "Derived enforcement counts — regenerate with "
                    "`python3 scripts/check.py --write-counts`; never hand-edit "
                    "(check.py re-derives and compares on every run).",
        **{key: derived[key] for key in COUNTS_KEYS},
    }
    COUNTS_FILE.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    rewritten = [rel(COUNTS_FILE)]
    triple = tuple(derived[key] for key in COUNTS_KEYS)
    for doc in (ROOT / "README.md", ROOT / "docs" / "COMPARISON.md"):
        text = doc.read_text(encoding="utf-8")
        new_text, n = COUNT_CLAIM_RE.subn(lambda m: renumber_claim(m, triple), text)
        if n == 0:
            err(f"counts: {rel(doc)} has no enforcement-count claim to rewrite "
                f"('N repo checks, N authoring-conformance checks, N tests')")
            continue
        if new_text != text:
            doc.write_text(new_text, encoding="utf-8")
            rewritten.append(rel(doc))
    bench = ROOT / "docs" / "BENCHMARKS.md"
    text = bench.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    for (anchor, unit), value in zip(BENCH_COUNT_ROWS, triple):
        row_index = next((i for i, line in enumerate(lines) if anchor in line), None)
        if row_index is None:
            err(f"counts: {rel(bench)} has no {anchor} row to rewrite")
            continue
        new_row, n = re.subn(rf"(\|\s*)\d+(\s+{unit}\s*\|)",
                             rf"\g<1>{value}\g<2>", lines[row_index], count=1)
        if n == 0:
            err(f"counts: {rel(bench)} {anchor} row has no '<N> {unit}' cell to rewrite")
            continue
        lines[row_index] = new_row
    new_text = "".join(lines)
    if new_text != text:
        bench.write_text(new_text, encoding="utf-8")
        rewritten.append(rel(bench))
    print(f"[check.py] --write-counts: {', '.join(rewritten)} now record "
          f"repo_checks={triple[0]}, authoring_checks={triple[1]}, tests={triple[2]}")


_authoring_count = derive_authoring_count()
_test_count = derive_test_count()
if _authoring_count is None and not any(e.startswith("authoring:") for e in errors):
    err("counts: authoring_check.py's 'OK — N check(s)' line was unparseable — "
        "update §15's AUTHORING_OK_RE alongside its report format")
if _test_count is None:
    err("counts: unittest discovery over tests/ failed to collect — fix the "
        "import error it reported before trusting any count")

checked += 1  # the counts triple is itself a guarded surface (final counter)
if _authoring_count is not None and _test_count is not None:
    _derived = {
        "repo_checks": checked,
        "authoring_checks": _authoring_count,
        "tests": _test_count,
    }
    if WRITE_COUNTS:
        write_counts(_derived)
        # §12 judged the PRE-write docs; re-judge the rewritten ones so one
        # command converges a drifted tree to green (nothing else about the
        # product layer changed — only the sites write_counts touched).
        if PRODUCT_LAYER_CHECK.is_file():
            errors[:] = [e for e in errors if not e.startswith("product-layer:")]
            res = subprocess.run(
                [sys.executable, str(PRODUCT_LAYER_CHECK), "--root", str(ROOT)],
                capture_output=True,
                text=True,
            )
            if res.returncode != 0:
                for line in (res.stderr or res.stdout).splitlines():
                    if line.strip():
                        err(f"product-layer: {line.strip()}")
    else:
        _recorded = None
        try:
            _recorded = json.loads(COUNTS_FILE.read_text(encoding="utf-8"))
        except FileNotFoundError:
            err(f"counts: missing {rel(COUNTS_FILE)} — the enforcement counts "
                f"must be derived, never asserted; {WRITE_COUNTS_REMEDY}")
        except (OSError, ValueError) as e:
            err(f"counts: {rel(COUNTS_FILE)}: could not read/parse: {e}")
        if isinstance(_recorded, dict):
            for key in COUNTS_KEYS:
                if _recorded.get(key) != _derived[key]:
                    err(f"counts: {rel(COUNTS_FILE)} records "
                        f"{key}={_recorded.get(key)!r} but this run derived "
                        f"{_derived[key]} — {WRITE_COUNTS_REMEDY}")
        elif _recorded is not None:
            err(f"counts: {rel(COUNTS_FILE)}: top level must be a JSON object")

# --- report ----------------------------------------------------------------
if errors:
    print(f"FAIL — {len(errors)} issue(s) across {checked} file(s):\n", file=sys.stderr)
    for e in errors:
        print(f"  ✗ {e}", file=sys.stderr)
    sys.exit(1)
print(f"OK — {checked} file(s) checked, 0 issues.")
