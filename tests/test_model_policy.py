"""Data-level invariants for plugins/core-engineering/model-policy.json.

These assert the policy file's own contract directly (two-way completeness
against the skill corpus, tier vocabulary, the down_routable consistency
rule). The same invariants are enforced by scripts/check.py section 7 — which
additionally guards the frontmatter side — but check.py needs pyyaml, and this
suite must stay runnable on a bare python3 (local runs without pyyaml), so the
JSON-side rules are asserted here independently.
"""

import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PLUGIN = REPO / "plugins" / "core-engineering"
POLICY = PLUGIN / "model-policy.json"

try:
    import yaml  # noqa: F401
    HAVE_YAML = True
except ImportError:
    HAVE_YAML = False


class ModelPolicy(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.policy = json.loads(POLICY.read_text())
        cls.skill_dirs = {p.name for p in (PLUGIN / "skills").iterdir()
                          if p.is_dir()}

    def test_schema_version(self):
        self.assertEqual(self.policy["schema_version"], 1)

    def test_two_way_completeness(self):
        entries = set(self.policy["skills"])
        self.assertEqual(self.skill_dirs - entries, set(),
                         "skills with no policy entry")
        self.assertEqual(entries - self.skill_dirs, set(),
                         "policy entries naming no existing skill")

    def test_tier_vocabulary_and_consistency(self):
        for name, entry in self.policy["skills"].items():
            self.assertIn(entry["tier"], ("strong", "cheap-ok"), name)
            self.assertIsInstance(entry["down_routable"], bool, name)
            if entry["down_routable"]:
                self.assertEqual(entry["tier"], "cheap-ok",
                                 f"{name}: down_routable requires cheap-ok")

    def test_tier_patterns_cover_used_tiers_and_name_no_unknown_tier(self):
        # Runtime attestation buckets (WS3-T5): every tier a skill entry uses must
        # have a non-empty pattern list, and tier_patterns may not name a tier
        # outside the closed vocabulary. Underscore keys are inline comments.
        valid = ("strong", "cheap-ok")
        patterns = self.policy["tier_patterns"]
        self.assertIsInstance(patterns, dict)
        pattern_tiers = {k for k in patterns if not k.startswith("_")}
        self.assertEqual(pattern_tiers - set(valid), set(),
                         "tier_patterns names a tier outside the vocabulary")
        used = {e["tier"] for e in self.policy["skills"].values()}
        for tier in used:
            pats = patterns.get(tier)
            self.assertTrue(
                isinstance(pats, list) and pats
                and all(isinstance(p, str) and p for p in pats),
                f"tier '{tier}' is used by a skill but has no pattern list")

    def test_ship_backlog_is_the_only_down_routable_skill(self):
        # CLAUDE.md: "/ce-ship-backlog is the one safe cheap-tier candidate".
        # Widening this set is a policy decision — change CLAUDE.md and this
        # test together, deliberately.
        down = sorted(n for n, e in self.policy["skills"].items()
                      if e["down_routable"])
        self.assertEqual(down, ["ce-ship-backlog"])

    def test_no_skill_binds_model_without_policy_consent(self):
        # Frontmatter side of the dual-truth guard, YAML-free: a crude
        # key-scan of each SKILL.md frontmatter block is enough to catch a
        # binding `model:`/`effort:` line (check.py does the strict parse).
        for skill_md in sorted((PLUGIN / "skills").glob("*/SKILL.md")):
            text = skill_md.read_text(encoding="utf-8")
            m = re.match(r"^---\n(.*?)\n---", text, re.S)
            self.assertIsNotNone(m, f"{skill_md}: no frontmatter block")
            # Tolerate YAML's 'key : value' spacing so 'model : haiku' can't slip past.
            keys = re.findall(r"^\s*([A-Za-z_-]+)\s*:", m.group(1), re.M)
            binds = {k for k in keys if k in ("model", "effort")}
            if binds:
                entry = self.policy["skills"].get(skill_md.parent.name, {})
                self.assertTrue(
                    entry.get("down_routable") is True,
                    f"{skill_md.parent.name} sets {binds} frontmatter but the "
                    f"policy does not mark it down_routable")


@unittest.skipUnless(HAVE_YAML, "check.py §7 integration needs pyyaml")
class CheckPySection7(unittest.TestCase):
    """Prove §7 actually fires — mutate a repo copy, run check.py, expect FAIL.

    These guard the dual-truth + completeness rules end-to-end (the regex
    tests above only cover the data file). A clean copy must PASS first, so a
    green result on a mutation is a real catch, not a pre-existing failure.
    """

    def _copy_repo(self, tmp: Path) -> Path:
        dst = tmp / "repo"
        for sub in (
            ".github", "action", "scripts", "plugins", "managed-agent-cookbooks",
            ".claude-plugin", "docs", "evals", "templates", "tests"
        ):
            shutil.copytree(REPO / sub, dst / sub)
        shutil.copy2(REPO / "README.md", dst / "README.md")
        shutil.copy2(REPO / "CLAUDE.md", dst / "CLAUDE.md")
        shutil.copy2(REPO / "CONTRIBUTING.md", dst / "CONTRIBUTING.md")
        shutil.copy2(REPO / "COMMERCIAL.md", dst / "COMMERCIAL.md")
        shutil.copy2(REPO / "SECURITY.md", dst / "SECURITY.md")
        shutil.copy2(REPO / "THIRD_PARTY_NOTICES.md", dst / "THIRD_PARTY_NOTICES.md")
        shutil.copy2(REPO / "LICENSE", dst / "LICENSE")
        return dst

    def _check(self, repo: Path):
        return subprocess.run(
            [sys.executable, str(repo / "scripts" / "check.py"), "--no-install-hooks"],
            capture_output=True, text=True, timeout=60,
        )

    def test_clean_copy_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._copy_repo(Path(tmp))
            self.assertEqual(self._check(repo).returncode, 0)

    def test_missing_entry_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._copy_repo(Path(tmp))
            pf = repo / "plugins/core-engineering/model-policy.json"
            data = json.loads(pf.read_text())
            data["skills"].pop("ce-ask")
            pf.write_text(json.dumps(data))
            res = self._check(repo)
            self.assertEqual(res.returncode, 1)
            self.assertIn("ce-ask", res.stderr)

    def test_skill_binding_without_policy_consent_fails_strict_yaml(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._copy_repo(Path(tmp))
            sk = repo / "plugins/core-engineering/skills/ce-ask/SKILL.md"
            sk.write_text("---\nmodel: haiku\n" + sk.read_text()[4:])
            res = self._check(repo)
            self.assertEqual(res.returncode, 1)
            self.assertIn("down_routable", res.stderr)

    def test_skill_binding_without_consent_fails_spaced_colon(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._copy_repo(Path(tmp))
            sk = repo / "plugins/core-engineering/skills/ce-ask/SKILL.md"
            sk.write_text("---\nmodel : haiku\n" + sk.read_text()[4:])  # spaced colon
            res = self._check(repo)
            self.assertEqual(res.returncode, 1)
            self.assertIn("down_routable", res.stderr)

    def test_missing_tier_pattern_for_used_tier_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._copy_repo(Path(tmp))
            pf = repo / "plugins/core-engineering/model-policy.json"
            data = json.loads(pf.read_text())
            # cheap-ok is used by ce-ship-backlog; drop its pattern list.
            data["tier_patterns"].pop("cheap-ok")
            pf.write_text(json.dumps(data))
            res = self._check(repo)
            self.assertEqual(res.returncode, 1)
            self.assertIn("cheap-ok", res.stderr)

    def test_tier_patterns_naming_unknown_tier_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._copy_repo(Path(tmp))
            pf = repo / "plugins/core-engineering/model-policy.json"
            data = json.loads(pf.read_text())
            data["tier_patterns"]["mystery"] = ["nonesuch"]
            pf.write_text(json.dumps(data))
            res = self._check(repo)
            self.assertEqual(res.returncode, 1)
            self.assertIn("unknown", res.stderr)

    def test_underscore_comment_key_in_tier_patterns_is_tolerated(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._copy_repo(Path(tmp))
            pf = repo / "plugins/core-engineering/model-policy.json"
            data = json.loads(pf.read_text())
            data["tier_patterns"]["_note"] = "an inline comment, not a tier"
            pf.write_text(json.dumps(data))
            self.assertEqual(self._check(repo).returncode, 0)

    def test_malformed_policy_is_clean_error_not_traceback(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._copy_repo(Path(tmp))
            (repo / "plugins/core-engineering/model-policy.json").write_text("[]")
            res = self._check(repo)
            self.assertEqual(res.returncode, 1)
            self.assertNotIn("Traceback", res.stderr)
            self.assertIn("top level must be a JSON object", res.stderr)

    def test_plugin_with_skills_but_no_policy_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._copy_repo(Path(tmp))
            other = repo / "plugins/other-plugin"
            (other / "skills/sneaky").mkdir(parents=True)
            (other / ".claude-plugin").mkdir(parents=True)
            (other / ".claude-plugin/plugin.json").write_text(
                json.dumps({"name": "other-plugin", "version": "0.0.1"}))
            (other / "skills/sneaky/SKILL.md").write_text(
                "---\nname: sneaky\ndescription: x\nmodel: haiku\n---\n# s\n")
            res = self._check(repo)
            self.assertEqual(res.returncode, 1)
            self.assertIn("no model-policy.json", res.stderr)


if __name__ == "__main__":
    unittest.main()
