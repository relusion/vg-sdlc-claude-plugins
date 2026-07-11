"""Tests for scripts/eval_impact.py — diff → affected scenarios + freshness."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "eval_impact.py"
sys.path.insert(0, str(REPO / "scripts"))

import eval_impact  # noqa: E402


def run(*args, root=REPO):
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(root), *args],
        capture_output=True, text=True, timeout=120,
    )


def payload(res):
    return json.loads(res.stdout)


# ---------------------------------------------------------------------------
# Pure-function unit tests
# ---------------------------------------------------------------------------
class PureHelpers(unittest.TestCase):
    def test_skill_from_path(self):
        self.assertEqual(
            eval_impact.skill_from_path("plugins/core-engineering/skills/ce-review/SKILL.md"),
            "ce-review")
        self.assertEqual(
            eval_impact.skill_from_path("plugins/product-discovery/skills/ce-idea-score/SKILL.md"),
            "ce-idea-score")
        self.assertIsNone(eval_impact.skill_from_path("scripts/gate_runner.py"))
        self.assertIsNone(eval_impact.skill_from_path("plugins/core-engineering/hooks/git-guard.py"))

    def test_fixture_from_path(self):
        self.assertEqual(
            eval_impact.fixture_from_path("evals/fixtures/minimal-service/app.py"),
            "minimal-service")
        self.assertIsNone(eval_impact.fixture_from_path("evals/scenarios.json"))

    def test_parse_run_id(self):
        dt = eval_impact.parse_run_id("20260627-044925Z")
        self.assertIsNotNone(dt)
        self.assertEqual((dt.year, dt.month, dt.day, dt.hour), (2026, 6, 27, 4))
        self.assertIsNone(eval_impact.parse_run_id("2026-06-27"))
        self.assertIsNone(eval_impact.parse_run_id(None))

    def test_parse_iso_handles_offset_and_date_only(self):
        self.assertIsNotNone(eval_impact.parse_iso("2026-07-05T08:40:32+02:00"))
        self.assertIsNotNone(eval_impact.parse_iso("2026-07-03"))
        self.assertIsNotNone(eval_impact.parse_iso("2026-07-03T00:00:00Z"))
        self.assertIsNone(eval_impact.parse_iso("not-a-date"))
        self.assertIsNone(eval_impact.parse_iso(None))

    def test_fork_index_maps_canonical_and_copy_to_all_consumers(self):
        index = eval_impact.load_fork_index(REPO)
        canonical = "plugins/core-engineering/skills/ce-spec/scripts/spec-lint.py"
        copy = "plugins/core-engineering/skills/ce-auto-build/scripts/spec-lint.py"
        self.assertIn(canonical, index)
        self.assertEqual(index[canonical], {"ce-spec", "ce-auto-build"})
        self.assertEqual(index[copy], {"ce-spec", "ce-auto-build"})

    def test_fork_index_canonical_outside_skills_resolves_to_copy_skill(self):
        index = eval_impact.load_fork_index(REPO)
        self.assertEqual(index.get("scripts/gate_runner.py"), {"ce-auto-build"})

    def test_analyze_unions_direct_and_fork_skills(self):
        scenarios = [
            {"id": "S-spec", "skill": "ce-spec", "fixture": "f"},
            {"id": "S-auto", "skill": "ce-auto-build", "fixture": "f"},
        ]
        fork_index = {"plugins/core-engineering/skills/ce-spec/scripts/spec-lint.py":
                      {"ce-spec", "ce-auto-build"}}
        triggers, skills = eval_impact.analyze_changes(
            ["plugins/core-engineering/skills/ce-spec/scripts/spec-lint.py"],
            scenarios, fork_index)
        self.assertEqual(set(triggers), {"S-spec", "S-auto"})
        self.assertEqual(skills, {"ce-spec", "ce-auto-build"})


# ---------------------------------------------------------------------------
# Mapping tests against the real committed corpus (deterministic)
# ---------------------------------------------------------------------------
class MappingAgainstRealCorpus(unittest.TestCase):
    def test_prompt_only_ce_review_edit_maps_to_eval_007(self):
        res = run("--files", "plugins/core-engineering/skills/ce-review/SKILL.md")
        self.assertEqual(res.returncode, 0, res.stderr)
        data = payload(res)
        self.assertEqual(data["affected_scenarios"], ["EVAL-007"])
        self.assertEqual(data["touched_waived_skills"], [])

    def test_spec_lint_canonical_edit_maps_to_ce_spec_and_ce_auto_build(self):
        res = run("--files", "plugins/core-engineering/skills/ce-spec/scripts/spec-lint.py")
        self.assertEqual(res.returncode, 0, res.stderr)
        data = payload(res)
        # ce-spec owns EVAL-005; ce-auto-build now owns EVAL-017 (waiver retired by WS3-T12).
        self.assertIn("EVAL-005", data["affected_scenarios"])
        self.assertIn("EVAL-017", data["affected_scenarios"])
        self.assertEqual(data["touched_waived_skills"], [])

    def test_spec_lint_copy_edit_also_reaches_ce_spec(self):
        res = run("--files", "plugins/core-engineering/skills/ce-auto-build/scripts/spec-lint.py")
        self.assertEqual(res.returncode, 0, res.stderr)
        data = payload(res)
        self.assertIn("EVAL-005", data["affected_scenarios"])
        self.assertIn("EVAL-017", data["affected_scenarios"])
        self.assertEqual(data["touched_waived_skills"], [])

    def test_gate_runner_canonical_maps_to_ce_auto_build_scenario(self):
        res = run("--files", "scripts/gate_runner.py")
        self.assertEqual(res.returncode, 0, res.stderr)
        data = payload(res)
        # gate_runner is ce-auto-build's fork; ce-auto-build now owns EVAL-017.
        self.assertEqual(data["affected_scenarios"], ["EVAL-017"])
        self.assertEqual(data["touched_waived_skills"], [])

    def test_fixture_edit_maps_to_every_consumer_scenario(self):
        res = run("--files", "evals/fixtures/minimal-service/app.py")
        self.assertEqual(res.returncode, 0, res.stderr)
        data = payload(res)
        self.assertIn("EVAL-001", data["affected_scenarios"])
        self.assertIn("EVAL-004", data["affected_scenarios"])
        # A minimal-service scenario, but not a TypeScript one.
        self.assertNotIn("EVAL-013", data["affected_scenarios"])

    def test_catchall_grader_edit_maps_to_all_scenarios(self):
        catalog = json.loads((REPO / "evals" / "scenarios.json").read_text())
        total = len(catalog["scenarios"])
        for path in ("scripts/eval_check.py", "scripts/eval_run.py", "evals/scenarios.json"):
            res = run("--files", path)
            self.assertEqual(res.returncode, 0, res.stderr)
            self.assertEqual(len(payload(res)["affected_scenarios"]), total, path)

    def test_unrelated_file_maps_to_nothing(self):
        res = run("--files", "docs/HOW-IT-WORKS.md")
        self.assertEqual(res.returncode, 0, res.stderr)
        data = payload(res)
        self.assertEqual(data["affected_scenarios"], [])
        self.assertEqual(data["touched_waived_skills"], [])

    def test_requires_exactly_one_source(self):
        neither = subprocess.run(
            [sys.executable, str(SCRIPT), "--root", str(REPO)],
            capture_output=True, text=True, timeout=60)
        self.assertEqual(neither.returncode, 2)
        both = subprocess.run(
            [sys.executable, str(SCRIPT), "--root", str(REPO),
             "--base", "HEAD", "--files", "a.py"],
            capture_output=True, text=True, timeout=60)
        self.assertEqual(both.returncode, 2)


# ---------------------------------------------------------------------------
# Freshness against a synthetic git repo
# ---------------------------------------------------------------------------
SKILL_REL = "plugins/core-engineering/skills/ce-foo/SKILL.md"


def git(repo, *args, date=None):
    env = dict(os.environ)
    if date:
        env["GIT_AUTHOR_DATE"] = date
        env["GIT_COMMITTER_DATE"] = date
    proc = subprocess.run(["git", "-C", str(repo), *args],
                          capture_output=True, text=True, env=env)
    if proc.returncode != 0:
        raise AssertionError(f"git {args} failed: {proc.stderr}")
    return proc.stdout.strip()


def build_repo(tmp):
    repo = Path(tmp) / "repo"
    (repo / "evals" / "results").mkdir(parents=True)
    (repo / "plugins" / "core-engineering" / "skills" / "ce-foo").mkdir(parents=True)
    (repo / "evals" / "scenarios.json").write_text(json.dumps({
        "schema_version": 1,
        "scenarios": [{"id": "EVAL-T1", "skill": "ce-foo", "fixture": "fix1"}],
    }), encoding="utf-8")
    (repo / "plugins" / "core-engineering" / "fork-manifest.json").write_text(
        json.dumps({"schema_version": 1, "forks": []}), encoding="utf-8")
    (repo / "evals" / "coverage-allowlist.json").write_text(
        json.dumps({"waivers": []}), encoding="utf-8")
    (repo / SKILL_REL).write_text("v1\n", encoding="utf-8")
    git(repo, "init", "-q")
    git(repo, "config", "user.email", "t@example.com")
    git(repo, "config", "user.name", "T")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "seed", date="2026-06-01T00:00:00")
    return repo


def write_result(repo, name, *, run_id="20260627-000000Z", git_head=None,
                 status="pass", returncode=0, dry_run=False):
    scenario = {"id": "EVAL-T1", "skill": "ce-foo",
                "status": status, "returncode": returncode, "run_id": run_id}
    if git_head:
        scenario["git_head"] = git_head
    (repo / "evals" / "results" / name).write_text(json.dumps({
        "schema_version": 1, "dry_run": dry_run, "scenarios": [scenario],
    }), encoding="utf-8")


class FreshnessSynthetic(unittest.TestCase):
    def _touch_skill(self, repo, date):
        (repo / SKILL_REL).write_text("v2\n", encoding="utf-8")
        git(repo, "add", "-A")
        git(repo, "commit", "-qm", "edit skill", date=date)
        return git(repo, "rev-parse", "HEAD")

    def test_stale_when_live_pass_predates_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = build_repo(tmp)
            write_result(repo, "old.json", run_id="20260601-000000Z")
            self._touch_skill(repo, "2026-07-05T00:00:00")
            res = run("--files", SKILL_REL, "--check", root=repo)
            self.assertEqual(res.returncode, 1, res.stdout)
            data = payload(res)
            self.assertEqual(len(data["stale"]), 1)
            self.assertEqual(data["stale"][0]["id"], "EVAL-T1")
            self.assertEqual(data["stale"][0]["reason"], "live pass predates the change")
            self.assertIn("dispatch eval-live", res.stderr)

    def test_fresh_when_live_pass_dated_after_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = build_repo(tmp)
            self._touch_skill(repo, "2026-07-01T00:00:00")
            write_result(repo, "new.json", run_id="20260705-000000Z")
            res = run("--files", SKILL_REL, "--check", root=repo)
            self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
            self.assertEqual(payload(res)["stale"], [])

    def test_fresh_via_git_head_anchor_even_if_date_older(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = build_repo(tmp)
            head = self._touch_skill(repo, "2026-07-05T00:00:00")
            # An OLD-dated run, but anchored to the commit that made the change.
            write_result(repo, "anchored.json", run_id="20260101-000000Z", git_head=head)
            res = run("--files", SKILL_REL, "--check", root=repo)
            self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
            self.assertEqual(payload(res)["stale"], [])

    def test_stale_when_no_committed_live_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = build_repo(tmp)
            self._touch_skill(repo, "2026-07-05T00:00:00")
            res = run("--files", SKILL_REL, "--check", root=repo)
            self.assertEqual(res.returncode, 1, res.stdout)
            self.assertEqual(payload(res)["stale"][0]["reason"], "no committed live pass")

    def test_dry_run_result_is_not_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = build_repo(tmp)
            self._touch_skill(repo, "2026-07-05T00:00:00")
            write_result(repo, "dry.json", run_id="20260706-000000Z", dry_run=True)
            res = run("--files", SKILL_REL, "--check", root=repo)
            self.assertEqual(res.returncode, 1, res.stdout)
            self.assertEqual(payload(res)["stale"][0]["reason"], "no committed live pass")

    def test_failed_receipt_is_not_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = build_repo(tmp)
            self._touch_skill(repo, "2026-07-05T00:00:00")
            write_result(repo, "failed.json", run_id="20260706-000000Z",
                         status="failed", returncode=1)
            res = run("--files", SKILL_REL, "--check", root=repo)
            self.assertEqual(res.returncode, 1, res.stdout)
            self.assertEqual(payload(res)["stale"][0]["reason"], "no committed live pass")

    def test_base_ref_diff_drives_check(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = build_repo(tmp)
            base = git(repo, "rev-parse", "HEAD")
            write_result(repo, "old.json", run_id="20260601-000000Z")
            self._touch_skill(repo, "2026-07-05T00:00:00")
            res = run("--base", base, "--check", root=repo)
            self.assertEqual(res.returncode, 1, res.stdout)
            data = payload(res)
            self.assertIn(SKILL_REL, data["changed"])
            self.assertEqual(data["affected_scenarios"], ["EVAL-T1"])


if __name__ == "__main__":
    unittest.main()
