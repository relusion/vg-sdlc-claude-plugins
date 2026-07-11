"""Data-level invariants for plugins/core-engineering/merge-policy.json.

These assert the shipped merge bar's own contract directly (gate scripts
resolve, bars are complete, the validity vocabulary has no 'none', the
placeholder set is closed). The same invariants are enforced by
scripts/check.py section 14 — but check.py needs pyyaml, and this suite must
stay runnable on a bare python3, so the JSON-side rules are asserted here
independently, with the check.py integration guarded by skipUnless.
"""

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PLUGIN = REPO / "plugins" / "core-engineering"
POLICY = PLUGIN / "merge-policy.json"

# Independently re-derived here (this suite must run on a bare python3 and asserts
# the JSON contract directly). test_vocab_matches_gate_runner below imports the
# runner's own constants and fails if these drift — independence AND drift-safety.
PLACEHOLDERS = {"repo", "base", "head", "spec_dir", "plan_dir", "declared",
                "head_tree"}
VALIDITY_VOCAB = {"human", "two-human"}
SPEC_LINT_SCOPE_VOCAB = {"all", "changed-plans"}

try:
    import yaml  # noqa: F401
    HAVE_YAML = True
except ImportError:
    HAVE_YAML = False


class MergePolicyData(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.policy = json.loads(POLICY.read_text(encoding="utf-8"))

    def _all_bars(self):
        yield "defaults", self.policy["defaults"]
        for name, bar in sorted(self.policy["change_classes"].items()):
            yield name, bar

    def test_schema_version(self):
        self.assertEqual(self.policy["schema_version"], 1)

    def test_gate_scripts_resolve_inside_the_plugin(self):
        for gate_id, gate in self.policy["gates"].items():
            script = gate["script"]
            self.assertTrue(script.startswith("skills/"),
                            f"{gate_id}: script must point at a skill script")
            self.assertNotIn("..", Path(script).parts, gate_id)
            resolved = (PLUGIN / script).resolve()
            self.assertTrue(resolved.is_relative_to(PLUGIN.resolve()), gate_id)
            self.assertTrue(resolved.is_file(), f"{gate_id}: {script} missing")

    def test_every_bar_requires_registered_gates(self):
        registered = set(self.policy["gates"])
        for name, bar in self._all_bars():
            required = bar["required_integrity_gates"]
            self.assertTrue(required, f"{name}: empty required gate list")
            self.assertLessEqual(set(required), registered, name)
            advisory = set(bar.get("advisory_gates", []))
            self.assertLessEqual(advisory, registered, name)
            self.assertFalse(advisory & set(required),
                             f"{name}: a gate is both required and advisory")

    def test_validity_vocab_has_no_none(self):
        for name, bar in self._all_bars():
            self.assertIn(bar["validity"], VALIDITY_VOCAB, name)
            self.assertNotEqual(bar["validity"], "none", name)

    def test_defaults_bar_is_strictest(self):
        # The fail-safe bar (used when no change class is named) demands the
        # strongest validity attestation. A data-level opinion test: weakening
        # the default is a policy decision — change it deliberately, with this.
        self.assertEqual(self.policy["defaults"]["validity"], "two-human")

    def test_two_way_completeness_no_dead_gates(self):
        referenced = set()
        for _, bar in self._all_bars():
            referenced.update(bar["required_integrity_gates"])
            referenced.update(bar.get("advisory_gates", []))
        self.assertEqual(set(self.policy["gates"]), referenced,
                         "a registered gate is referenced by no bar")

    def test_arg_placeholders_are_the_closed_set(self):
        import re
        for gate_id, gate in self.policy["gates"].items():
            for arg in gate["args"]:
                for token in re.findall(r"\{([^{}]*)\}", arg):
                    self.assertIn(token, PLACEHOLDERS, f"{gate_id}: {arg}")

    def test_vocab_matches_gate_runner(self):
        # gate_runner.py is the single source; this file re-derives the sets for
        # independence but must not silently drift from the runner that actually
        # consumes the policy. gate_runner is stdlib-only, so importing it here
        # keeps the suite runnable on a bare python3.
        sys.path.insert(0, str(REPO / "scripts"))
        try:
            import gate_runner
        finally:
            sys.path.pop(0)
        self.assertEqual(PLACEHOLDERS, gate_runner.PLACEHOLDERS)
        self.assertEqual(VALIDITY_VOCAB, gate_runner.VALIDITY_VOCAB)
        self.assertEqual(SPEC_LINT_SCOPE_VOCAB,
                         gate_runner.SPEC_LINT_SCOPE_VOCAB)

    # --- class_rules (WS2-T3) + spec_lint_scope (WS2-T4) shipped-policy shape ----

    def test_shipped_class_rules_are_well_formed(self):
        # The shipped classifier: a mandatory fallback + rules that only select
        # among defined change classes (so a rule can never invent a bar).
        rules = self.policy.get("class_rules")
        self.assertIsNotNone(rules, "shipped policy must ship class_rules")
        classes = set(self.policy["change_classes"])
        self.assertIn(rules["fallback"], classes,
                      "class_rules.fallback must name a defined change class")
        self.assertTrue(rules["rules"], "class_rules.rules must be non-empty")
        for i, rule in enumerate(rules["rules"]):
            self.assertIn(rule["class"], classes, f"rule[{i}].class undefined")
            self.assertTrue(rule["paths"] and all(rule["paths"]),
                            f"rule[{i}].paths must be non-empty strings")

    def test_shipped_policy_escalates_github_to_two_human(self):
        # The load-bearing WS2-T5 invariant: a change under .github/** (which
        # covers .github/merge-bar/**, the same-PR declared-deps path) selects a
        # two-human bar — same-PR self-declaration is allowed only under review.
        sys.path.insert(0, str(REPO / "scripts"))
        try:
            import gate_runner
        finally:
            sys.path.pop(0)
        cls, source, matched = gate_runner.classify_change(
            self.policy, None, [".github/merge-bar/declared-deps.txt"])
        self.assertEqual(self.policy["change_classes"][cls]["validity"],
                         "two-human", f"{cls} via {source} must be two-human")

    def test_shipped_spec_lint_scope_default_is_fail_closed(self):
        # The out-of-box posture stays 'all' (fail-closed): shipping
        # 'changed-plans' by default would silently stop gating legacy specs.
        self.assertEqual(self.policy.get("spec_lint_scope", "all"), "all")


@unittest.skipUnless(HAVE_YAML, "check.py §14 integration needs pyyaml")
class CheckPyMergePolicy(unittest.TestCase):
    """Prove §14 actually fires — mutate a repo copy, run check.py, expect FAIL.

    Same copy-repo shape as test_model_policy.CheckPySection7 (plus templates/,
    which supply_chain_check now scans). A clean copy must PASS first, so a
    red result on a mutation is a real catch, not a pre-existing failure.
    """

    def _copy_repo(self, tmp: Path) -> Path:
        dst = tmp / "repo"
        for sub in (
            ".github", "action", "scripts", "plugins", "managed-agent-cookbooks",
            ".claude-plugin", "docs", "evals", "templates", "tests"
        ):
            shutil.copytree(REPO / sub, dst / sub,
                            ignore=shutil.ignore_patterns("__pycache__"))
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

    def _expect_fail(self, mutate, *needles):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._copy_repo(Path(tmp))
            mutate(repo)
            res = self._check(repo)
            self.assertEqual(res.returncode, 1, res.stderr)
            self.assertNotIn("Traceback", res.stderr)
            merge_lines = "\n".join(
                line for line in res.stderr.splitlines() if "merge-policy:" in line)
            for needle in needles:
                self.assertIn(needle, merge_lines, res.stderr)

    def test_clean_copy_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._copy_repo(Path(tmp))
            res = self._check(repo)
            self.assertEqual(res.returncode, 0,
                             f"stdout={res.stdout}\nstderr={res.stderr}")

    def test_malformed_policy_fails_cleanly(self):
        def mutate(repo):
            (repo / "plugins/core-engineering/merge-policy.json").write_text("[]")
        self._expect_fail(mutate, "top level must be a JSON object")

    def test_dangling_gate_ref_fails(self):
        def mutate(repo):
            pf = repo / "plugins/core-engineering/merge-policy.json"
            data = json.loads(pf.read_text())
            data["change_classes"]["standard"]["required_integrity_gates"].append("ghost-gate")
            pf.write_text(json.dumps(data))
        self._expect_fail(mutate, "unregistered gate 'ghost-gate'")

    def test_dead_registry_gate_fails(self):
        def mutate(repo):
            pf = repo / "plugins/core-engineering/merge-policy.json"
            data = json.loads(pf.read_text())
            data["gates"]["unused-gate"] = {
                "script": "skills/ce-spec/scripts/spec-lint.py",
                "args": ["{spec_dir}", "--json"],
                "proves": "nothing — no bar references it",
            }
            pf.write_text(json.dumps(data))
        self._expect_fail(mutate, "'unused-gate' is referenced by no bar")

    def test_validity_none_fails(self):
        def mutate(repo):
            pf = repo / "plugins/core-engineering/merge-policy.json"
            data = json.loads(pf.read_text())
            data["change_classes"]["standard"]["validity"] = "none"
            pf.write_text(json.dumps(data))
        self._expect_fail(mutate, "validity", "'none' does not exist by design")

    def test_deleting_policy_while_auto_build_ships_fails(self):
        def mutate(repo):
            (repo / "plugins/core-engineering/merge-policy.json").unlink()
        self._expect_fail(mutate, "ships ce-auto-build but has no merge-policy.json")

    def test_duplicate_gate_key_fails(self):
        # JSON last-one-wins would let a lax duplicate silently replace a
        # strict gate definition with no lint error — §14 must refuse it.
        def mutate(repo):
            pf = repo / "plugins/core-engineering/merge-policy.json"
            data = json.loads(pf.read_text())
            gate = json.dumps(data["gates"]["spec-lint"])
            text = json.dumps(data)
            text = text.replace('"gates": {', f'"gates": {{"spec-lint": {gate}, ', 1)
            pf.write_text(text)
        self._expect_fail(mutate, "duplicate key 'spec-lint'")

    def test_class_rules_unknown_class_fails(self):
        # A rule may only SELECT AMONG defined change classes — a rule naming a
        # class no bar defines could silently pick a nonexistent bar (§14 + the
        # runner's load_policy must both refuse it).
        def mutate(repo):
            pf = repo / "plugins/core-engineering/merge-policy.json"
            data = json.loads(pf.read_text())
            data["class_rules"]["rules"][0]["class"] = "ultra-sensitive"
            pf.write_text(json.dumps(data))
        self._expect_fail(mutate, "class must name a change class")

    def test_class_rules_missing_fallback_fails(self):
        # fallback is MANDATORY whenever class_rules is present, so an unmatched
        # diff can never silently downgrade below an explicit choice.
        def mutate(repo):
            pf = repo / "plugins/core-engineering/merge-policy.json"
            data = json.loads(pf.read_text())
            del data["class_rules"]["fallback"]
            pf.write_text(json.dumps(data))
        self._expect_fail(mutate, "class_rules.fallback must name a change class")

    def test_class_rules_empty_paths_fails(self):
        def mutate(repo):
            pf = repo / "plugins/core-engineering/merge-policy.json"
            data = json.loads(pf.read_text())
            data["class_rules"]["rules"][0]["paths"] = []
            pf.write_text(json.dumps(data))
        self._expect_fail(mutate, "paths must be a non-empty list")

    def test_unknown_spec_lint_scope_fails(self):
        def mutate(repo):
            pf = repo / "plugins/core-engineering/merge-policy.json"
            data = json.loads(pf.read_text())
            data["spec_lint_scope"] = "only-mine"
            pf.write_text(json.dumps(data))
        self._expect_fail(mutate, "spec_lint_scope must be one of")


if __name__ == "__main__":
    unittest.main()
