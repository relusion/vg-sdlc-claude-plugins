"""Adversarial tests for deterministic single-feature architecture retirement."""

import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


REPO = Path(__file__).resolve().parents[1]
SCRIPT = (
    REPO
    / "plugins/core-engineering/skills/ce-architecture/scripts/architecture-retire.py"
)

_spec = importlib.util.spec_from_file_location("architecture_retire_mod", SCRIPT)
ar = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ar)


def _case(workspace: Path, slug: str = "single-feature") -> tuple[Path, Path, Path]:
    repo = workspace / "repo"
    plan = repo / "docs/plans" / slug
    architecture = plan / "architecture"
    architecture.mkdir(parents=True)
    return repo, plan, architecture


def _write(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def _entry_map(payload: dict) -> dict[str, dict]:
    return {item["path"]: item for item in payload["inventory"]["entries"]}


class ArchitectureRetireInventory(unittest.TestCase):
    def test_inventory_is_stable_typed_and_content_bound(self):
        with tempfile.TemporaryDirectory() as td:
            repo, _, architecture = _case(Path(td))
            _write(architecture / "z.txt", "payload\n")
            (architecture / "empty").mkdir()
            external = Path(td) / "outside.txt"
            _write(external, "keep\n")
            (architecture / "outside-link").symlink_to(external)
            if hasattr(os, "mkfifo"):
                os.mkfifo(architecture / "named-pipe")

            first, first_code = ar.inventory_architecture(repo, "single-feature")
            second, second_code = ar.inventory_architecture(repo, "single-feature")

            self.assertEqual((first_code, second_code), (0, 0))
            self.assertEqual(first["status"], "ready")
            self.assertEqual(first["inventory"], second["inventory"])
            self.assertRegex(first["inventory"]["token"], r"^[0-9a-f]{64}$")
            entries = _entry_map(first)
            self.assertEqual(entries["."]["type"], "directory")
            self.assertEqual(entries["empty"]["type"], "directory")
            self.assertEqual(entries["z.txt"]["type"], "regular-file")
            self.assertEqual(
                entries["z.txt"]["sha256"],
                hashlib.sha256(b"payload\n").hexdigest(),
            )
            self.assertEqual(entries["outside-link"]["type"], "symlink")
            self.assertEqual(entries["outside-link"]["link_target"], str(external))
            self.assertNotIn("outside-link/anything", entries)
            if hasattr(os, "mkfifo"):
                self.assertEqual(entries["named-pipe"]["type"], "fifo")

            _write(architecture / "z.txt", "changed\n")
            changed, code = ar.inventory_architecture(repo, "single-feature")
            self.assertEqual(code, 0)
            self.assertNotEqual(
                changed["inventory"]["token"], first["inventory"]["token"]
            )

    def test_absent_target_is_a_successful_absence_inventory(self):
        with tempfile.TemporaryDirectory() as td:
            repo, _, architecture = _case(Path(td))
            architecture.rmdir()
            result, code = ar.inventory_architecture(repo, "single-feature")
            self.assertEqual(code, 0)
            self.assertEqual(result["status"], "absent")
            self.assertFalse(result["present"])
            self.assertIsNone(result["inventory"])

    def test_symlink_and_broken_symlink_roots_are_present_but_refused(self):
        for label, target_exists in (("symlink", True), ("broken", False)):
            with self.subTest(label=label), tempfile.TemporaryDirectory() as td:
                repo, _, architecture = _case(Path(td))
                architecture.rmdir()
                external = Path(td) / "external-architecture"
                if target_exists:
                    external.mkdir()
                    _write(external / "do-not-read.txt", "outside\n")
                architecture.symlink_to(external, target_is_directory=True)

                result, code = ar.inventory_architecture(repo, "single-feature")

                self.assertEqual(code, 1)
                self.assertEqual(result["status"], "refused")
                self.assertTrue(result["present"])
                self.assertEqual(result["target_type"], "symlink")
                self.assertEqual(
                    [item["path"] for item in result["inventory"]["entries"]],
                    ["."],
                )
                self.assertTrue(architecture.is_symlink())
                if target_exists:
                    self.assertTrue((external / "do-not-read.txt").is_file())

    def test_regular_file_root_is_present_but_refused(self):
        with tempfile.TemporaryDirectory() as td:
            repo, _, architecture = _case(Path(td))
            architecture.rmdir()
            _write(architecture, "not a directory\n")
            result, code = ar.inventory_architecture(repo, "single-feature")
            self.assertEqual(code, 1)
            self.assertTrue(result["present"])
            self.assertEqual(result["target_type"], "regular-file")
            self.assertTrue(architecture.is_file())

    def test_strict_slug_and_real_parent_components_are_required(self):
        with tempfile.TemporaryDirectory() as td:
            repo, _, architecture = _case(Path(td))
            result, code = ar.inventory_architecture(repo, "../single-feature")
            self.assertEqual(code, 1)
            self.assertEqual(result["status"], "refused")
            self.assertIsNone(result["target"])
            self.assertTrue(architecture.is_dir())

        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td)
            repo = workspace / "repo"
            repo.mkdir()
            external_docs = workspace / "external-docs"
            (external_docs / "plans/single-feature/architecture").mkdir(parents=True)
            (repo / "docs").symlink_to(external_docs, target_is_directory=True)
            result, code = ar.inventory_architecture(repo, "single-feature")
            self.assertEqual(code, 1)
            self.assertIn("must not be a symlink", result["message"])
            self.assertTrue(
                (external_docs / "plans/single-feature/architecture").is_dir()
            )


class ArchitectureRetireMutation(unittest.TestCase):
    def test_retirement_requires_matching_explicit_token(self):
        with tempfile.TemporaryDirectory() as td:
            repo, plan, architecture = _case(Path(td))
            _write(architecture / "keep-until-approved.txt", "bytes\n")

            missing, missing_code = ar.retire_architecture(
                repo, "single-feature", None
            )
            self.assertEqual(missing_code, 1)
            self.assertEqual(missing["status"], "refused")
            self.assertTrue(architecture.is_dir())

            stale, stale_code = ar.retire_architecture(
                repo, "single-feature", "0" * 64
            )
            self.assertEqual(stale_code, 1)
            self.assertIn("token changed", stale["message"])
            self.assertTrue((architecture / "keep-until-approved.txt").is_file())
            self.assertFalse((plan / ar.TRANSACTION_LOCK).exists())

    def test_retirement_is_bottom_up_and_unlinks_external_symlinks(self):
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td)
            repo, plan, architecture = _case(workspace)
            _write(architecture / "nested/deeper/file.txt", "inside\n")
            _write(architecture / "root.txt", "root\n")
            external = workspace / "external"
            external.mkdir()
            _write(external / "preserved.txt", "outside\n")
            (architecture / "nested/external-link").symlink_to(
                external, target_is_directory=True
            )
            if hasattr(os, "mkfifo"):
                os.mkfifo(architecture / "nested/pipe")

            inspected, inventory_code = ar.inventory_architecture(
                repo, "single-feature"
            )
            result, code = ar.retire_architecture(
                repo,
                "single-feature",
                inspected["inventory"]["token"],
            )

            self.assertEqual(inventory_code, 0)
            self.assertEqual(code, 0, result)
            self.assertEqual(result["status"], "retired")
            self.assertFalse(os.path.lexists(architecture))
            self.assertTrue((external / "preserved.txt").is_file())
            self.assertFalse((plan / ar.TRANSACTION_LOCK).exists())
            removed = result["removed_paths"]
            self.assertLess(removed.index("nested/deeper/file.txt"), removed.index("nested/deeper"))
            self.assertLess(removed.index("nested/deeper"), removed.index("nested"))
            self.assertEqual(removed[-1], ".")

    def test_any_preexisting_transaction_sibling_refuses_without_cleanup(self):
        for name, kind in (
            (".architecture-publish-lock", "file"),
            (".architecture-publish-stage-live", "directory"),
            (".architecture-publish-backup-broken", "symlink"),
        ):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as td:
                repo, plan, architecture = _case(Path(td))
                _write(architecture / "package.txt", "keep\n")
                inspected, _ = ar.inventory_architecture(repo, "single-feature")
                sibling = plan / name
                if kind == "file":
                    _write(sibling, "owned elsewhere\n")
                elif kind == "directory":
                    sibling.mkdir()
                else:
                    sibling.symlink_to(Path(td) / "missing")

                result, code = ar.retire_architecture(
                    repo, "single-feature", inspected["inventory"]["token"]
                )

                self.assertEqual(code, 1)
                self.assertEqual(result["status"], "refused")
                self.assertTrue((architecture / "package.txt").is_file())
                self.assertTrue(os.path.lexists(sibling))

    def test_locked_second_token_check_detects_a_change(self):
        with tempfile.TemporaryDirectory() as td:
            repo, plan, architecture = _case(Path(td))
            package_file = architecture / "package.txt"
            _write(package_file, "reviewed\n")
            inspected, _ = ar.inventory_architecture(repo, "single-feature")
            original = ar._inventory_from_plan_fd
            calls = 0

            def inventory_then_change(plan_fd, target):
                nonlocal calls
                value = original(plan_fd, target)
                calls += 1
                if calls == 1:
                    _write(package_file, "changed after first locked check\n")
                return value

            with mock.patch.object(
                ar, "_inventory_from_plan_fd", side_effect=inventory_then_change
            ):
                result, code = ar.retire_architecture(
                    repo, "single-feature", inspected["inventory"]["token"]
                )

            self.assertEqual(code, 1, result)
            self.assertIn("locked token recheck", result["message"])
            self.assertTrue(package_file.is_file())
            self.assertEqual(result["removed_paths"], [])
            self.assertFalse((plan / ar.TRANSACTION_LOCK).exists())

    def test_mid_removal_error_is_structured_and_reports_removed_paths(self):
        with tempfile.TemporaryDirectory() as td:
            repo, plan, architecture = _case(Path(td))
            _write(architecture / "a-first.txt", "first\n")
            _write(architecture / "b-fails.txt", "second\n")
            inspected, _ = ar.inventory_architecture(repo, "single-feature")
            real_unlink = ar.os.unlink

            def fail_second(name, *args, **kwargs):
                if name == "b-fails.txt":
                    raise PermissionError("simulated unlink refusal")
                return real_unlink(name, *args, **kwargs)

            with mock.patch.object(
                ar, "_platform_safety_check", return_value=None
            ), mock.patch.object(ar.os, "unlink", side_effect=fail_second):
                result, code = ar.retire_architecture(
                    repo, "single-feature", inspected["inventory"]["token"]
                )

            self.assertEqual(code, 2, result)
            self.assertEqual(result["status"], "error")
            self.assertEqual(result["removed_paths"], ["a-first.txt"])
            self.assertFalse((architecture / "a-first.txt").exists())
            self.assertTrue((architecture / "b-fails.txt").is_file())
            self.assertFalse((plan / ar.TRANSACTION_LOCK).exists())


class ArchitectureRetireCli(unittest.TestCase):
    def _run(self, repo: Path, *extra: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--repo-root",
                str(repo),
                "--plan-slug",
                "single-feature",
                *extra,
                "--json",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )

    def test_cli_inventory_and_retirement_are_structured(self):
        with tempfile.TemporaryDirectory() as td:
            repo, _, architecture = _case(Path(td))
            _write(architecture / "package.txt", "retire me\n")

            inventory_proc = self._run(repo)
            self.assertEqual(inventory_proc.returncode, 0, inventory_proc.stderr)
            inventory = json.loads(inventory_proc.stdout)
            self.assertEqual(inventory["status"], "ready")

            retire_proc = self._run(
                repo,
                "--retire",
                "--expected-token",
                inventory["inventory"]["token"],
            )
            self.assertEqual(retire_proc.returncode, 0, retire_proc.stderr)
            retired = json.loads(retire_proc.stdout)
            self.assertEqual(retired["status"], "retired")
            self.assertEqual(retired["target"], "docs/plans/single-feature/architecture")
            self.assertFalse(os.path.lexists(architecture))

    def test_cli_refusal_has_json_and_no_traceback(self):
        with tempfile.TemporaryDirectory() as td:
            repo, _, architecture = _case(Path(td))
            _write(architecture / "package.txt", "keep\n")
            proc = self._run(repo, "--retire", "--expected-token", "invalid")
            self.assertEqual(proc.returncode, 1)
            self.assertEqual(json.loads(proc.stdout)["status"], "refused")
            self.assertNotIn("Traceback", proc.stderr)
            self.assertTrue(architecture.is_dir())


if __name__ == "__main__":
    unittest.main()
