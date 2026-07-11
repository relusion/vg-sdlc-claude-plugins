"""Tests for skills/ce-patch/scripts/patch-lint.py — the `--express` mechanical screen.

patch-lint had zero dedicated tests before this suite (the build-spine finding). These
pin the featherweight express lane's admission contract (WS5-T1):

  E1  candidate file count <= 2 (stricter than C1's cap);
  E2  the C4 cross-feature collision scan, reused over a synthetic docs/plans anchor;
  E3  the C6 reviewer-trigger mechanical floor — auth/secret/payment/migration/i18n/a11y
      path segments + the H8 durable-file wall + the H8/H10 content walls over the desc;
  E4  no dependency-manifest file in the candidate set;
  --express --post  re-runs H8/H9/H10 over the ACTUAL diff against the candidate set.

The exit contract is patch-lint's shared 0/1/2: 0 PASS, 1 a hard clause FAIL (named),
2 could-not-run (garbled stub / bad invocation / no git) — so the express fold falls
back to the full lane loudly, never silently passes.
"""

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "plugins/core-engineering/skills/ce-patch/scripts/patch-lint.py"

_spec = importlib.util.spec_from_file_location("patch_lint_mod", SCRIPT)
pl = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pl)


# --- helpers -----------------------------------------------------------------

def run_lint(*argv: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *argv],
        capture_output=True, text=True, timeout=30,
        cwd=str(cwd) if cwd else None,
    )


def run_json(*argv: str, cwd: Path | None = None) -> tuple[dict, int]:
    proc = run_lint(*argv, "--json", cwd=cwd)
    return json.loads(proc.stdout), proc.returncode


def write_stub(root: Path, files: list, desc: str = "tweak", name: str = "express.json") -> Path:
    p = root / name
    p.write_text(json.dumps({"files": files, "desc": desc}), encoding="utf-8")
    return p


def git(repo: Path, *args: str) -> str:
    out = subprocess.run(["git", "-C", str(repo), *args],
                         capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {out.stderr}")
    return out.stdout


def init_repo(root: Path) -> str:
    """A minimal committed git repo; returns the base commit sha."""
    git(root, "init", "-q")
    git(root, "config", "user.email", "t@t")
    git(root, "config", "user.name", "t")
    (root / "src").mkdir()
    (root / "src" / "widget.py").write_text("x = 1\n", encoding="utf-8")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "init")
    return git(root, "rev-parse", "HEAD").strip()


# --- E1: file cap ------------------------------------------------------------

class E1FileCap(unittest.TestCase):
    def test_one_file_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            stub = write_stub(Path(tmp), ["src/widget.py"])
            payload, rc = run_json(str(stub), "--express")
        self.assertEqual(rc, 0)
        self.assertEqual(payload["status"], "pass")
        self.assertEqual(payload["hard_failures"], [])

    def test_two_files_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            stub = write_stub(Path(tmp), ["src/a.py", "src/b.py"])
            payload, rc = run_json(str(stub), "--express")
        self.assertEqual(rc, 0)
        self.assertEqual(payload["status"], "pass")

    def test_three_files_fail_e1(self):
        with tempfile.TemporaryDirectory() as tmp:
            stub = write_stub(Path(tmp), ["src/a.py", "src/b.py", "src/c.py"])
            payload, rc = run_json(str(stub), "--express")
        self.assertEqual(rc, 1)
        self.assertEqual(payload["status"], "fail")
        self.assertTrue(any(h.startswith("E1:") for h in payload["hard_failures"]))


# --- E2: cross-feature collision (reused recompute_c4) ----------------------

class E2Collision(unittest.TestCase):
    def _repo_with_other_plan(self, tmp: Path) -> None:
        init_repo(tmp)
        owner = tmp / "docs/plans/other/specs/feat-x"
        owner.mkdir(parents=True)
        (owner / "tasks.json").write_text(
            json.dumps({"tasks": [{"id": "T1", "files": ["src/widget.py"]}]}),
            encoding="utf-8")

    def test_collision_with_other_plan_fails_e2(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._repo_with_other_plan(root)
            stub = write_stub(root, ["src/widget.py"])
            payload, rc = run_json(str(stub), "--express", cwd=root)
        self.assertEqual(rc, 1)
        self.assertTrue(any(h.startswith("E2:") for h in payload["hard_failures"]),
                        payload["hard_failures"])
        # re-tag worked: no leaked H5 C4 vocabulary.
        self.assertFalse(any("H5 C4" in h for h in payload["hard_failures"]))

    def test_no_collision_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._repo_with_other_plan(root)
            stub = write_stub(root, ["src/untouched.py"])
            payload, rc = run_json(str(stub), "--express", cwd=root)
        self.assertEqual(rc, 0, payload["hard_failures"])
        self.assertEqual(payload["status"], "pass")

    def test_no_plans_dir_passes(self):
        # A repo with no docs/plans at all -> nothing to collide with.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_repo(root)
            stub = write_stub(root, ["src/widget.py"])
            payload, rc = run_json(str(stub), "--express", cwd=root)
        self.assertEqual(rc, 0, payload["hard_failures"])


# --- E3: reviewer-trigger heuristic (C6 floor) ------------------------------

class E3ReviewerTriggerPaths(unittest.TestCase):
    TRIGGER_PATHS = [
        "src/auth/login.py",
        "app/authorization/policy.py",   # prefix-match beyond exact 'auth'
        "lib/paymentService.ts",         # camelCase segment prefix
        "config/secrets.yaml",
        "api/billing/charge.py",
        "db/migrations/001_init.py",
        "web/i18n/en.json",
        "ui/a11y/aria.ts",
        "core/session_store.py",
    ]
    BENIGN_PATHS = [
        "src/widget.py",
        "lib/helpers/format.ts",
        "components/Button.tsx",
        "docs/readme.md",
        "src/plugin/registry.py",        # 'plugin' must NOT match 'login'
    ]

    def test_trigger_paths_fail_e3(self):
        for path in self.TRIGGER_PATHS:
            with self.subTest(path=path), tempfile.TemporaryDirectory() as tmp:
                stub = write_stub(Path(tmp), [path], desc="small tweak")
                payload, rc = run_json(str(stub), "--express")
            self.assertEqual(rc, 1, f"{path} should trip E3")
            self.assertTrue(any(h.startswith("E3:") for h in payload["hard_failures"]),
                            f"{path}: {payload['hard_failures']}")

    def test_benign_paths_pass(self):
        for path in self.BENIGN_PATHS:
            with self.subTest(path=path), tempfile.TemporaryDirectory() as tmp:
                stub = write_stub(Path(tmp), [path], desc="rename a helper")
                payload, rc = run_json(str(stub), "--express")
            self.assertEqual(rc, 0, f"{path} should pass: {payload['hard_failures']}")


class E3ReviewerTriggerDesc(unittest.TestCase):
    TRIGGER_DESCS = [
        "add authentication to the login flow",
        "encrypt the session token",
        "fix the payment charge webhook",
        "update the i18n locale bundle",
        "improve aria accessibility labels",
        "run DROP TABLE users in the fixup",   # destructive content wall over the desc
    ]
    BENIGN_DESCS = [
        "rename the widget helper function",
        "fix an off-by-one in the paginator",
        "improve the button label copy wording",
    ]

    def test_trigger_descs_fail_e3(self):
        for desc in self.TRIGGER_DESCS:
            with self.subTest(desc=desc), tempfile.TemporaryDirectory() as tmp:
                stub = write_stub(Path(tmp), ["src/widget.py"], desc=desc)
                payload, rc = run_json(str(stub), "--express")
            self.assertEqual(rc, 1, f"desc {desc!r} should trip E3")
            self.assertTrue(any(h.startswith("E3:") for h in payload["hard_failures"]))

    def test_benign_descs_pass(self):
        for desc in self.BENIGN_DESCS:
            with self.subTest(desc=desc), tempfile.TemporaryDirectory() as tmp:
                stub = write_stub(Path(tmp), ["src/widget.py"], desc=desc)
                payload, rc = run_json(str(stub), "--express")
            self.assertEqual(rc, 0, f"desc {desc!r} should pass: {payload['hard_failures']}")


class E3DurableFileWall(unittest.TestCase):
    # DURABLE_FILE (the H8 file wall) reused in the screen, isolated from the
    # reviewer-trigger path list.
    def test_sql_and_timestamp_migration_files_fail_e3(self):
        for path in ["db/seed.sql", "data/1700000000000-seed.ts", "app/schema.prisma"]:
            with self.subTest(path=path), tempfile.TemporaryDirectory() as tmp:
                stub = write_stub(Path(tmp), [path], desc="small tweak")
                payload, rc = run_json(str(stub), "--express")
            self.assertEqual(rc, 1, f"{path} should trip E3 (durable file)")
            self.assertTrue(any(h.startswith("E3:") for h in payload["hard_failures"]))


# --- E4: dependency manifests ------------------------------------------------

class E4DepManifest(unittest.TestCase):
    MANIFESTS = [
        "package.json", "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
        "requirements.txt", "requirements-dev.txt", "pyproject.toml",
        "Pipfile", "poetry.lock", "go.mod", "go.sum", "Cargo.toml",
        "pom.xml", "build.gradle", "build.gradle.kts", "composer.json",
        "src/App.csproj", "packages.config",
    ]
    NOT_MANIFESTS = [
        "src/package.py",           # not package.json
        "config/requirements.md",   # not a .txt
        "docs/go.md",               # not go.mod
        "src/widget.py",
    ]

    def test_manifests_fail_e4(self):
        for path in self.MANIFESTS:
            with self.subTest(path=path), tempfile.TemporaryDirectory() as tmp:
                stub = write_stub(Path(tmp), [path], desc="bump a version")
                payload, rc = run_json(str(stub), "--express")
            self.assertEqual(rc, 1, f"{path} should trip E4")
            self.assertTrue(any(h.startswith("E4:") for h in payload["hard_failures"]),
                            f"{path}: {payload['hard_failures']}")

    def test_non_manifests_pass_e4(self):
        for path in self.NOT_MANIFESTS:
            with self.subTest(path=path), tempfile.TemporaryDirectory() as tmp:
                stub = write_stub(Path(tmp), [path], desc="edit")
                payload, rc = run_json(str(stub), "--express")
            self.assertEqual(rc, 0, f"{path} should pass E4: {payload['hard_failures']}")


# --- H8/H9/H10 regex corpus (unit-level, over the shipped patterns) ---------

class DiffRegexCorpus(unittest.TestCase):
    def test_durable_line_true_positives(self):
        for line in [
            "await repo.save(entity)",
            "db.session.add(user)",
            "await ctx.SaveChangesAsync()",
            "CREATE TABLE users (id int)",
            "INSERT INTO orders VALUES (1)",
            "fs.writeFileSync(path, data)",
            "localStorage.setItem('k', v)",
            "await prisma.user.create({ data })",
        ]:
            self.assertTrue(pl.DURABLE_LINE.search(line), line)

    def test_durable_line_false_positives(self):
        for line in [
            "const total = calculate(a, b)",
            "return renderView(props)",
            "updateLabel = 'saved'",         # no .create(/SET; word 'update' alone is inert
            "logger.info('created widget')",
        ]:
            self.assertFalse(pl.DURABLE_LINE.search(line), line)

    def test_destructive_line_true_positives(self):
        for line in [
            "DROP TABLE users",
            "DELETE FROM orders WHERE id = 1",
            "await repo.delete(id)",
            "os.remove(path)",
            "shutil.rmtree(tmp)",
            "fs.unlinkSync(file)",
            "rm -rf build",
        ]:
            self.assertTrue(pl.DESTRUCTIVE_LINE.search(line), line)

    def test_destructive_line_false_positives(self):
        for line in [
            "const removed = removeFromList(x)",   # no leading dot, not .remove(
            "return dropdownItems",
            "deleteme = false",
        ]:
            self.assertFalse(pl.DESTRUCTIVE_LINE.search(line), line)

    def test_durable_file_wall(self):
        for path in ["db/migrations/001.py", "schema.sql", "app/schema.prisma"]:
            self.assertTrue(pl.DURABLE_FILE.search(path), path)
        for path in ["src/widget.py", "test_migrate_helper.py"]:
            self.assertFalse(pl.DURABLE_FILE.search(path), path)


# --- --express --post: H8/H9/H10 over the real diff -------------------------

class ExpressPostDiffGate(unittest.TestCase):
    def test_clean_in_scope_edit_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = init_repo(root)
            (root / "src" / "widget.py").write_text("x = 2\n", encoding="utf-8")
            stub = write_stub(root, ["src/widget.py"])
            payload, rc = run_json(str(stub), "--express", "--post", "--base", base, cwd=root)
        self.assertEqual(rc, 0, payload["hard_failures"])
        self.assertEqual(payload["status"], "pass")

    def test_out_of_set_edit_fails_h9(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = init_repo(root)
            (root / "src" / "widget.py").write_text("x = 2\n", encoding="utf-8")
            (root / "src" / "sneaky.py").write_text("y = 1\n", encoding="utf-8")
            stub = write_stub(root, ["src/widget.py"])
            payload, rc = run_json(str(stub), "--express", "--post", "--base", base, cwd=root)
        self.assertEqual(rc, 1)
        self.assertTrue(any(h.startswith("H9:") and "src/sneaky.py" in h
                            for h in payload["hard_failures"]), payload["hard_failures"])

    def test_destructive_op_fails_h10(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = init_repo(root)
            (root / "src" / "widget.py").write_text(
                "import os\nos.remove('f')\n", encoding="utf-8")
            stub = write_stub(root, ["src/widget.py"])
            payload, rc = run_json(str(stub), "--express", "--post", "--base", base, cwd=root)
        self.assertEqual(rc, 1)
        self.assertTrue(any(h.startswith("H10:") for h in payload["hard_failures"]),
                        payload["hard_failures"])

    def test_durable_write_fails_h8(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = init_repo(root)
            (root / "src" / "widget.py").write_text(
                "def f(repo, e):\n    repo.save(e)\n", encoding="utf-8")
            stub = write_stub(root, ["src/widget.py"])
            payload, rc = run_json(str(stub), "--express", "--post", "--base", base, cwd=root)
        self.assertEqual(rc, 1)
        self.assertTrue(any(h.startswith("H8:") for h in payload["hard_failures"]),
                        payload["hard_failures"])

    def test_stub_file_in_tree_not_flagged_h9(self):
        # The lane's own stub must not count as an out-of-lease file.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = init_repo(root)
            (root / "src" / "widget.py").write_text("x = 2\n", encoding="utf-8")
            stub = write_stub(root, ["src/widget.py"])  # written into the tree, untracked
            payload, rc = run_json(str(stub), "--express", "--post", "--base", base, cwd=root)
        self.assertEqual(rc, 0, payload["hard_failures"])


# --- exit-2: garbled input & bad invocation ---------------------------------

class Exit2Contract(unittest.TestCase):
    def test_missing_stub_is_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            payload, rc = run_json(str(Path(tmp) / "nope.json"), "--express")
        self.assertEqual(rc, 2)
        self.assertEqual(payload["status"], "error")

    def test_invalid_json_is_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "express.json"
            bad.write_text("not json", encoding="utf-8")
            payload, rc = run_json(str(bad), "--express")
        self.assertEqual(rc, 2)
        self.assertEqual(payload["status"], "error")

    def test_non_object_stub_is_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "express.json"
            bad.write_text("[1, 2, 3]", encoding="utf-8")
            payload, rc = run_json(str(bad), "--express")
        self.assertEqual(rc, 2)

    def test_empty_files_list_is_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            stub = write_stub(Path(tmp), [])
            payload, rc = run_json(str(stub), "--express")
        self.assertEqual(rc, 2)

    def test_files_not_list_is_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "express.json"
            bad.write_text(json.dumps({"files": "src/widget.py"}), encoding="utf-8")
            payload, rc = run_json(str(bad), "--express")
        self.assertEqual(rc, 2)

    def test_directory_arg_resolves_express_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_stub(root, ["src/widget.py"])          # writes <dir>/express.json
            payload, rc = run_json(str(root), "--express")  # pass the DIR, not the file
        self.assertEqual(rc, 0, payload["hard_failures"])

    def test_express_post_without_base_is_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_repo(root)
            stub = write_stub(root, ["src/widget.py"])
            payload, rc = run_json(str(stub), "--express", "--post", cwd=root)
        self.assertEqual(rc, 2)
        self.assertEqual(payload["status"], "error")

    def test_express_with_pre_is_usage_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            stub = write_stub(Path(tmp), ["src/widget.py"])
            proc = run_lint(str(stub), "--express", "--pre")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("combines only with --post", proc.stderr)

    def test_no_mode_is_usage_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            stub = write_stub(Path(tmp), ["src/widget.py"])
            proc = run_lint(str(stub))
        self.assertEqual(proc.returncode, 2)


# --- the three legacy modes still resolve (regression on the argparse rewrite) --

class LegacyModesStillWork(unittest.TestCase):
    def test_eligibility_missing_file_still_exit_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            payload, rc = run_json(str(Path(tmp)), "--eligibility")
        self.assertEqual(rc, 2)

    def test_two_primary_modes_is_usage_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc = run_lint(str(Path(tmp)), "--eligibility", "--pre")
        self.assertEqual(proc.returncode, 2)


if __name__ == "__main__":
    unittest.main()
