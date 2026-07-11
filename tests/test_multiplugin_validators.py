"""WS7-T5: the validator stack iterates every ``plugins/*/skills`` dir.

These tests drop a scratch second plugin (``plugins/_probe/...``) into a temp
copy of the repo and prove each generalized validator now sees it. On the
committed single-plugin tree the same validators stay byte-identically green
(the sibling suites cover that); here we prove the generalization is real, not
vestigial — a second marketplace plugin's skills are frontmatter-checked,
model-policy-checked, authoring-linted, corpus-linted, coverage-ratcheted, and
catalog-checked exactly like core's.
"""

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

try:
    import yaml  # noqa: F401
    HAVE_YAML = True
except ImportError:
    HAVE_YAML = False

DESC = (
    "A probe skill added by the T5 multi-plugin validator test to prove the "
    "validators iterate plugins/*/skills across every marketplace plugin."
)

VALID_SKILL = """---
name: {name}
description: {desc}
---

## Runtime Inputs
Probe input.

## Execution Contract
Probe contract.

## Escalation
Probe escalation.

## Honest Limitations
Probe limitations.
"""


def valid_skill(name: str) -> str:
    return VALID_SKILL.format(name=name, desc=DESC)


def copy(dst_parent: Path, subs, files=()) -> Path:
    dst = dst_parent / "repo"
    for sub in subs:
        ignore = shutil.ignore_patterns("__pycache__", "runs")
        shutil.copytree(REPO / sub, dst / sub, ignore=ignore)
    for name in files:
        shutil.copy2(REPO / name, dst / name)
    return dst


def add_skill(repo: Path, plugin: str, skill: str, body: str) -> Path:
    d = repo / "plugins" / plugin / "skills" / skill
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text(body, encoding="utf-8")
    return d


def add_model_policy(repo: Path, plugin: str, skill: str) -> None:
    policy = {
        "schema_version": 1,
        "skills": {skill: {"tier": "strong", "down_routable": False}},
        "tier_patterns": {"strong": ["opus"]},
    }
    (repo / "plugins" / plugin / "model-policy.json").write_text(
        json.dumps(policy), encoding="utf-8"
    )


def run(script: str, repo: Path):
    return subprocess.run(
        [sys.executable, str(repo / "scripts" / script), "--root", str(repo)],
        capture_output=True,
        text=True,
        timeout=120,
    )


class AuthoringMultiPlugin(unittest.TestCase):
    SUBS = ("scripts", "plugins", "docs")

    def test_hitl_suffix_scanned_in_second_plugin(self):
        # skill_md_files / all_skill_docs now span plugins: a bad HITL suffix in
        # a second plugin's skill trips the A1 enum just like a core skill's.
        with tempfile.TemporaryDirectory() as tmp:
            repo = copy(Path(tmp), self.SUBS)
            body = valid_skill("x") + "\n## Human-in-the-Loop — bogus\nA gate.\n"
            add_skill(repo, "_probe", "x", body)
            res = run("authoring_check.py", repo)
            self.assertEqual(res.returncode, 1, res.stdout)
            self.assertIn("suffix must be one of", res.stderr)

    def test_material_gate_locator_scanned_in_second_plugin(self):
        # check_material_gate_locators iterates every plugin's skill dirs.
        with tempfile.TemporaryDirectory() as tmp:
            repo = copy(Path(tmp), self.SUBS)
            body = valid_skill("x") + "\nThe confirm step is a [material] gate.\n"
            add_skill(repo, "_probe", "x", body)
            res = run("authoring_check.py", repo)
            self.assertEqual(res.returncode, 1, res.stdout)
            self.assertIn("gate-locator", res.stderr)

    def test_router_cluster_resolves_across_plugins(self):
        # A cluster member living in a second plugin (the extracted idea trio)
        # still resolves: ce-market-scan already ships in the product-discovery
        # plugin, and relocating it again to a third plugin keeps authoring green
        # because check_router_clusters maps names across the plugin union.
        with tempfile.TemporaryDirectory() as tmp:
            repo = copy(Path(tmp), self.SUBS)
            src = repo / "plugins/product-discovery/skills/ce-market-scan"
            self.assertTrue(src.is_dir(), "fixture drift: ce-market-scan missing")
            dst = repo / "plugins/_probe/skills/ce-market-scan"
            dst.parent.mkdir(parents=True)
            shutil.move(str(src), str(dst))
            res = run("authoring_check.py", repo)
            self.assertEqual(res.returncode, 0, res.stderr)


class CorpusMultiPlugin(unittest.TestCase):
    SUBS = ("scripts", "plugins", "managed-agent-cookbooks", "docs")
    FILES = ("README.md", "CLAUDE.md")

    def test_required_headings_scanned_in_second_plugin(self):
        # skill_files() is the union, so a second plugin's SKILL.md is held to
        # the same skeleton headings.
        with tempfile.TemporaryDirectory() as tmp:
            repo = copy(Path(tmp), self.SUBS, self.FILES)
            body = valid_skill("x").replace("## Escalation\nProbe escalation.\n", "")
            add_skill(repo, "_probe", "x", body)
            res = run("corpus_lint.py", repo)
            self.assertEqual(res.returncode, 1, res.stdout)
            self.assertIn("missing required heading '## Escalation'", res.stderr)

    def test_companion_ref_scanned_in_second_plugin(self):
        # check_skill_dir_refs walks every plugin's skills dir.
        with tempfile.TemporaryDirectory() as tmp:
            repo = copy(Path(tmp), self.SUBS, self.FILES)
            body = valid_skill("x") + "\nLoad `${CLAUDE_SKILL_DIR}/not-real.md`.\n"
            add_skill(repo, "_probe", "x", body)
            res = run("corpus_lint.py", repo)
            self.assertEqual(res.returncode, 1, res.stdout)
            self.assertIn("not-real.md does not exist", res.stderr)

    def test_known_name_universe_is_the_plugin_union(self):
        # A core doc referencing a second-plugin skill (the T6 case: core skills
        # route to /ce-market-scan) stays valid because the known-name universe
        # is the union across plugins.
        with tempfile.TemporaryDirectory() as tmp:
            repo = copy(Path(tmp), self.SUBS, self.FILES)
            add_skill(repo, "_probe", "ce-widget", valid_skill("ce-widget"))
            readme = repo / "README.md"
            readme.write_text(
                readme.read_text(encoding="utf-8") + "\nRoute to /ce-widget for widgets.\n",
                encoding="utf-8",
            )
            res = run("corpus_lint.py", repo)
            self.assertEqual(res.returncode, 0, res.stderr)


class ProductLayerMultiPlugin(unittest.TestCase):
    SUBS = (
        ".github", "action", "docs", "plugins", "scripts", "templates", "tests",
        "managed-agent-cookbooks", "evals",
    )
    FILES = ("README.md", "CLAUDE.md", "CONTRIBUTING.md", "COMMERCIAL.md",
             "SECURITY.md", "THIRD_PARTY_NOTICES.md", "LICENSE")

    def test_skill_names_union_covers_second_plugin(self):
        # skill_names() spans plugins, so a second plugin's skill absent from
        # USAGE-MATRIX trips the same coverage lint core skills do.
        with tempfile.TemporaryDirectory() as tmp:
            repo = copy(Path(tmp), self.SUBS, self.FILES)
            add_skill(repo, "_probe", "ce-widget", valid_skill("ce-widget"))
            res = run("product_layer_check.py", repo)
            self.assertEqual(res.returncode, 1, res.stdout)
            self.assertIn("missing shipped skill", res.stderr)
            self.assertIn("/ce-widget", res.stderr)


class EvalCoverageMultiPlugin(unittest.TestCase):
    SUBS = ("scripts", "plugins", "evals")

    def test_coverage_ratchet_spans_plugins(self):
        # The coverage ratchet's skill universe is the plugin union: a second
        # plugin's skill with neither scenario nor waiver fails loudly.
        with tempfile.TemporaryDirectory() as tmp:
            repo = copy(Path(tmp), self.SUBS)
            add_skill(repo, "_probe", "ce-widget", valid_skill("ce-widget"))
            res = run("eval_check.py", repo)
            self.assertEqual(res.returncode, 1, res.stdout)
            self.assertIn("ce-widget has no eval scenario and no waiver", res.stderr)


@unittest.skipUnless(HAVE_YAML, "check.py integration needs pyyaml")
class CheckPyMultiPlugin(unittest.TestCase):
    SUBS = (
        ".github", "action", "scripts", "plugins", "managed-agent-cookbooks",
        ".claude-plugin", "docs", "evals", "templates", "tests",
    )
    FILES = ("README.md", "CLAUDE.md", "CONTRIBUTING.md", "COMMERCIAL.md",
             "SECURITY.md", "THIRD_PARTY_NOTICES.md", "LICENSE")

    def _check(self, repo: Path):
        return subprocess.run(
            [sys.executable, str(repo / "scripts" / "check.py"), "--no-install-hooks"],
            capture_output=True, text=True, timeout=120,
        )

    def test_frontmatter_scanned_in_second_plugin(self):
        # §3 already globs plugins/*/skills/*/SKILL.md — confirm a second
        # plugin's name/dir mismatch is caught (frontmatter, per Done-when).
        with tempfile.TemporaryDirectory() as tmp:
            repo = copy(Path(tmp), self.SUBS, self.FILES)
            body = valid_skill("x").replace("name: x", "name: wrong", 1)
            add_skill(repo, "_probe", "x", body)
            res = self._check(repo)
            self.assertEqual(res.returncode, 1, res.stdout)
            self.assertIn("name 'wrong' must match skill directory 'x'", res.stderr)

    def test_model_policy_required_for_second_plugin(self):
        # §7 derives its plugin set from skills/ dirs, so a second plugin that
        # ships skills without a model-policy.json is caught (model-policy).
        with tempfile.TemporaryDirectory() as tmp:
            repo = copy(Path(tmp), self.SUBS, self.FILES)
            add_skill(repo, "_probe", "x", valid_skill("x"))
            res = self._check(repo)
            self.assertEqual(res.returncode, 1, res.stdout)
            self.assertIn("ships skills/ but has no", res.stderr)
            self.assertIn("_probe", res.stderr)

    def test_readme_catalog_expected_skills_is_the_plugin_union(self):
        # §8 derives expected_skills from the union of plugins: a second
        # plugin's /ce-* skill absent from the bounded README catalog block is
        # reported missing. (The core "{N} skills" count needle stays scoped to
        # core-engineering and is unaffected — asserted by the sibling suite.)
        with tempfile.TemporaryDirectory() as tmp:
            repo = copy(Path(tmp), self.SUBS, self.FILES)
            add_skill(repo, "_probe", "ce-widget", valid_skill("ce-widget"))
            add_model_policy(repo, "_probe", "ce-widget")
            res = self._check(repo)
            self.assertEqual(res.returncode, 1, res.stdout)
            self.assertIn("skill catalog missing skill(s)", res.stderr)
            self.assertIn("/ce-widget", res.stderr)


if __name__ == "__main__":
    unittest.main()
