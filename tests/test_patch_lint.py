"""Focused tests for the express-only `/core-engineering:ce-patch` admission and diff gate."""

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "plugins/core-engineering/skills/ce-patch/scripts/patch-lint.py"
SKILL = REPO / "plugins/core-engineering/skills/ce-patch/SKILL.md"
STAGES = REPO / "plugins/core-engineering/skills/ce-patch/stages.md"

_spec = importlib.util.spec_from_file_location("patch_lint_mod", SCRIPT)
pl = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pl)


def run_lint(*argv: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *argv],
        capture_output=True,
        text=True,
        timeout=30,
        cwd=str(cwd) if cwd else None,
    )


def run_json(*argv: str, cwd: Path | None = None) -> tuple[dict, int]:
    result = run_lint(*argv, "--json", cwd=cwd)
    return json.loads(result.stdout), result.returncode


def write_stub(root: Path, files: list[str], desc: str = "fix widget") -> Path:
    path = root / "express.json"
    path.write_text(json.dumps({"files": files, "desc": desc}), encoding="utf-8")
    return path


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, timeout=30
    )
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr}")
    return result.stdout


def init_repo(root: Path) -> str:
    git(root, "init", "-q")
    git(root, "config", "user.email", "patch@example.test")
    git(root, "config", "user.name", "Patch Test")
    (root / "src").mkdir()
    (root / "src/widget.py").write_text("x = 1\n", encoding="utf-8")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "initial")
    return git(root, "rev-parse", "HEAD").strip()


class ExpressContractText(unittest.TestCase):
    def test_first_nonzero_admission_result_is_terminal(self):
        stages = STAGES.read_text(encoding="utf-8")
        self.assertIn("first non-zero admission result is terminal", stages)
        self.assertIn("Do not try alternate candidate", stages)

    def test_failed_green_or_regression_check_routes_without_repair_loop(self):
        skill = SKILL.read_text(encoding="utf-8")
        stages = STAGES.read_text(encoding="utf-8")
        self.assertNotIn("until the intended check is green", stages)
        self.assertIn("this lane has no automated repair loop", skill)
        self.assertIn("still-red intended check", skill)
        self.assertIn("regression/lint/build failure", skill)
        self.assertIn("Any\n   failure or could-not-run result routes directly to `/core-engineering:ce-plan`", stages)


class AdmissionFileBoundary(unittest.TestCase):
    def test_default_mode_accepts_two_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_repo(root)
            stub = write_stub(root, ["src/widget.py", "tests/test_widget.py"])
            payload, rc = run_json(str(stub), cwd=root)
        self.assertEqual(rc, 0, payload)
        self.assertEqual(payload["mode"], "admission")

    def test_express_flag_is_a_no_op_alias(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_repo(root)
            stub = write_stub(root, ["src/widget.py"])
            default, default_rc = run_json(str(stub), cwd=root)
            alias, alias_rc = run_json(str(stub), "--express", cwd=root)
        self.assertEqual(default_rc, alias_rc)
        self.assertEqual(default["hard_failures"], alias["hard_failures"])

    def test_more_than_two_files_fails_e1_and_routes_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_repo(root)
            stub = write_stub(root, ["src/a.py", "src/b.py", "src/c.py"])
            payload, rc = run_json(str(stub), cwd=root)
        self.assertEqual(rc, 1)
        self.assertEqual(payload["route"], "/core-engineering:ce-plan")
        self.assertTrue(any(item.startswith("E1:") for item in payload["hard_failures"]))

    def test_over_cap_schema_request_reports_both_reasons(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_repo(root)
            stub = write_stub(
                root,
                ["schema.sql", "accounts.py", "checks/accounts_check.py"],
                "add a stored preference field to the database schema",
            )
            payload, rc = run_json(str(stub), cwd=root)
        self.assertEqual(rc, 1)
        self.assertTrue(any(item.startswith("E1:") for item in payload["hard_failures"]))
        self.assertTrue(any(item.startswith("E5:") for item in payload["hard_failures"]))

    def test_duplicate_and_parent_paths_fail_e1(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_repo(root)
            stub = write_stub(root, ["src/widget.py", "../outside.py"])
            payload, rc = run_json(str(stub), cwd=root)
        self.assertEqual(rc, 1)
        self.assertTrue(any("safe repository-relative" in item for item in payload["hard_failures"]))


class AdmissionOwnership(unittest.TestCase):
    @staticmethod
    def write_owner(root: Path, data: object) -> None:
        owner = root / "docs/plans/other/specs/01-widget"
        owner.mkdir(parents=True)
        (owner / "tasks.json").write_text(json.dumps(data), encoding="utf-8")

    def test_cross_plan_collision_fails_e2(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_repo(root)
            self.write_owner(root, {"tasks": [{"id": "T1", "files": ["src/widget.py"]}]})
            stub = write_stub(root, ["src/widget.py"])
            payload, rc = run_json(str(stub), cwd=root)
        self.assertEqual(rc, 1)
        self.assertTrue(any(item.startswith("E2:") for item in payload["hard_failures"]))

    def test_malformed_ownership_is_inconclusive_and_routes_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_repo(root)
            self.write_owner(root, {"not_tasks": []})
            stub = write_stub(root, ["src/widget.py"])
            payload, rc = run_json(str(stub), cwd=root)
        self.assertEqual(rc, 2)
        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["route"], "/core-engineering:ce-plan")
        self.assertIn("ownership data", payload["message"])


class AdmissionSafetySurfaces(unittest.TestCase):
    def check_refused(self, path: str, desc: str, code: str) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_repo(root)
            stub = write_stub(root, [path], desc)
            payload, rc = run_json(str(stub), cwd=root)
        self.assertEqual(rc, 1, (path, desc, payload))
        self.assertTrue(any(item.startswith(code + ":") for item in payload["hard_failures"]))

    def test_reviewer_trigger_paths_fail_e3(self):
        for path in (
            "src/auth/login.py",
            "templates/invoice.py",
            "web/i18n/en.json",
            "ui/a11y/button.tsx",
            "privacy/retention.py",
        ):
            with self.subTest(path=path):
                self.check_refused(path, "small wording fix", "E3")

    def test_reviewer_trigger_request_fails_e3(self):
        self.check_refused("src/widget.py", "fix authentication token handling", "E3")

    def test_dependency_manifests_fail_e4(self):
        for path in ("package.json", "requirements-dev.txt", "go.mod", "src/App.csproj"):
            with self.subTest(path=path):
                self.check_refused(path, "small version bump", "E4")

    def test_durable_and_schema_signals_fail_e5(self):
        for path, desc in (
            ("db/migrations/001.sql", "small cleanup"),
            ("src/widget.py", "add a stored preference field to the database schema"),
            ("src/widget.py", "run DROP TABLE old_widgets"),
        ):
            with self.subTest(path=path, desc=desc):
                self.check_refused(path, desc, "E5")

    def test_public_contract_signals_fail_e5(self):
        for path, desc in (
            ("src/api/widget.py", "fix widget"),
            ("src/widget.py", "add a CLI flag for quiet output"),
            ("openapi.yaml", "correct a field"),
        ):
            with self.subTest(path=path, desc=desc):
                self.check_refused(path, desc, "E5")

    def test_ignored_candidate_fails_instead_of_escaping_diff_check(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_repo(root)
            (root / ".gitignore").write_text("generated/\n", encoding="utf-8")
            stub = write_stub(root, ["generated/output.py"])
            payload, rc = run_json(str(stub), cwd=root)
        self.assertEqual(rc, 1)
        self.assertTrue(any("ignored by git" in item for item in payload["hard_failures"]))


class DiffRegexCorpus(unittest.TestCase):
    def test_durable_patterns(self):
        for line in (
            "await repo.save(entity)",
            "db.session.add(user)",
            "CREATE TABLE users (id int)",
            "fs.writeFileSync(path, data)",
        ):
            self.assertTrue(pl.DURABLE_LINE.search(line), line)
        for line in ("return render_view(props)", "logger.info('created widget')"):
            self.assertFalse(pl.DURABLE_LINE.search(line), line)

    def test_destructive_patterns(self):
        for line in (
            "DROP TABLE users",
            "DELETE FROM orders WHERE id = 1",
            "os.remove(path)",
            "rm -rf build",
        ):
            self.assertTrue(pl.DESTRUCTIVE_LINE.search(line), line)
        self.assertFalse(pl.DESTRUCTIVE_LINE.search("return remove_from_list(value)"))


class PostDiffGate(unittest.TestCase):
    def test_clean_in_scope_edit_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = init_repo(root)
            (root / "src/widget.py").write_text("x = 2\n", encoding="utf-8")
            stub = write_stub(root, ["src/widget.py"])
            payload, rc = run_json(str(stub), "--post", "--base", base, cwd=root)
        self.assertEqual(rc, 0, payload)
        self.assertEqual(payload["mode"], "post")

    def test_out_of_set_edit_fails_h9(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = init_repo(root)
            (root / "src/widget.py").write_text("x = 2\n", encoding="utf-8")
            (root / "src/sneaky.py").write_text("y = 1\n", encoding="utf-8")
            stub = write_stub(root, ["src/widget.py"])
            payload, rc = run_json(str(stub), "--post", "--base", base, cwd=root)
        self.assertEqual(rc, 1)
        self.assertTrue(any(item.startswith("H9:") for item in payload["hard_failures"]))

    def test_durable_write_fails_h8(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = init_repo(root)
            (root / "src/widget.py").write_text("def f(repo, e):\n    repo.save(e)\n", encoding="utf-8")
            stub = write_stub(root, ["src/widget.py"])
            payload, rc = run_json(str(stub), "--post", "--base", base, cwd=root)
        self.assertEqual(rc, 1)
        self.assertTrue(any(item.startswith("H8:") for item in payload["hard_failures"]))

    def test_destructive_write_and_file_delete_fail_h10(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = init_repo(root)
            (root / "src/widget.py").write_text("import os\nos.remove('x')\n", encoding="utf-8")
            stub = write_stub(root, ["src/widget.py"])
            payload, rc = run_json(str(stub), "--post", "--base", base, cwd=root)
        self.assertEqual(rc, 1)
        self.assertTrue(any(item.startswith("H10:") for item in payload["hard_failures"]))

    def test_new_public_surface_fails_h11(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = init_repo(root)
            (root / "src/widget.py").write_text("export function widget() { return 1 }\n", encoding="utf-8")
            stub = write_stub(root, ["src/widget.py"])
            payload, rc = run_json(str(stub), "--post", "--base", base, cwd=root)
        self.assertEqual(rc, 1)
        self.assertTrue(any(item.startswith("H11:") for item in payload["hard_failures"]))

    def test_no_diff_fails_h9(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = init_repo(root)
            stub = write_stub(root, ["src/widget.py"])
            payload, rc = run_json(str(stub), "--post", "--base", base, cwd=root)
        self.assertEqual(rc, 1)
        self.assertTrue(any("no working-tree diff" in item for item in payload["hard_failures"]))


class ErrorContract(unittest.TestCase):
    def test_missing_and_invalid_stubs_are_exit_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            payload, rc = run_json(str(root / "missing.json"), cwd=REPO)
            self.assertEqual(rc, 2)
            self.assertEqual(payload["route"], "/core-engineering:ce-plan")
            bad = root / "express.json"
            bad.write_text("not json", encoding="utf-8")
            payload, rc = run_json(str(bad), cwd=REPO)
            self.assertEqual(rc, 2)

    def test_non_git_directory_is_inconclusive(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            stub = write_stub(root, ["src/widget.py"])
            payload, rc = run_json(str(stub), cwd=root)
        self.assertEqual(rc, 2)
        self.assertIn("no git worktree", payload["message"])

    def test_post_without_base_is_exit_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_repo(root)
            stub = write_stub(root, ["src/widget.py"])
            payload, rc = run_json(str(stub), "--post", cwd=root)
        self.assertEqual(rc, 2)
        self.assertEqual(payload["route"], "/core-engineering:ce-plan")

    def test_retired_full_lane_flags_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_repo(root)
            stub = write_stub(root, ["src/widget.py"])
            result = run_lint(str(stub), "--eligibility", cwd=root)
        self.assertEqual(result.returncode, 2)
        self.assertIn("unrecognized arguments", result.stderr)


if __name__ == "__main__":
    unittest.main()
