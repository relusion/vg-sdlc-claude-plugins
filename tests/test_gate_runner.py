"""Behavioral tests for scripts/gate_runner.py — the agent-agnostic merge bar.

Subprocess-only (the runner is exercised exactly as CI runs it, never
imported), fully offline: each test git-inits a tempdir copy of the
implementation-ready-feature eval fixture as a stand-in adopter repo, injects
a violation, and asserts the verdict goes red — or stays green — with the
documented exit codes (0 pass / 1 required-gate failure, fail-closed /
2 runner-level could-not-run).
"""

import ast
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
RUNNER = REPO / "scripts" / "gate_runner.py"
PLUGIN = REPO / "plugins" / "core-engineering"
POLICY = PLUGIN / "merge-policy.json"
FIXTURE = REPO / "evals" / "fixtures" / "implementation-ready-feature"
CONTEXT_HELPER = (
    REPO
    / "plugins/core-engineering/skills/ce-spec/scripts/architecture_context.py"
)

_context_spec = importlib.util.spec_from_file_location(
    "gate_runner_review_context", CONTEXT_HELPER
)
ac = importlib.util.module_from_spec(_context_spec)
assert _context_spec.loader is not None
_context_spec.loader.exec_module(ac)

GIT_ENV = dict(
    os.environ,
    GIT_CONFIG_GLOBAL="/dev/null",
    GIT_CONFIG_SYSTEM="/dev/null",
)

# test-guard's default test-file heuristic does not match the fixture's
# checks/*_check.py layout, so the adopter copy gets a conventionally-named
# test file to weaken (the heuristic is test-guard's contract, not ours).
TEST_FILE_REL = "tests/test_invitations.py"
TEST_FILE_BODY = (
    "from src.invitations import create_invitation\n\n\n"
    "def test_create_invitation_returns_token():\n"
    "    inv = create_invitation('a@example.com', 'admin')\n"
    "    assert inv['token']\n"
    "    assert inv['email'] == 'a@example.com'\n"
)


def _git(repo, *args):
    subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t",
         "-c", "commit.gpgsign=false", *args],
        check=True, capture_output=True, text=True, env=GIT_ENV, timeout=60,
    )


def _commit_all(repo, msg):
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", msg)


def _run(*args):
    return subprocess.run(
        [sys.executable, str(RUNNER), *args],
        capture_output=True, text=True, timeout=120,
    )


def _verdict(res):
    return json.loads(res.stdout)


def _make_adopter_repo(tmpdir):
    """Fixture copy + conventional test file + git init/commit -> (repo, base)."""
    repo = Path(tmpdir) / "repo"
    shutil.copytree(FIXTURE, repo,
                    ignore=shutil.ignore_patterns("__pycache__"))
    plan_dir = repo / "docs/plans/team-invitations"
    spec_dir = plan_dir / "specs/01-invite-user"
    context = ac.derive_context(
        plan_dir, "01-invite-user", repo_root=repo
    )
    tasks_path = spec_dir / "tasks.json"
    tasks = json.loads(tasks_path.read_text(encoding="utf-8"))
    tasks["architecture_context"] = context
    tasks_path.write_text(json.dumps(tasks, indent=2) + "\n", encoding="utf-8")
    spec_path = spec_dir / "ce-spec.md"
    spec_path.write_text(
        spec_path.read_text(encoding="utf-8")
        + "\n## Architecture Context\n\n"
        + "```json architecture-context\n"
        + json.dumps(context, indent=2, sort_keys=True)
        + "\n```\n",
        encoding="utf-8",
    )
    test_file = repo / TEST_FILE_REL
    test_file.parent.mkdir(parents=True, exist_ok=True)
    test_file.write_text(TEST_FILE_BODY, encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "init", "-q", "-b", "main"],
                   check=True, capture_output=True, env=GIT_ENV, timeout=60)
    _commit_all(repo, "base")
    base = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True, env=GIT_ENV, timeout=60,
    ).stdout.strip()
    return repo, base


@unittest.skipUnless(shutil.which("git"), "gate_runner git-mode tests need git")
class GateRunner(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)

    def _make_adopter(self):
        return _make_adopter_repo(self._tmp.name)

    # --- green path ------------------------------------------------------------

    def test_fixture_adopter_passes(self):
        repo, base = self._make_adopter()
        res = _run("--repo", str(repo), "--base", base,
                   "--change-class", "standard", "--declared", "", "--json")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        verdict = _verdict(res)
        self.assertEqual(verdict["status"], "pass")
        self.assertEqual(verdict["change_class"], "standard")
        self.assertEqual(verdict["validity_required"], "human")
        required = [g for g in verdict["gates"] if g["disposition"] == "required"]
        self.assertEqual(len(required), 3)
        self.assertTrue(all(g["status"] == "pass" for g in required))
        self.assertEqual(verdict["hard_failures"], [])

    # --- red paths (the roadmap done-when, offline) ------------------------------

    def test_spec_lint_violation_goes_red(self):
        repo, base = self._make_adopter()
        spec = repo / "docs/plans/team-invitations/specs/01-invite-user/ce-spec.md"
        text = spec.read_text(encoding="utf-8")
        # Delete a TC heading a task verifies -> H1 dangling `verifies` ref.
        lines = [ln for ln in text.splitlines() if not ln.startswith("### TC-1")]
        spec.write_text("\n".join(lines) + "\n", encoding="utf-8")
        _commit_all(repo, "break traceability")
        res = _run("--repo", str(repo), "--base", base,
                   "--change-class", "standard", "--declared", "", "--json")
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        verdict = _verdict(res)
        self.assertEqual(verdict["status"], "fail")
        self.assertTrue(any("spec-lint" in h for h in verdict["hard_failures"]),
                        verdict["hard_failures"])

    def test_architecture_context_removal_cannot_downgrade_merge_gate(self):
        repo, base = self._make_adopter()
        spec_dir = (
            repo
            / "docs/plans/team-invitations/specs/01-invite-user"
        )
        tasks_path = spec_dir / "tasks.json"
        tasks = json.loads(tasks_path.read_text(encoding="utf-8"))
        del tasks["architecture_context"]
        tasks_path.write_text(json.dumps(tasks, indent=2) + "\n", encoding="utf-8")
        spec_path = spec_dir / "ce-spec.md"
        text = spec_path.read_text(encoding="utf-8")
        spec_path.write_text(
            text.split("\n## Architecture Context\n", 1)[0] + "\n",
            encoding="utf-8",
        )
        _commit_all(repo, "strip architecture provenance")
        res = _run(
            "--repo",
            str(repo),
            "--base",
            base,
            "--change-class",
            "standard",
            "--declared",
            "",
            "--json",
        )
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        verdict = _verdict(res)
        self.assertTrue(
            any(
                "missing required architecture_context" in item
                for item in verdict["hard_failures"]
            ),
            verdict["hard_failures"],
        )

    def test_working_tree_cannot_launder_a_broken_committed_spec(self):
        # The bar judges COMMITTED state: restoring the spec on disk WITHOUT
        # committing must not flip a red verdict green — the recorded head SHA
        # fully determines the verdict (audit-evidence soundness).
        repo, base = self._make_adopter()
        spec = repo / "docs/plans/team-invitations/specs/01-invite-user/ce-spec.md"
        good = spec.read_text(encoding="utf-8")
        lines = [ln for ln in good.splitlines() if not ln.startswith("### TC-1")]
        spec.write_text("\n".join(lines) + "\n", encoding="utf-8")
        _commit_all(repo, "break traceability")
        spec.write_text(good, encoding="utf-8")  # restored on disk, uncommitted
        res = _run("--repo", str(repo), "--base", base,
                   "--change-class", "standard", "--declared", "", "--json")
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        verdict = _verdict(res)
        self.assertEqual(verdict["status"], "fail")
        self.assertTrue(any("spec-lint" in h for h in verdict["hard_failures"]),
                        verdict["hard_failures"])

    def test_weakened_test_goes_red(self):
        repo, base = self._make_adopter()
        (repo / TEST_FILE_REL).write_text("", encoding="utf-8")
        _commit_all(repo, "genie empties the test")
        res = _run("--repo", str(repo), "--base", base,
                   "--change-class", "standard", "--declared", "", "--json")
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        verdict = _verdict(res)
        self.assertTrue(any("test-guard" in h for h in verdict["hard_failures"]),
                        verdict["hard_failures"])

    def test_undeclared_dep_red_then_declared_green(self):
        repo, base = self._make_adopter()
        (repo / "requirements.txt").write_text("leftpadx==1.0.0\n", encoding="utf-8")
        _commit_all(repo, "add a dependency")
        res = _run("--repo", str(repo), "--base", base,
                   "--change-class", "standard", "--declared", "", "--json")
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        self.assertTrue(any("dep-guard" in h
                            for h in _verdict(res)["hard_failures"]))
        res = _run("--repo", str(repo), "--base", base,
                   "--change-class", "standard", "--declared", "leftpadx", "--json")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertEqual(_verdict(res)["status"], "pass")

    # --- verdict logic ------------------------------------------------------------

    def _write_policy(self, data):
        path = Path(self._tmp.name) / "policy.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    def _advisory_policy(self):
        data = json.loads(POLICY.read_text(encoding="utf-8"))
        data.pop("$comment", None)
        for bar in [data["defaults"], *data["change_classes"].values()]:
            bar["required_integrity_gates"] = ["spec-lint", "dep-guard"]
            bar["advisory_gates"] = ["test-guard"]
        return self._write_policy(data)

    def test_advisory_gate_never_fails_the_verdict(self):
        repo, base = self._make_adopter()
        (repo / TEST_FILE_REL).write_text("", encoding="utf-8")
        _commit_all(repo, "genie empties the test")
        res = _run("--repo", str(repo), "--base", base,
                   "--change-class", "standard", "--declared", "",
                   "--policy", str(self._advisory_policy()), "--json")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        verdict = _verdict(res)
        self.assertEqual(verdict["status"], "pass")
        self.assertTrue(any("test-guard" in a for a in verdict["advisory"]),
                        verdict["advisory"])
        self.assertEqual(verdict["hard_failures"], [])

    def _no_class_rules_policy(self):
        """Shipped policy minus class_rules — the pre-T3 shape, where omitting
        --change-class falls through to the fail-safe defaults bar."""
        data = json.loads(POLICY.read_text(encoding="utf-8"))
        data.pop("$comment", None)
        data.pop("class_rules", None)
        return self._write_policy(data)

    def test_defaults_bar_when_no_class_rules_and_class_omitted(self):
        # A policy WITHOUT class_rules keeps the original semantics: omitting
        # --change-class selects the strict fail-safe defaults bar (two-human).
        repo, base = self._make_adopter()
        res = _run("--repo", str(repo), "--base", base, "--declared", "",
                   "--policy", str(self._no_class_rules_policy()), "--json")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        verdict = _verdict(res)
        self.assertEqual(verdict["change_class"], "defaults")
        self.assertEqual(verdict["change_class_source"], "defaults")
        self.assertEqual(verdict["validity_required"], "two-human")

    # --- WS2-T3: path-based change-class rules, from the committed diff ----------

    def test_class_rules_fallback_when_no_rule_matches(self):
        # Shipped policy carries class_rules; a fixture PR touches no sensitive
        # path, so classification lands on the mandatory fallback (standard),
        # recorded as such — NOT the strict defaults bar.
        repo, base = self._make_adopter()
        res = _run("--repo", str(repo), "--base", base, "--declared", "", "--json")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        verdict = _verdict(res)
        self.assertEqual(verdict["change_class"], "standard")
        self.assertEqual(verdict["change_class_source"], "fallback")
        self.assertEqual(verdict["validity_required"], "human")
        self.assertEqual(verdict["change_class_matched_paths"], [])

    def test_auth_path_auto_classified_sensitive_from_diff(self):
        # The T3 done-when: a PR touching **/auth/** is auto-classified sensitive
        # (two-human) with NO env var / --change-class set, and the verdict shows
        # rule:<n> plus the matched path so an auditor sees WHY it fired.
        repo, base = self._make_adopter()
        (repo / "src" / "auth").mkdir(parents=True, exist_ok=True)
        (repo / "src" / "auth" / "login.py").write_text("X = 1\n", encoding="utf-8")
        _commit_all(repo, "touch an auth path")
        res = _run("--repo", str(repo), "--base", base, "--declared", "", "--json")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        verdict = _verdict(res)
        self.assertEqual(verdict["change_class"], "sensitive")
        self.assertEqual(verdict["validity_required"], "two-human")
        self.assertTrue(verdict["change_class_source"].startswith("rule:"),
                        verdict["change_class_source"])
        self.assertIn("src/auth/login.py", verdict["change_class_matched_paths"])

    def test_explicit_change_class_always_wins_over_rules(self):
        # An explicit --change-class overrides the classifier even when the diff
        # would have matched a rule — source is 'explicit', no diff consulted.
        repo, base = self._make_adopter()
        (repo / "src" / "auth").mkdir(parents=True, exist_ok=True)
        (repo / "src" / "auth" / "login.py").write_text("X = 1\n", encoding="utf-8")
        _commit_all(repo, "touch an auth path")
        res = _run("--repo", str(repo), "--base", base,
                   "--change-class", "standard", "--declared", "", "--json")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        verdict = _verdict(res)
        self.assertEqual(verdict["change_class"], "standard")
        self.assertEqual(verdict["change_class_source"], "explicit")
        self.assertEqual(verdict["validity_required"], "human")

    def test_github_merge_bar_path_escalates_to_two_human(self):
        # WS2-T5 keystone: the same-PR declared-deps path lives under
        # .github/merge-bar/, which .github/** classifies sensitive — so a PR
        # declaring its own dep is allowed only under two-human validity.
        repo, base = self._make_adopter()
        (repo / ".github" / "merge-bar").mkdir(parents=True, exist_ok=True)
        (repo / ".github" / "merge-bar" / "declared-deps.txt").write_text(
            "leftpadx\n", encoding="utf-8")
        _commit_all(repo, "declare a dep in-PR")
        res = _run("--repo", str(repo), "--base", base, "--declared", "", "--json")
        verdict = _verdict(res)
        self.assertEqual(verdict["change_class"], "sensitive")
        self.assertEqual(verdict["validity_required"], "two-human")
        self.assertTrue(verdict["change_class_source"].startswith("rule:"))

    def test_class_rule_referencing_unknown_class_exits_2(self):
        # load_policy must refuse a rule that names a class no bar defines (the
        # same rule check.py §14 enforces, re-applied for adopter overrides).
        repo, base = self._make_adopter()
        data = json.loads(POLICY.read_text(encoding="utf-8"))
        data.pop("$comment", None)
        data["class_rules"]["rules"][0]["class"] = "ghost-class"
        res = _run("--repo", str(repo), "--base", base,
                   "--policy", str(self._write_policy(data)), "--json")
        self.assertEqual(res.returncode, 2, res.stdout + res.stderr)
        self.assertIn("class must name a change class", _verdict(res)["message"])

    def test_class_rules_without_fallback_exits_2(self):
        repo, base = self._make_adopter()
        data = json.loads(POLICY.read_text(encoding="utf-8"))
        data.pop("$comment", None)
        del data["class_rules"]["fallback"]
        res = _run("--repo", str(repo), "--base", base,
                   "--policy", str(self._write_policy(data)), "--json")
        self.assertEqual(res.returncode, 2, res.stdout + res.stderr)
        self.assertIn("fallback", _verdict(res)["message"])

    # --- WS2-T4: spec_lint_scope (cold-start) -----------------------------------

    def _scoped_policy(self, scope):
        """Minimal single-gate (spec-lint required) policy at the given scope —
        isolates the scope behavior from the shipped advisory gates."""
        return self._write_policy({
            "schema_version": 1,
            "spec_lint_scope": scope,
            "gates": {"spec-lint": {
                "script": "skills/ce-spec/scripts/spec-lint.py",
                "args": ["{spec_dir}", "--json"], "proves": "traceability"}},
            "change_classes": {"standard": {
                "required_integrity_gates": ["spec-lint"], "validity": "human"}},
            "defaults": {"required_integrity_gates": ["spec-lint"],
                         "validity": "two-human"},
        })

    def test_changed_plans_scope_vacuously_holds_on_empty_repo(self):
        # A repo with ZERO spec dirs passes under changed-plans with the
        # vacuous-holds advisory, but still FAILS under all (fail-closed).
        repo, base = self._make_adopter()
        shutil.rmtree(repo / "docs" / "plans")
        (repo / "README.md").write_text("changed\n", encoding="utf-8")
        _commit_all(repo, "remove all plans")
        res = _run("--repo", str(repo), "--base", base, "--change-class",
                   "standard", "--policy", str(self._scoped_policy("changed-plans")),
                   "--json")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        verdict = _verdict(res)
        self.assertEqual(verdict["status"], "pass")
        self.assertTrue(any("vacuously holds" in a for a in verdict["advisory"]),
                        verdict["advisory"])
        res = _run("--repo", str(repo), "--base", base, "--change-class",
                   "standard", "--policy", str(self._scoped_policy("all")), "--json")
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        self.assertTrue(any("no spec dirs" in h
                            for h in _verdict(res)["hard_failures"]))

    def test_changed_plans_skips_untouched_broken_legacy_spec(self):
        # A repo with one BROKEN legacy spec passes a PR that does not touch it
        # under changed-plans (the spec is out of scope), by choice.
        repo, base = self._make_adopter()
        spec = repo / "docs/plans/team-invitations/specs/01-invite-user/ce-spec.md"
        text = spec.read_text(encoding="utf-8")
        lines = [ln for ln in text.splitlines() if not ln.startswith("### TC-1")]
        spec.write_text("\n".join(lines) + "\n", encoding="utf-8")  # break H1
        _commit_all(repo, "break the legacy spec")
        # A later PR that touches only an unrelated file, not the broken spec.
        (repo / "src" / "invitations.py").write_text(
            (repo / "src" / "invitations.py").read_text(encoding="utf-8") + "\n# x\n",
            encoding="utf-8")
        mid = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                             check=True, capture_output=True, text=True,
                             env=GIT_ENV, timeout=60).stdout.strip()
        _commit_all(repo, "unrelated change")
        res = _run("--repo", str(repo), "--base", mid, "--change-class",
                   "standard", "--policy", str(self._scoped_policy("changed-plans")),
                   "--json")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertEqual(_verdict(res)["status"], "pass")

    def test_changed_plans_still_gates_a_touched_broken_spec(self):
        # changed-plans is not a loophole: a PR that DOES touch the broken spec
        # is in scope and still goes red.
        repo, base = self._make_adopter()
        spec = repo / "docs/plans/team-invitations/specs/01-invite-user/ce-spec.md"
        text = spec.read_text(encoding="utf-8")
        lines = [ln for ln in text.splitlines() if not ln.startswith("### TC-1")]
        spec.write_text("\n".join(lines) + "\n", encoding="utf-8")
        _commit_all(repo, "break the touched spec")
        res = _run("--repo", str(repo), "--base", base, "--change-class",
                   "standard", "--policy", str(self._scoped_policy("changed-plans")),
                   "--json")
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        self.assertTrue(any("spec-lint" in h
                            for h in _verdict(res)["hard_failures"]))

    def test_unknown_spec_lint_scope_exits_2(self):
        repo, base = self._make_adopter()
        data = json.loads(POLICY.read_text(encoding="utf-8"))
        data.pop("$comment", None)
        data["spec_lint_scope"] = "only-mine"
        res = _run("--repo", str(repo), "--base", base,
                   "--policy", str(self._write_policy(data)), "--json")
        self.assertEqual(res.returncode, 2, res.stdout + res.stderr)
        self.assertIn("spec_lint_scope", _verdict(res)["message"])

    # --- WS2-T8: review-gate + plan-lint as advisory gates ----------------------

    SPEC_REL = "docs/plans/team-invitations/specs/01-invite-user"

    def _write_review_summary(self, repo, blocking_high):
        plan_dir = repo / "docs/plans/team-invitations"
        spec_dir = repo / self.SPEC_REL
        tasks_path = spec_dir / "tasks.json"
        tasks = json.loads(tasks_path.read_text(encoding="utf-8"))
        findings = [
            {
                "id": f"CR-{index}",
                "lens": "correctness",
                "severity": "high",
                "confidence": "confirmed",
            }
            for index in range(1, blocking_high + 1)
        ]
        summary = spec_dir / "review-summary.json"
        summary.write_text(
            json.dumps(
                {
                    "schema_version": 2,
                    "status": "blocked" if blocking_high else "pass",
                    "feature_id": "01-invite-user",
                    "plan_slug": "team-invitations",
                    "spec_revision": tasks["spec_revision"],
                    "binding": ac.review_binding(
                        spec_dir,
                        repo_root=repo,
                        plan_dir=plan_dir,
                        feature_id="01-invite-user",
                    ),
                    "blocking_high": blocking_high,
                    "blocking_route": "implement" if blocking_high else None,
                    "findings_total": len(findings),
                    "findings": findings,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    def test_review_gate_advisory_never_blocks_but_surfaces(self):
        # A spec whose review-summary.json has blocking_high: 1 gets a yellow
        # advisory line but a GREEN verdict (review-gate ships advisory).
        repo, base = self._make_adopter()
        self._write_review_summary(repo, 1)
        _commit_all(repo, "review found a blocking high")
        res = _run("--repo", str(repo), "--base", base,
                   "--change-class", "standard", "--declared", "", "--json")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        verdict = _verdict(res)
        self.assertEqual(verdict["status"], "pass")
        rg = next(g for g in verdict["gates"] if g["id"] == "review-gate")
        self.assertEqual(rg["disposition"], "advisory")
        self.assertEqual(rg["status"], "fail")
        self.assertTrue(any("review-gate" in a for a in verdict["advisory"]),
                        verdict["advisory"])
        self.assertEqual(verdict["hard_failures"], [])

    def test_promoting_review_gate_to_required_turns_it_red(self):
        # The same blocking_high: 1, but review-gate promoted to required in an
        # override policy, now FAILS the bar — the adopter's opt-in to hard-gate.
        repo, base = self._make_adopter()
        self._write_review_summary(repo, 1)
        _commit_all(repo, "review found a blocking high")
        data = json.loads(POLICY.read_text(encoding="utf-8"))
        data.pop("$comment", None)
        for bar in [data["defaults"], *data["change_classes"].values()]:
            bar["advisory_gates"] = [g for g in bar["advisory_gates"]
                                     if g != "review-gate"]
            bar["required_integrity_gates"].append("review-gate")
        res = _run("--repo", str(repo), "--base", base,
                   "--change-class", "standard", "--declared", "",
                   "--policy", str(self._write_policy(data)), "--json")
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        verdict = _verdict(res)
        self.assertEqual(verdict["status"], "fail")
        self.assertTrue(any("review-gate" in h for h in verdict["hard_failures"]),
                        verdict["hard_failures"])

    def test_review_gate_clean_summary_is_a_pass(self):
        repo, base = self._make_adopter()
        self._write_review_summary(repo, 0)
        _commit_all(repo, "clean review")
        res = _run("--repo", str(repo), "--base", base,
                   "--change-class", "standard", "--declared", "", "--json")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        rg = next(g for g in _verdict(res)["gates"] if g["id"] == "review-gate")
        self.assertEqual(rg["status"], "pass")

    def test_review_gate_uses_materialized_head_not_checked_out_head(self):
        repo, base = self._make_adopter()
        (repo / "reviewed-marker.txt").write_text(
            "state reviewed at target head\n", encoding="utf-8"
        )
        _commit_all(repo, "implementation state to review")
        self._write_review_summary(repo, 0)
        _commit_all(repo, "clean review evidence")
        reviewed_head = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            env=GIT_ENV,
            timeout=60,
        ).stdout.strip()

        # The runner evaluates reviewed_head from a materialized tree while the
        # adopter worktree is deliberately checked out at an older commit.
        _git(repo, "checkout", "--detach", base)
        data = json.loads(POLICY.read_text(encoding="utf-8"))
        data.pop("$comment", None)
        review_bar = {
            "required_integrity_gates": ["review-gate"],
            "validity": "human",
            "advisory_gates": [],
        }
        data["defaults"] = dict(review_bar)
        data["change_classes"] = {"standard": dict(review_bar)}
        data.pop("class_rules", None)
        res = _run(
            "--repo",
            str(repo),
            "--base",
            base,
            "--head",
            reviewed_head,
            "--change-class",
            "standard",
            "--policy",
            str(self._write_policy(data)),
            "--json",
        )
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        gate = _verdict(res)["gates"][0]
        self.assertEqual(gate["status"], "pass")
        self.assertEqual(
            gate["runs"][0]["detail"]["evaluated_commit"], reviewed_head
        )

    def test_plan_lint_advisory_fans_out_per_plan_dir(self):
        # plan-lint runs once per committed plan dir ({plan_dir} fan-out) as an
        # advisory gate — present in the verdict, never in hard_failures.
        repo, base = self._make_adopter()
        res = _run("--repo", str(repo), "--base", base,
                   "--change-class", "standard", "--declared", "", "--json")
        verdict = _verdict(res)
        pl = next(g for g in verdict["gates"] if g["id"] == "plan-lint")
        self.assertEqual(pl["disposition"], "advisory")
        self.assertEqual(len(pl["runs"]), 1)  # one plan dir in the fixture
        self.assertNotIn("plan-lint", "".join(verdict["hard_failures"]))

    # --- fail-closed paths ----------------------------------------------------------

    def test_malformed_policy_exits_2(self):
        repo, base = self._make_adopter()
        bad = Path(self._tmp.name) / "bad.json"
        bad.write_text("{not json", encoding="utf-8")
        res = _run("--repo", str(repo), "--base", base,
                   "--policy", str(bad), "--json")
        self.assertEqual(res.returncode, 2, res.stdout + res.stderr)
        self.assertNotIn("Traceback", res.stderr)
        self.assertEqual(_verdict(res)["status"], "error")

    def test_missing_gate_script_exits_2(self):
        repo, base = self._make_adopter()
        data = json.loads(POLICY.read_text(encoding="utf-8"))
        data["gates"]["spec-lint"]["script"] = "skills/ce-spec/scripts/gone.py"
        res = _run("--repo", str(repo), "--base", base,
                   "--policy", str(self._write_policy(data)), "--json")
        self.assertEqual(res.returncode, 2, res.stdout + res.stderr)
        self.assertIn("not found", _verdict(res)["message"])

    def test_path_traversal_rejected(self):
        repo, base = self._make_adopter()
        for evil in ("../../x.py", "/bin/echo"):
            data = json.loads(POLICY.read_text(encoding="utf-8"))
            data["gates"]["spec-lint"]["script"] = evil
            res = _run("--repo", str(repo), "--base", base,
                       "--policy", str(self._write_policy(data)), "--json")
            self.assertEqual(res.returncode, 2, f"{evil}: {res.stdout}{res.stderr}")
            self.assertEqual(_verdict(res)["status"], "error")

    def test_unknown_change_class_exits_2(self):
        repo, base = self._make_adopter()
        res = _run("--repo", str(repo), "--base", base,
                   "--change-class", "nonexistent", "--json")
        self.assertEqual(res.returncode, 2, res.stdout + res.stderr)
        self.assertIn("unknown --change-class", _verdict(res)["message"])

    def test_gate_exit_2_fails_closed(self):
        repo, base = self._make_adopter()
        plugin_root = Path(self._tmp.name) / "plugin"
        (plugin_root / "gates").mkdir(parents=True)
        stub = plugin_root / "gates" / "stub.py"
        stub.write_text("import sys\nprint('cannot run')\nsys.exit(2)\n",
                        encoding="utf-8")
        policy = self._write_policy({
            "schema_version": 1,
            "gates": {"stub": {"script": "gates/stub.py", "args": ["--json"],
                               "proves": "nothing"}},
            "change_classes": {"standard": {
                "required_integrity_gates": ["stub"], "validity": "human"}},
            "defaults": {"required_integrity_gates": ["stub"],
                         "validity": "two-human"},
        })
        res = _run("--repo", str(repo), "--base", base,
                   "--change-class", "standard",
                   "--policy", str(policy), "--plugin-root", str(plugin_root),
                   "--json")
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        verdict = _verdict(res)
        self.assertEqual(verdict["status"], "fail")
        self.assertTrue(any("could not run" in h for h in verdict["hard_failures"]),
                        verdict["hard_failures"])

    def _stub_gate_policy(self, body: str):
        """A plugin-root + policy whose only required gate is a stub script."""
        plugin_root = Path(self._tmp.name) / "plugin"
        (plugin_root / "gates").mkdir(parents=True, exist_ok=True)
        (plugin_root / "gates" / "stub.py").write_text(body, encoding="utf-8")
        policy = self._write_policy({
            "schema_version": 1,
            "gates": {"stub": {"script": "gates/stub.py", "args": [],
                               "proves": "nothing"}},
            "change_classes": {"standard": {
                "required_integrity_gates": ["stub"], "validity": "human"}},
            "defaults": {"required_integrity_gates": ["stub"],
                         "validity": "two-human"},
        })
        return policy, plugin_root

    def test_gate_json_fail_with_exit_0_fails_closed(self):
        # A wrapper gate that prints {"status": "fail"} but forgets
        # sys.exit(1) must never be scored pass on its exit code alone.
        repo, base = self._make_adopter()
        policy, plugin_root = self._stub_gate_policy(
            "import json\n"
            "print(json.dumps({'status': 'fail',"
            " 'hard_failures': ['gate JSON says FAIL']}))\n")
        res = _run("--repo", str(repo), "--base", base,
                   "--change-class", "standard",
                   "--policy", str(policy), "--plugin-root", str(plugin_root),
                   "--json")
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        verdict = _verdict(res)
        self.assertEqual(verdict["status"], "fail")
        self.assertTrue(any("contradicts" in h or "failing closed" in h
                            for h in verdict["hard_failures"]),
                        verdict["hard_failures"])

    def test_gate_hard_failures_without_status_and_exit_0_fails_closed(self):
        # A gate that reports hard_failures but exits 0 and omits a `status`
        # field would slip past the status-mismatch check — non-empty
        # hard_failures still contradicts a pass and must fail CLOSED.
        repo, base = self._make_adopter()
        policy, plugin_root = self._stub_gate_policy(
            "import json\n"
            "print(json.dumps({'hard_failures': ['silent hard failure']}))\n")
        res = _run("--repo", str(repo), "--base", base,
                   "--change-class", "standard",
                   "--policy", str(policy), "--plugin-root", str(plugin_root),
                   "--json")
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        verdict = _verdict(res)
        self.assertEqual(verdict["status"], "fail")
        self.assertTrue(any("failing closed" in h for h in verdict["hard_failures"]),
                        verdict["hard_failures"])

    def test_sca_guard_scans_committed_head_not_working_tree(self):
        # sca-guard runs against {head_tree} (materialized from the head COMMIT),
        # so an uncommitted dependency manifest in the working tree is invisible
        # to it — the verdict is a pure function of the recorded SHAs. Offline &
        # deterministic: a dep-free committed head means packages_scanned == 0
        # with no network touched; had it scanned the working tree it would have
        # found the planted pin (packages_scanned >= 1).
        repo, base = self._make_adopter()
        (repo / "requirements.txt").write_text("leftpadx==1.0.0\n", encoding="utf-8")
        # left UNCOMMITTED on purpose
        res = _run("--repo", str(repo), "--base", base,
                   "--change-class", "standard", "--declared", "", "--json")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        verdict = _verdict(res)
        sca = next(g for g in verdict["gates"] if g["id"] == "sca-guard")
        self.assertEqual(sca["status"], "pass", sca)
        self.assertEqual(sca["runs"][0]["detail"]["packages_scanned"], 0, sca)

    def test_non_object_gate_json_is_not_a_crash(self):
        # A gate printing a bare JSON scalar must yield a gate record, never
        # an AttributeError reported as a runner error (exit 2).
        repo, base = self._make_adopter()
        policy, plugin_root = self._stub_gate_policy("print('true')\n")
        res = _run("--repo", str(repo), "--base", base,
                   "--change-class", "standard",
                   "--policy", str(policy), "--plugin-root", str(plugin_root),
                   "--json")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        verdict = _verdict(res)
        self.assertEqual(verdict["status"], "pass")
        self.assertIsNone(verdict["gates"][0]["runs"][0]["detail"])

    def test_duplicate_policy_key_exits_2(self):
        # JSON last-one-wins would let a lax duplicate silently replace a
        # strict gate definition — the runner must refuse the policy outright.
        repo, base = self._make_adopter()
        dup = Path(self._tmp.name) / "dup.json"
        strict = json.dumps({"script": "skills/ce-spec/scripts/spec-lint.py",
                             "args": ["{spec_dir}", "--json"], "proves": "strict"})
        lax = json.dumps({"script": "skills/ce-spec/scripts/spec-lint.py",
                          "args": ["{spec_dir}"], "proves": "lax"})
        dup.write_text(
            '{"schema_version": 1,'
            f'"gates": {{"g": {strict}, "g": {lax}}},'
            '"change_classes": {"standard": {"required_integrity_gates": ["g"],'
            '"validity": "human"}},'
            '"defaults": {"required_integrity_gates": ["g"],'
            '"validity": "two-human"}}', encoding="utf-8")
        res = _run("--repo", str(repo), "--base", base,
                   "--change-class", "standard", "--policy", str(dup), "--json")
        self.assertEqual(res.returncode, 2, res.stdout + res.stderr)
        verdict = _verdict(res)
        self.assertEqual(verdict["status"], "error")
        self.assertIn("duplicate key", verdict["message"])

    def test_verdict_records_policy_provenance_and_pinned_shas(self):
        # An auditor must be able to see from the verdict alone WHICH policy
        # produced it (path + sha256, shipped vs override) and exactly which
        # commits were judged.
        import hashlib
        repo, base = self._make_adopter()
        res = _run("--repo", str(repo), "--base", base,
                   "--change-class", "standard", "--declared", "", "--json")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        verdict = _verdict(res)
        self.assertEqual(verdict["policy"]["sha256"],
                         hashlib.sha256(POLICY.read_bytes()).hexdigest())
        self.assertTrue(verdict["policy"]["shipped_default"])
        self.assertEqual(verdict["base_sha"], base)
        self.assertRegex(verdict["head_sha"], r"^[0-9a-f]{40}$")

        override = self._advisory_policy()
        res = _run("--repo", str(repo), "--base", base,
                   "--change-class", "standard", "--declared", "",
                   "--policy", str(override), "--json")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        verdict = _verdict(res)
        self.assertFalse(verdict["policy"]["shipped_default"])
        self.assertEqual(verdict["policy"]["sha256"],
                         hashlib.sha256(override.read_bytes()).hexdigest())

    def test_no_spec_dirs_fails_closed(self):
        repo, base = self._make_adopter()
        shutil.rmtree(repo / "docs" / "plans")
        _commit_all(repo, "remove plans")
        res = _run("--repo", str(repo), "--base", base,
                   "--change-class", "standard", "--declared", "", "--json")
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        verdict = _verdict(res)
        self.assertTrue(any("no spec dirs" in h for h in verdict["hard_failures"]),
                        verdict["hard_failures"])

    def test_bare_run_is_a_usage_error(self):
        res = _run()
        self.assertEqual(res.returncode, 2)
        self.assertIn("usage", res.stderr.lower())

    # --- portability self-test --------------------------------------------------------

    def test_runner_is_stdlib_only(self):
        # gate_runner.py lives at scripts/ (outside portability_check.py's
        # shipped-plugin glob), so its stdlib-only guarantee is asserted here.
        tree = ast.parse(RUNNER.read_text(encoding="utf-8"))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                imported.add((node.module or "").split(".")[0])
        allowed = {"__future__", "argparse", "hashlib", "json", "os", "re",
                   "subprocess", "sys", "tempfile", "pathlib"}
        self.assertLessEqual(imported, allowed, imported - allowed)


@unittest.skipUnless(shutil.which("git"), "committed-state tests need git")
class HeadTreeMaterialization(unittest.TestCase):
    """Unit-level proof that {head_tree} materialization ignores the working
    tree — the deterministic, offline core of the sca-guard committed-state fix."""

    def setUp(self):
        sys.path.insert(0, str(REPO / "scripts"))
        self.addCleanup(lambda: sys.path.remove(str(REPO / "scripts")))
        import gate_runner
        self.gr = gate_runner
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)

    def test_export_ignore_cannot_hide_a_committed_file(self):
        # `git archive` honors .gitattributes export-ignore and would silently
        # drop a committed manifest from the materialized tree; checkout-index
        # does not. A committed requirements.txt marked export-ignore must still
        # appear in the materialized tree so sca-guard/spec-lint see the truth.
        repo = Path(self._tmp.name) / "repo"
        repo.mkdir()
        subprocess.run(["git", "-C", str(repo), "init", "-q"],
                       check=True, capture_output=True, env=GIT_ENV, timeout=60)
        (repo / "requirements.txt").write_text("urllib3==1.24.1\n", encoding="utf-8")
        (repo / ".gitattributes").write_text("requirements.txt export-ignore\n",
                                              encoding="utf-8")
        _commit_all(repo, "committed but export-ignored manifest")
        head = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"],
            check=True, capture_output=True, text=True, env=GIT_ENV, timeout=60,
        ).stdout.strip()
        workdir = Path(self._tmp.name) / "work"
        workdir.mkdir()
        tree = self.gr.materialize_head_tree(repo, head, workdir)
        self.assertTrue((tree / "requirements.txt").is_file(),
                        "export-ignore hid a committed file from the merge bar")
        self.assertEqual((tree / "requirements.txt").read_text(encoding="utf-8"),
                         "urllib3==1.24.1\n")

    def test_materialize_head_tree_ignores_working_tree_edits(self):
        repo = Path(self._tmp.name) / "repo"
        repo.mkdir()
        subprocess.run(["git", "-C", str(repo), "init", "-q"],
                       check=True, capture_output=True, env=GIT_ENV, timeout=60)
        (repo / "requirements.txt").write_text("safe==1.0.0\n", encoding="utf-8")
        _commit_all(repo, "committed manifest")
        head = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"],
            check=True, capture_output=True, text=True, env=GIT_ENV, timeout=60,
        ).stdout.strip()
        # Corrupt the manifest on disk WITHOUT committing.
        (repo / "requirements.txt").write_text("evil==6.6.6\n", encoding="utf-8")
        workdir = Path(self._tmp.name) / "work"
        workdir.mkdir()
        tree = self.gr.materialize_head_tree(repo, head, workdir)
        self.assertEqual((tree / "requirements.txt").read_text(encoding="utf-8"),
                         "safe==1.0.0\n")

    def test_shipped_bars_reference_head_tree(self):
        policy = json.loads(POLICY.read_text(encoding="utf-8"))
        policy.pop("$comment", None)
        for name in ["defaults", *policy["change_classes"]]:
            bar = policy["defaults"] if name == "defaults" else policy["change_classes"][name]
            self.assertTrue(self.gr.bar_references(policy, bar, "head_tree"),
                            f"{name}: sca-guard should pull in the head tree")


# --- human-emit color (TTY-gated presentation, never content) -------------------------

try:
    import pty
except ImportError:  # pragma: no cover — non-POSIX platform
    pty = None

BOLD_GREEN = b"\x1b[1;32m"
BOLD_RED = b"\x1b[1;31m"
RED = b"\x1b[31m"
YELLOW = b"\x1b[33m"


def _run_on_pty(argv, env=None):
    """Run argv with stdout attached to a pseudo-TTY -> (stdout_bytes, exit)."""
    master, slave = pty.openpty()
    try:
        proc = subprocess.Popen(argv, stdout=slave,
                                stderr=subprocess.DEVNULL, env=env)
    finally:
        os.close(slave)
    chunks = []
    while True:
        try:
            chunk = os.read(master, 4096)
        except OSError:  # EIO when the slave end closes (Linux)
            break
        if not chunk:
            break
        chunks.append(chunk)
    rc = proc.wait(timeout=120)
    os.close(master)
    return b"".join(chunks), rc


@unittest.skipUnless(shutil.which("git"), "gate_runner color tests need git")
@unittest.skipUnless(pty is not None, "TTY color tests need the pty module (POSIX)")
class ColorEmission(unittest.TestCase):
    """Color on the human emit path is TTY-gated PRESENTATION only: bold
    green/red verdict headline, red hard-failure lines, yellow advisories —
    while piped / NO_COLOR / --no-color rendering stays byte-identical to the
    pre-color prose (committed run-records quote those lines verbatim), and
    --json output never carries ANSI, TTY or not."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.repo, self.base = _make_adopter_repo(self._tmp.name)

    def _argv(self, *extra):
        return [sys.executable, str(RUNNER), "--repo", str(self.repo),
                "--base", self.base, "--change-class", "standard",
                "--declared", "", *extra]

    def _env(self, **overrides):
        env = {k: v for k, v in os.environ.items() if k != "NO_COLOR"}
        env.update(overrides)
        return env

    def _commit_cheat(self):
        (self.repo / TEST_FILE_REL).write_text("", encoding="utf-8")
        _commit_all(self.repo, "genie empties the test")

    def test_tty_pass_headline_bold_green_advisory_yellow(self):
        out, rc = _run_on_pty(self._argv(), env=self._env())
        self.assertEqual(rc, 0, out)
        self.assertIn(
            BOLD_GREEN + b"merge bar [standard]: integrity conjunct PASS", out)
        self.assertIn(YELLOW, out)  # the test-guard A0 advisory line

    def test_tty_fail_headline_bold_red_failure_lines_red(self):
        self._commit_cheat()
        out, rc = _run_on_pty(self._argv(), env=self._env())
        self.assertEqual(rc, 1, out)
        self.assertIn(
            BOLD_RED + b"merge bar [standard]: integrity conjunct FAIL", out)
        self.assertIn(RED + b"    x test-guard:", out)

    def test_no_color_env_suppresses_ansi_even_on_tty(self):
        out, rc = _run_on_pty(self._argv(), env=self._env(NO_COLOR="1"))
        self.assertEqual(rc, 0, out)
        self.assertNotIn(b"\x1b", out)

    def test_no_color_flag_suppresses_ansi_even_on_tty(self):
        out, rc = _run_on_pty(self._argv("--no-color"), env=self._env())
        self.assertEqual(rc, 0, out)
        self.assertNotIn(b"\x1b", out)

    def test_piped_output_is_uncolored_verbatim_prose(self):
        res = subprocess.run(self._argv(), capture_output=True, text=True,
                             timeout=120)
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertNotIn("\x1b", res.stdout)
        self.assertIn("merge bar [standard]: integrity conjunct PASS\n",
                      res.stdout)
        self._commit_cheat()
        res = subprocess.run(self._argv(), capture_output=True, text=True,
                             timeout=120)
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        self.assertNotIn("\x1b", res.stdout)
        self.assertIn("\n  FAIL — 1 hard failure(s):\n    x test-guard:",
                      res.stdout)

    def test_json_never_colored_even_on_tty(self):
        out, rc = _run_on_pty(self._argv("--json"), env=self._env())
        self.assertEqual(rc, 0, out)
        self.assertNotIn(b"\x1b", out)
        verdict = json.loads(out.decode().replace("\r\n", "\n"))
        self.assertEqual(verdict["status"], "pass")


if __name__ == "__main__":
    unittest.main()
