"""Focused tests for ce-architecture's transactional publication helper."""

import copy
import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
SCRIPT = (
    REPO
    / "plugins/core-engineering/skills/ce-architecture/scripts/architecture-publish.py"
)
GOLDEN_ROOT = REPO / "evals/golden/EVAL-020"
SLUG = "team-invitations-rbac"

_spec = importlib.util.spec_from_file_location("architecture_publish_mod", SCRIPT)
ap = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ap)


def _save_manifest(package: Path, manifest: dict) -> None:
    (package / "architecture.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )


def _set_architecture_revision(package: Path, manifest: dict, revision: int) -> None:
    current = manifest["architecture_revision"]
    overview = package / "solution-architecture.md"
    text = overview.read_text(encoding="utf-8")
    current_banner = f"> Architecture revision: {current}"
    if text.count(current_banner) != 1:
        raise AssertionError(
            f"expected exactly one reviewed architecture revision banner: {current_banner}"
        )
    overview.write_text(
        text.replace(current_banner, f"> Architecture revision: {revision}"),
        encoding="utf-8",
    )
    manifest["architecture_revision"] = revision


def _fingerprint(path: Path) -> dict[str, str]:
    return {
        item.relative_to(path).as_posix(): hashlib.sha256(item.read_bytes()).hexdigest()
        for item in sorted(path.rglob("*"))
        if item.is_file()
    }


def _package_case(workspace: Path) -> tuple[Path, Path, Path, dict]:
    root = workspace / "repo"
    shutil.copytree(GOLDEN_ROOT, root, dirs_exist_ok=True)
    target = root / f"docs/plans/{SLUG}/architecture"
    manifest = json.loads((target / "architecture.json").read_text(encoding="utf-8"))
    scratch = workspace / "scratch-architecture"
    shutil.copytree(target, scratch)
    manifest["status"] = "proposed"
    manifest["approval"] = copy.deepcopy(ap.PENDING_APPROVAL)
    _save_manifest(scratch, manifest)
    return root, target, scratch, manifest


class ArchitecturePublish(unittest.TestCase):
    def test_unexpected_lint_result_decoding_exception_is_structured(self):
        completed = subprocess.CompletedProcess(
            args=["architecture-lint.py"],
            returncode=0,
            stdout="{}",
            stderr="",
        )
        with mock.patch.object(ap.subprocess, "run", return_value=completed), \
                mock.patch.object(
                    ap.json,
                    "loads",
                    side_effect=RuntimeError("simulated decoder failure"),
                ):
            result = ap.run_lint(Path("/unused"), REPO)

        self.assertEqual(result["exit_code"], 2)
        self.assertEqual(result["process_exit_code"], 0)
        self.assertEqual(result["status"], "error")
        self.assertIn("RuntimeError", result["error"])
        assessment = ap._assess_lint_result(result)
        self.assertTrue(assessment["coherent"])
        self.assertEqual(assessment["outcome"], "error")

    def test_first_publication_succeeds_and_emits_structured_json(self):
        with tempfile.TemporaryDirectory() as td:
            root, target, scratch, reviewed = _package_case(Path(td))
            markdown_bytes = {
                name: (scratch / name).read_bytes()
                for name in ap.PACKAGE_FILES - {"architecture.json"}
            }
            shutil.rmtree(target)

            proc = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    str(scratch),
                    "--repo-root",
                    str(root),
                    "--plan-slug",
                    SLUG,
                    "--publish-status",
                    "approved",
                    "--json",
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            result = json.loads(proc.stdout)
            self.assertEqual(result["status"], "published")
            self.assertEqual(result["published_revision"], 1)
            self.assertEqual(result["final_lint"]["status"], "pass")
            self.assertFalse(result["transaction"]["crash_consistent"])
            self.assertEqual(
                {item.name for item in target.iterdir()}, ap.PACKAGE_FILES
            )
            for name, expected_bytes in markdown_bytes.items():
                self.assertEqual((target / name).read_bytes(), expected_bytes)
            expected_manifest = copy.deepcopy(reviewed)
            expected_manifest["status"] = "approved"
            expected_manifest["approval"] = {
                "decision": "approved",
                "recorded_by": "human",
                "gate": ap.FINAL_APPROVAL_GATE,
            }
            published_manifest = json.loads(
                (target / "architecture.json").read_text(encoding="utf-8")
            )
            self.assertEqual(published_manifest, expected_manifest)
            for key in reviewed.keys() - {"status", "approval"}:
                self.assertEqual(published_manifest[key], reviewed[key])
            self.assertTrue(scratch.is_dir(), "publisher must not consume scratch")
            self.assertEqual(
                list(target.parent.glob(".architecture-publish-*")), [],
                "successful publication must leave no transaction directory",
            )

    def test_scratch_pre_lint_failure_preserves_valid_old_package(self):
        with tempfile.TemporaryDirectory() as td:
            root, target, scratch, manifest = _package_case(Path(td))
            before = _fingerprint(target)
            _set_architecture_revision(scratch, manifest, 2)
            manifest["relationships"][0]["to"] = "C-999"
            _save_manifest(scratch, manifest)

            result, code = ap.publish_package(
                scratch, root, SLUG, publish_status="approved"
            )
            self.assertEqual(code, 1)
            self.assertEqual(result["status"], "refused")
            self.assertIn("scratch architecture lint failed", result["message"])
            self.assertEqual(_fingerprint(target), before)
            self.assertFalse(result["rollback"]["attempted"])

    def test_revision_banner_mismatch_is_pre_lint_refusal(self):
        with tempfile.TemporaryDirectory() as td:
            root, target, scratch, manifest = _package_case(Path(td))
            before = _fingerprint(target)
            _set_architecture_revision(scratch, manifest, 2)
            _save_manifest(scratch, manifest)
            overview = scratch / "solution-architecture.md"
            overview.write_text(
                overview.read_text(encoding="utf-8").replace(
                    "> Architecture revision: 2",
                    "> Architecture revision: 1",
                ),
                encoding="utf-8",
            )

            result, code = ap.publish_package(
                scratch, root, SLUG, publish_status="approved"
            )

            self.assertEqual(code, 1)
            self.assertEqual(result["status"], "refused")
            self.assertIn("Architecture revision must equal 2", result["message"])
            self.assertEqual(_fingerprint(target), before)
            self.assertFalse(result["rollback"]["attempted"])
            self.assertEqual(
                list(target.parent.glob(".architecture-publish-*")), []
            )

    def test_unexpected_existing_entry_refuses_without_cleanup_authority(self):
        with tempfile.TemporaryDirectory() as td:
            root, target, scratch, manifest = _package_case(Path(td))
            _set_architecture_revision(scratch, manifest, 2)
            _save_manifest(scratch, manifest)
            (target / "operator-notes.txt").write_text("keep me\n", encoding="utf-8")

            result, code = ap.publish_package(
                scratch, root, SLUG, publish_status="approved"
            )
            self.assertEqual(code, 1)
            self.assertIn("--allow-extra-cleanup", result["message"])
            self.assertTrue((target / "operator-notes.txt").is_file())
            self.assertEqual(
                json.loads((target / "architecture.json").read_text())["architecture_revision"],
                1,
            )

    def test_malformed_prior_requires_cli_and_durable_human_reset(self):
        with tempfile.TemporaryDirectory() as td:
            root, target, scratch, manifest = _package_case(Path(td))
            malformed = "{not-json\n"
            (target / "architecture.json").write_text(malformed, encoding="utf-8")
            manifest["revision_reset"] = {
                "reason": (
                    "The prior manifest is unreadable; architecture owner approved "
                    "a new baseline."
                ),
                "recorded_by": "human",
                "gate": ap.RESET_GATE,
            }
            _save_manifest(scratch, manifest)

            result, code = ap.publish_package(
                scratch, root, SLUG, publish_status="approved"
            )
            self.assertEqual(code, 1)
            self.assertIn("--accept-human-approved-reset", result["message"])
            self.assertEqual((target / "architecture.json").read_text(), malformed)

            no_record = dict(manifest)
            no_record.pop("revision_reset")
            _save_manifest(scratch, no_record)
            result, code = ap.publish_package(
                scratch,
                root,
                SLUG,
                publish_status="approved",
                accept_human_approved_reset=True,
            )
            self.assertEqual(code, 1)
            self.assertIn("revision_reset", result["message"])
            self.assertEqual((target / "architecture.json").read_text(), malformed)

            _save_manifest(scratch, manifest)
            result, code = ap.publish_package(
                scratch,
                root,
                SLUG,
                publish_status="approved",
                accept_human_approved_reset=True,
            )
            self.assertEqual(code, 0, result)
            self.assertEqual(result["status"], "published")
            published = json.loads((target / "architecture.json").read_text())
            self.assertEqual(published["architecture_revision"], 1)
            self.assertEqual(published["revision_reset"]["recorded_by"], "human")

    def test_final_lint_failure_rolls_back_valid_old_package(self):
        with tempfile.TemporaryDirectory() as td:
            root, target, scratch, manifest = _package_case(Path(td))
            before = _fingerprint(target)
            _set_architecture_revision(scratch, manifest, 2)
            _save_manifest(scratch, manifest)
            real_run_lint = ap.run_lint
            target_calls = 0

            def fail_only_final(
                package: Path,
                repo_root: Path,
                *,
                allow_proposed: bool = False,
            ) -> dict:
                nonlocal target_calls
                result = real_run_lint(
                    package, repo_root, allow_proposed=allow_proposed
                )
                if package.resolve() == target.resolve():
                    target_calls += 1
                    if target_calls == 2:
                        return {
                            "exit_code": 1,
                            "status": "fail",
                            "hard_failures": ["simulated final validation failure"],
                        }
                return result

            with mock.patch.object(ap, "run_lint", side_effect=fail_only_final):
                result, code = ap.publish_package(
                    scratch, root, SLUG, publish_status="approved"
                )

            self.assertEqual(code, 1, result)
            self.assertEqual(result["status"], "rolled-back")
            self.assertTrue(result["rollback"]["attempted"])
            self.assertTrue(result["rollback"]["restored"])
            self.assertEqual(_fingerprint(target), before)
            self.assertEqual(
                list(target.parent.glob(".architecture-publish-*")), []
            )

    def test_incoherent_pre_lint_payload_is_runtime_error_without_mutation(self):
        with tempfile.TemporaryDirectory() as td:
            root, target, scratch, manifest = _package_case(Path(td))
            _set_architecture_revision(scratch, manifest, 2)
            _save_manifest(scratch, manifest)
            before = _fingerprint(target)
            real_run_lint = ap.run_lint

            def corrupt_pre_result(
                package: Path,
                repo_root: Path,
                *,
                allow_proposed: bool = False,
            ) -> dict:
                if allow_proposed:
                    return {
                        "exit_code": 0,
                        "status": "error",
                        "error": "simulated non-JSON linter output",
                    }
                return real_run_lint(
                    package, repo_root, allow_proposed=allow_proposed
                )

            with mock.patch.object(ap, "run_lint", side_effect=corrupt_pre_result):
                result, code = ap.publish_package(
                    scratch, root, SLUG, publish_status="approved"
                )

            self.assertEqual(code, 2)
            self.assertEqual(result["status"], "error")
            self.assertFalse(result["prelint_validation"]["coherent"])
            self.assertEqual(result["prelint_validation"]["outcome"], "error")
            self.assertEqual(_fingerprint(target), before)
            self.assertEqual(
                list(target.parent.glob(".architecture-publish-*")), []
            )

    def test_contradictory_stage_lint_payload_is_error_without_target_mutation(self):
        with tempfile.TemporaryDirectory() as td:
            root, target, scratch, manifest = _package_case(Path(td))
            _set_architecture_revision(scratch, manifest, 2)
            _save_manifest(scratch, manifest)
            before = _fingerprint(target)
            real_run_lint = ap.run_lint

            def corrupt_stage_result(
                package: Path,
                repo_root: Path,
                *,
                allow_proposed: bool = False,
            ) -> dict:
                if package.name.startswith(".architecture-publish-stage-"):
                    return {
                        "schema_version": 1,
                        "exit_code": 0,
                        "status": "fail",
                        "blocking_hard": 1,
                        "hard_failures": ["simulated contradictory result"],
                        "advisory": [],
                    }
                return real_run_lint(
                    package, repo_root, allow_proposed=allow_proposed
                )

            with mock.patch.object(ap, "run_lint", side_effect=corrupt_stage_result):
                result, code = ap.publish_package(
                    scratch, root, SLUG, publish_status="approved"
                )

            self.assertEqual(code, 2)
            self.assertEqual(result["status"], "error")
            self.assertFalse(result["stage_lint_validation"]["coherent"])
            self.assertEqual(_fingerprint(target), before)
            self.assertEqual(
                list(target.parent.glob(".architecture-publish-*")), []
            )

    def test_contradictory_final_lint_payload_rolls_back(self):
        with tempfile.TemporaryDirectory() as td:
            root, target, scratch, manifest = _package_case(Path(td))
            _set_architecture_revision(scratch, manifest, 2)
            _save_manifest(scratch, manifest)
            before = _fingerprint(target)
            real_run_lint = ap.run_lint
            target_calls = 0

            def corrupt_final_result(
                package: Path,
                repo_root: Path,
                *,
                allow_proposed: bool = False,
            ) -> dict:
                nonlocal target_calls
                result = real_run_lint(
                    package, repo_root, allow_proposed=allow_proposed
                )
                if package.resolve() == target.resolve():
                    target_calls += 1
                    if target_calls == 2:
                        return {
                            "schema_version": 1,
                            "exit_code": 0,
                            "status": "pass",
                            "blocking_hard": 1,
                            "hard_failures": ["hidden failure"],
                            "advisory": [],
                        }
                return result

            with mock.patch.object(ap, "run_lint", side_effect=corrupt_final_result):
                result, code = ap.publish_package(
                    scratch, root, SLUG, publish_status="approved"
                )

            self.assertEqual(code, 1, result)
            self.assertEqual(result["status"], "rolled-back")
            self.assertFalse(result["final_lint_validation"]["coherent"])
            self.assertEqual(result["final_lint_validation"]["outcome"], "error")
            self.assertTrue(result["rollback"]["restored"])
            self.assertEqual(_fingerprint(target), before)
            self.assertEqual(
                list(target.parent.glob(".architecture-publish-*")), []
            )

    def test_final_lint_unicode_decode_error_is_structured_and_rolls_back(self):
        with tempfile.TemporaryDirectory() as td:
            root, target, scratch, manifest = _package_case(Path(td))
            _set_architecture_revision(scratch, manifest, 2)
            _save_manifest(scratch, manifest)
            before = _fingerprint(target)
            real_run_lint = ap.run_lint
            lint_calls = 0
            coherent_pass = {
                "schema_version": 1,
                "exit_code": 0,
                "status": "pass",
                "blocking_hard": 0,
                "hard_failures": [],
                "advisory": [],
            }

            def decode_error_on_final(
                package: Path,
                repo_root: Path,
                *,
                allow_proposed: bool = False,
            ) -> dict:
                nonlocal lint_calls
                lint_calls += 1
                if lint_calls != 4:
                    return dict(coherent_pass)
                decode_error = UnicodeDecodeError(
                    "utf-8",
                    b"\xff",
                    0,
                    1,
                    "simulated invalid linter output",
                )
                with mock.patch.object(
                    ap.subprocess,
                    "run",
                    side_effect=decode_error,
                ):
                    return real_run_lint(
                        package,
                        repo_root,
                        allow_proposed=allow_proposed,
                    )

            with mock.patch.object(
                ap,
                "run_lint",
                side_effect=decode_error_on_final,
            ):
                result, code = ap.publish_package(
                    scratch, root, SLUG, publish_status="approved"
                )

            self.assertEqual(code, 1, result)
            self.assertEqual(result["status"], "rolled-back")
            self.assertEqual(result["final_lint"]["exit_code"], 2)
            self.assertEqual(result["final_lint"]["status"], "error")
            self.assertIn("UnicodeDecodeError", result["final_lint"]["error"])
            self.assertTrue(result["final_lint_validation"]["coherent"])
            self.assertEqual(result["final_lint_validation"]["outcome"], "error")
            self.assertTrue(result["rollback"]["restored"])
            self.assertEqual(_fingerprint(target), before)
            self.assertEqual(
                list(target.parent.glob(".architecture-publish-*")), []
            )

    def test_missing_expected_backup_cannot_be_reported_as_restored(self):
        with tempfile.TemporaryDirectory() as td:
            root, target, scratch, manifest = _package_case(Path(td))
            _set_architecture_revision(scratch, manifest, 2)
            _save_manifest(scratch, manifest)
            target_calls = 0
            coherent_pass = {
                "schema_version": 1,
                "exit_code": 0,
                "status": "pass",
                "blocking_hard": 0,
                "hard_failures": [],
                "advisory": [],
            }

            def lose_backup_before_final_failure(
                package: Path,
                repo_root: Path,
                *,
                allow_proposed: bool = False,
            ) -> dict:
                nonlocal target_calls
                if package.resolve() == target.resolve():
                    target_calls += 1
                    if target_calls == 2:
                        backups = list(
                            target.parent.glob(".architecture-publish-backup-*")
                        )
                        self.assertEqual(len(backups), 1)
                        shutil.rmtree(backups[0])
                        return {
                            "schema_version": 1,
                            "exit_code": 1,
                            "status": "fail",
                            "blocking_hard": 1,
                            "hard_failures": ["simulated final failure"],
                            "advisory": [],
                        }
                return dict(coherent_pass)

            with mock.patch.object(
                ap, "run_lint", side_effect=lose_backup_before_final_failure
            ):
                result, code = ap.publish_package(
                    scratch, root, SLUG, publish_status="approved"
                )

            self.assertEqual(code, 2)
            self.assertEqual(result["status"], "error")
            self.assertFalse(result["rollback"]["restored"])
            self.assertIn("rollback could not be proven", result["message"])
            self.assertFalse(target.exists())
            self.assertEqual(
                len(list(target.parent.glob(".architecture-publish-rejected-*"))),
                1,
            )
            self.assertFalse((target.parent / ap.TRANSACTION_LOCK).exists())

    def test_scratch_symlink_is_refused_before_target_mutation(self):
        with tempfile.TemporaryDirectory() as td:
            root, target, scratch, _ = _package_case(Path(td))
            before = _fingerprint(target)
            overview = scratch / "solution-architecture.md"
            overview.unlink()
            overview.symlink_to(target / "solution-architecture.md")

            result, code = ap.publish_package(
                scratch, root, SLUG, publish_status="approved"
            )
            self.assertEqual(code, 1)
            self.assertIn("symlink entries", result["message"])
            self.assertEqual(_fingerprint(target), before)

    def test_already_published_scratch_is_refused(self):
        with tempfile.TemporaryDirectory() as td:
            root, target, scratch, manifest = _package_case(Path(td))
            before = _fingerprint(target)
            manifest["status"] = "approved"
            manifest["approval"] = {
                "decision": "approved",
                "recorded_by": "human",
                "gate": ap.FINAL_APPROVAL_GATE,
            }
            _save_manifest(scratch, manifest)

            result, code = ap.publish_package(
                scratch, root, SLUG, publish_status="approved"
            )

            self.assertEqual(code, 1)
            self.assertIn("status must be 'proposed'", result["message"])
            self.assertEqual(_fingerprint(target), before)

    def test_readable_invalid_prior_advances_revision_and_forbids_reset(self):
        with tempfile.TemporaryDirectory() as td:
            root, target, scratch, manifest = _package_case(Path(td))
            invalid_prior = json.loads(
                (target / "architecture.json").read_text(encoding="utf-8")
            )
            invalid_prior["relationships"][0]["to"] = "C-999"
            _save_manifest(target, invalid_prior)
            before = _fingerprint(target)
            _set_architecture_revision(scratch, manifest, 2)
            _save_manifest(scratch, manifest)

            refused, refused_code = ap.publish_package(
                scratch,
                root,
                SLUG,
                publish_status="approved",
                accept_human_approved_reset=True,
            )
            self.assertEqual(refused_code, 1)
            self.assertEqual(refused["prior"]["state"], "invalid-readable")
            self.assertIn("readable revision", refused["message"])
            self.assertEqual(_fingerprint(target), before)

            result, code = ap.publish_package(
                scratch, root, SLUG, publish_status="approved"
            )
            self.assertEqual(code, 0, result)
            self.assertEqual(result["prior"]["state"], "invalid-readable")
            self.assertEqual(result["published_revision"], 2)

    def test_orphan_transaction_refuses_with_recovery_details(self):
        with tempfile.TemporaryDirectory() as td:
            root, target, scratch, manifest = _package_case(Path(td))
            _set_architecture_revision(scratch, manifest, 2)
            _save_manifest(scratch, manifest)
            before = _fingerprint(target)
            orphan = target.parent / ".architecture-publish-backup-crashed"
            orphan.mkdir()

            result, code = ap.publish_package(
                scratch, root, SLUG, publish_status="approved"
            )

            self.assertEqual(code, 1)
            self.assertEqual(result["orphan_transactions"], [orphan.name])
            self.assertIn("explicit crash recovery", result["message"])
            self.assertEqual(_fingerprint(target), before)
            self.assertTrue(orphan.is_dir())
            self.assertEqual(
                result["transaction"]["lock"]["disposition"], "released"
            )
            self.assertFalse((target.parent / ap.TRANSACTION_LOCK).exists())

    def test_active_lock_blocks_a_concurrent_publisher(self):
        with tempfile.TemporaryDirectory() as td:
            root, target, scratch, manifest = _package_case(Path(td))
            _set_architecture_revision(scratch, manifest, 2)
            _save_manifest(scratch, manifest)
            before = _fingerprint(target)
            target_rel = Path(f"docs/plans/{SLUG}/architecture")
            lock_path, lock_token, lock_result = ap._acquire_transaction_lock(
                target.parent, target_rel
            )
            self.assertIsNotNone(lock_path)
            self.assertIsNotNone(lock_token)
            self.assertEqual(lock_result["disposition"], "acquired")
            try:
                result, code = ap.publish_package(
                    scratch, root, SLUG, publish_status="approved"
                )
                self.assertEqual(code, 1)
                lock = result["transaction"]["lock"]
                self.assertEqual(lock["disposition"], "blocked-existing")
                self.assertEqual(
                    lock["owner"]["token"], lock_result["owner"]["token"]
                )
                self.assertEqual(
                    result["orphan_transactions"], [ap.TRANSACTION_LOCK]
                )
                self.assertTrue(lock_path.is_file())
                self.assertEqual(_fingerprint(target), before)
            finally:
                ap._release_transaction_lock(lock_path, lock_token)

    def test_crash_leftover_lock_reports_owner_and_requires_recovery(self):
        with tempfile.TemporaryDirectory() as td:
            root, target, scratch, manifest = _package_case(Path(td))
            _set_architecture_revision(scratch, manifest, 2)
            _save_manifest(scratch, manifest)
            before = _fingerprint(target)
            lock_path = target.parent / ap.TRANSACTION_LOCK
            leftover_owner = {
                "schema_version": 1,
                "pid": 4242,
                "created_at": "2026-01-02T03:04:05Z",
                "target": f"docs/plans/{SLUG}/architecture",
                "token": "crash-leftover-token",
            }
            lock_path.write_text(json.dumps(leftover_owner), encoding="utf-8")

            result, code = ap.publish_package(
                scratch, root, SLUG, publish_status="approved"
            )

            self.assertEqual(code, 1)
            lock = result["transaction"]["lock"]
            self.assertEqual(lock["disposition"], "blocked-existing")
            self.assertEqual(lock["owner"]["state"], "readable")
            self.assertEqual(lock["owner"]["pid"], 4242)
            self.assertIn("crash-leftover", result["message"])
            self.assertTrue(lock_path.is_file(), "publisher must not remove an unknown lock")
            self.assertEqual(_fingerprint(target), before)

    def test_backup_cleanup_failure_keeps_valid_target_and_warns(self):
        with tempfile.TemporaryDirectory() as td:
            root, target, scratch, manifest = _package_case(Path(td))
            _set_architecture_revision(scratch, manifest, 2)
            _save_manifest(scratch, manifest)
            real_remove = ap._remove_path

            def refuse_backup_cleanup(path: Path) -> None:
                if path.name.startswith(".architecture-publish-backup-"):
                    raise PermissionError("simulated cleanup denial")
                real_remove(path)

            with mock.patch.object(
                ap, "_remove_path", side_effect=refuse_backup_cleanup
            ):
                result, code = ap.publish_package(
                    scratch, root, SLUG, publish_status="approved"
                )

            self.assertEqual(code, 0, result)
            self.assertEqual(result["status"], "published")
            self.assertFalse(result["cleanup"]["backup_removed"])
            retained = target.parent / result["cleanup"]["retained_backup"]
            self.assertTrue(retained.is_dir())
            self.assertTrue(result["warnings"])
            published = json.loads((target / "architecture.json").read_text())
            self.assertEqual(published["architecture_revision"], 2)

    def test_scratch_directory_symlink_is_refused(self):
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td)
            root, target, scratch, _ = _package_case(workspace)
            before = _fingerprint(target)
            linked = workspace / "scratch-link"
            linked.symlink_to(scratch, target_is_directory=True)

            result, code = ap.publish_package(
                linked, root, SLUG, publish_status="approved"
            )

            self.assertEqual(code, 1)
            self.assertIn("directory must not be a symlink", result["message"])
            self.assertEqual(_fingerprint(target), before)

    def test_scratch_inside_repository_is_refused(self):
        with tempfile.TemporaryDirectory() as td:
            root, target, scratch, _ = _package_case(Path(td))
            before = _fingerprint(target)
            inside = root / "scratch-inside-repository"
            shutil.copytree(scratch, inside)

            result, code = ap.publish_package(
                inside, root, SLUG, publish_status="approved"
            )

            self.assertEqual(code, 1)
            self.assertIn("outside the repository root", result["message"])
            self.assertEqual(_fingerprint(target), before)


if __name__ == "__main__":
    unittest.main()
