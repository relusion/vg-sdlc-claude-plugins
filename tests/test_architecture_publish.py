"""Focused tests for schema-v2 transactional architecture publication."""

from __future__ import annotations

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
FIXTURE = REPO / "tests/architecture_v2_fixture.py"
LEGACY_FIXTURE = REPO / "tests/test_architecture_lint.py"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ap = _load(SCRIPT, "architecture_publish_v2_tests")
v2 = _load(FIXTURE, "architecture_publish_v2_fixture")

APPROVAL = {
    "publish_status": "accepted-for-specification",
    "recorded_by": "architect@example.test",
    "approval_authority": "Solution Architecture Council",
    "approval_reference": "REVIEW-123",
    "approval_time": "2026-07-23T10:30:00Z",
}
COHERENT_PASS = {
    "schema_version": 1,
    "exit_code": 0,
    "status": "pass",
    "blocking_hard": 0,
    "hard_failures": [],
    "advisory": [],
}


def _case(workspace: Path, *, retain_target: bool = False):
    root = workspace / "repo"
    target, manifest = v2.make_v2_repo(root)
    scratch = workspace / "scratch"
    shutil.copytree(target, scratch)
    if not retain_target:
        shutil.rmtree(target)
    return root, target, scratch, manifest


def _render_review(package: Path, manifest: dict) -> dict:
    renderer = ap._load_renderer()
    finalized, documents = renderer.finalize_review_manifest(manifest)
    for path, payload in documents.items():
        (package / path).write_bytes(payload)
    (package / "architecture.json").write_text(
        json.dumps(finalized, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return finalized


def _fingerprint(path: Path) -> dict[str, str]:
    return {
        item.relative_to(path).as_posix(): hashlib.sha256(item.read_bytes()).hexdigest()
        for item in sorted(path.rglob("*"))
        if item.is_file()
    }


def _with_reset(manifest: dict, reset: dict) -> dict:
    result = {}
    for key, value in manifest.items():
        if key == "approval":
            result["revision_reset"] = reset
        result[key] = value
    return result


def _valid_prior_case(workspace: Path):
    root, target, scratch, manifest = _case(workspace, retain_target=True)
    prior_scratch = workspace / "prior-scratch"
    shutil.copytree(target, prior_scratch)
    shutil.rmtree(target)
    result, code = ap.publish_package(
        prior_scratch,
        root,
        "team-invitations",
        **APPROVAL,
    )
    if code != 0:
        raise AssertionError(f"could not prepare valid prior: {result}")
    manifest["architecture_revision"] = 2
    manifest = _render_review(scratch, manifest)
    return root, target, scratch, manifest


class ArchitecturePublishV2(unittest.TestCase):
    def test_first_publication_preserves_reviewed_markdown_and_seals_receipt(self):
        with tempfile.TemporaryDirectory() as td:
            root, target, scratch, reviewed = _case(Path(td))
            markdown = {
                name: (scratch / name).read_bytes()
                for name in ap.PACKAGE_FILES
                if name.endswith(".md")
            }
            result, code = ap.publish_package(
                scratch, root, "team-invitations", **APPROVAL
            )
            self.assertEqual(code, 0, result)
            self.assertEqual(result["status"], "published")
            self.assertEqual(result["pre_render_validation"]["outcome"], "pass")
            self.assertEqual(result["stage_render_validation"]["outcome"], "pass")
            self.assertEqual(result["final_lint_validation"]["outcome"], "pass")
            published = json.loads(
                (target / "architecture.json").read_text(encoding="utf-8")
            )
            self.assertEqual(published["lifecycle_status"], "published")
            self.assertEqual(
                published["baseline_status"], reviewed["baseline_status"]
            )
            self.assertEqual(
                published["approval"]["review_payload_sha256"],
                reviewed["approval"]["review_payload_sha256"],
            )
            self.assertEqual(
                published["approval"]["receipt_sha256"],
                result["package_receipt_sha256"],
            )
            self.assertEqual(
                published["approval"]["receipt_sha256"],
                result["final_lint"]["package_receipt_sha256"],
            )
            for name, payload in markdown.items():
                self.assertEqual((target / name).read_bytes(), payload)

    def test_cli_requires_identity_authority_and_reference(self):
        with tempfile.TemporaryDirectory() as td:
            root, _, scratch, _ = _case(Path(td))
            proc = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    str(scratch),
                    "--repo-root",
                    str(root),
                    "--plan-slug",
                    "team-invitations",
                    "--publish-status",
                    "accepted-for-specification",
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )
            self.assertEqual(proc.returncode, 2)
            self.assertIn("--recorded-by", proc.stderr)

    def test_placeholder_receipt_authority_is_refused(self):
        fields = ("recorded_by", "approval_authority", "approval_reference")
        for field in fields:
            with self.subTest(field=field), tempfile.TemporaryDirectory() as td:
                root, target, scratch, _ = _case(Path(td))
                arguments = {**APPROVAL, field: "TBD"}
                result, code = ap.publish_package(
                    scratch, root, "team-invitations", **arguments
                )
                self.assertEqual(code, 1)
                self.assertEqual(result["status"], "refused")
                self.assertIn("placeholder", result["message"])
                self.assertFalse(target.exists())

    def test_projection_byte_mutation_is_refused_before_lint(self):
        with tempfile.TemporaryDirectory() as td:
            root, target, scratch, _ = _case(Path(td))
            projection = scratch / "views.md"
            projection.write_text(
                projection.read_text(encoding="utf-8") + "\nmanual edit\n",
                encoding="utf-8",
            )
            result, code = ap.publish_package(
                scratch, root, "team-invitations", **APPROVAL
            )
            self.assertEqual(code, 1)
            self.assertIn("render check failed", result["message"])
            self.assertIsNone(result["prelint"])
            self.assertFalse(target.exists())

    def test_review_digest_mutation_is_refused(self):
        with tempfile.TemporaryDirectory() as td:
            root, _, scratch, _ = _case(Path(td))
            manifest = json.loads(
                (scratch / "architecture.json").read_text(encoding="utf-8")
            )
            manifest["approval"]["review_payload_sha256"] = "f" * 64
            (scratch / "architecture.json").write_text(
                json.dumps(manifest, indent=2) + "\n",
                encoding="utf-8",
            )
            result, code = ap.publish_package(
                scratch, root, "team-invitations", **APPROVAL
            )
            self.assertEqual(code, 1)
            self.assertIn("review_payload_sha256", result["message"])

    def test_schema_v1_is_refused_without_running_lint(self):
        with tempfile.TemporaryDirectory() as td:
            root, target, scratch, _ = _case(Path(td))
            manifest = json.loads(
                (scratch / "architecture.json").read_text(encoding="utf-8")
            )
            manifest.pop("$schema")
            manifest["schema_version"] = 1
            (scratch / "architecture.json").write_text(
                json.dumps(manifest, indent=2) + "\n",
                encoding="utf-8",
            )
            result, code = ap.publish_package(
                scratch, root, "team-invitations", **APPROVAL
            )
            self.assertEqual(code, 1)
            self.assertIn("schema v2", result["message"])
            self.assertIsNone(result["prelint"])
            self.assertFalse(target.exists())

    def test_readable_prior_requires_monotonic_revision(self):
        with tempfile.TemporaryDirectory() as td:
            root, target, scratch, manifest = _case(
                Path(td), retain_target=True
            )
            # Publish the current review package as the valid prior.
            prior_scratch = Path(td) / "prior-scratch"
            shutil.copytree(target, prior_scratch)
            shutil.rmtree(target)
            prior_result, prior_code = ap.publish_package(
                prior_scratch, root, "team-invitations", **APPROVAL
            )
            self.assertEqual(prior_code, 0, prior_result)

            result, code = ap.publish_package(
                scratch, root, "team-invitations", **APPROVAL
            )
            self.assertEqual(code, 1)
            self.assertIn("revision must advance", result["message"])

            manifest["architecture_revision"] = 2
            _render_review(scratch, manifest)
            result, code = ap.publish_package(
                scratch, root, "team-invitations", **APPROVAL
            )
            self.assertEqual(code, 0, result)
            self.assertEqual(result["published_revision"], 2)

    def test_readable_schema_v1_prior_can_upgrade_to_v2_next_revision(self):
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td)
            root, target, scratch, manifest = _case(
                workspace, retain_target=True
            )
            manifest["architecture_revision"] = 2
            _render_review(scratch, manifest)

            legacy_root = workspace / "legacy-repo"
            legacy = _load(
                LEGACY_FIXTURE,
                "architecture_publish_legacy_upgrade_fixture",
            )
            legacy_arch, legacy_manifest = legacy._make_repo(legacy_root)
            self.assertEqual(legacy_manifest["schema_version"], 1)
            shutil.rmtree(target)
            shutil.copytree(legacy_arch, target)

            result, code = ap.publish_package(
                scratch, root, "team-invitations", **APPROVAL
            )
            self.assertEqual(code, 0, result)
            self.assertEqual(result["prior"]["state"], "invalid-readable")
            self.assertEqual(result["published_revision"], 2)
            published = json.loads(
                (target / "architecture.json").read_text(encoding="utf-8")
            )
            self.assertEqual(published["schema_version"], 2)
            self.assertEqual(published["architecture_revision"], 2)

    def test_final_lint_failure_rolls_back_prior(self):
        with tempfile.TemporaryDirectory() as td:
            root, target, scratch, _ = _case(Path(td))
            calls = 0
            real = ap.run_lint

            def fail_final(package, repo_root, **kwargs):
                nonlocal calls
                calls += 1
                if calls == 3:
                    return {
                        "schema_version": 1,
                        "status": "fail",
                        "hard_failures": ["H1 injected final failure"],
                        "advisory": [],
                        "blocking_hard": 1,
                        "exit_code": 1,
                    }
                return real(package, repo_root, **kwargs)

            with mock.patch.object(ap, "run_lint", side_effect=fail_final):
                result, code = ap.publish_package(
                    scratch, root, "team-invitations", **APPROVAL
                )
            self.assertEqual(code, 1, result)
            self.assertEqual(result["status"], "rolled-back")
            self.assertTrue(result["rollback"]["restored"])
            self.assertFalse(target.exists(), "first-publish absence must be restored")

    def test_unexpected_lint_result_is_not_trusted(self):
        assessment = ap._assess_lint_result(
            {
                "schema_version": 1,
                "status": "pass",
                "hard_failures": ["contradiction"],
                "advisory": [],
                "blocking_hard": 1,
                "exit_code": 0,
            }
        )
        self.assertEqual(assessment["outcome"], "error")
        self.assertFalse(assessment["coherent"])

    def test_unexpected_lint_decoder_exception_is_structured(self):
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

    def test_scratch_pre_lint_failure_preserves_valid_prior(self):
        with tempfile.TemporaryDirectory() as td:
            root, target, scratch, manifest = _valid_prior_case(Path(td))
            before = _fingerprint(target)
            manifest["relationships"][0]["to"] = "C-999"
            _render_review(scratch, manifest)
            result, code = ap.publish_package(
                scratch, root, "team-invitations", **APPROVAL
            )
            self.assertEqual(code, 1, result)
            self.assertEqual(result["status"], "refused")
            self.assertIn("scratch architecture lint failed", result["message"])
            self.assertEqual(_fingerprint(target), before)
            self.assertFalse(result["rollback"]["attempted"])

    def test_unexpected_prior_entry_requires_cleanup_authority(self):
        with tempfile.TemporaryDirectory() as td:
            root, target, scratch, _ = _valid_prior_case(Path(td))
            note = target / "operator-notes.txt"
            note.write_text("retain until approved cleanup\n", encoding="utf-8")
            before = _fingerprint(target)
            refused, refused_code = ap.publish_package(
                scratch, root, "team-invitations", **APPROVAL
            )
            self.assertEqual(refused_code, 1, refused)
            self.assertIn("--allow-extra-cleanup", refused["message"])
            self.assertEqual(_fingerprint(target), before)
            self.assertTrue(note.is_file())

            result, code = ap.publish_package(
                scratch,
                root,
                "team-invitations",
                allow_extra_cleanup=True,
                **APPROVAL,
            )
            self.assertEqual(code, 0, result)
            self.assertFalse(note.exists())
            self.assertEqual(result["published_revision"], 2)

    def test_malformed_prior_requires_flag_and_durable_reset(self):
        with tempfile.TemporaryDirectory() as td:
            root, target, scratch, manifest = _case(
                Path(td), retain_target=True
            )
            malformed = "{not-json\n"
            (target / "architecture.json").write_text(malformed, encoding="utf-8")
            reset = {
                "reason": (
                    "The architecture owner approved a new baseline because "
                    "the prior manifest is unreadable."
                ),
                "recorded_by": "human",
                "gate": ap.RESET_GATE,
            }
            manifest = _with_reset(manifest, reset)
            _render_review(scratch, manifest)

            refused, refused_code = ap.publish_package(
                scratch, root, "team-invitations", **APPROVAL
            )
            self.assertEqual(refused_code, 1, refused)
            self.assertIn("--accept-human-approved-reset", refused["message"])
            self.assertEqual(
                (target / "architecture.json").read_text(encoding="utf-8"),
                malformed,
            )

            no_record = {
                key: value
                for key, value in manifest.items()
                if key != "revision_reset"
            }
            _render_review(scratch, no_record)
            refused, refused_code = ap.publish_package(
                scratch,
                root,
                "team-invitations",
                accept_human_approved_reset=True,
                **APPROVAL,
            )
            self.assertEqual(refused_code, 1, refused)
            self.assertIn("revision_reset", refused["message"])

            _render_review(scratch, manifest)
            result, code = ap.publish_package(
                scratch,
                root,
                "team-invitations",
                accept_human_approved_reset=True,
                **APPROVAL,
            )
            self.assertEqual(code, 0, result)
            published = json.loads(
                (target / "architecture.json").read_text(encoding="utf-8")
            )
            self.assertEqual(published["architecture_revision"], 1)
            self.assertEqual(
                published["revision_reset"]["recorded_by"], "human"
            )

    def test_final_lint_failure_restores_valid_prior_exactly(self):
        with tempfile.TemporaryDirectory() as td:
            root, target, scratch, _ = _valid_prior_case(Path(td))
            before = _fingerprint(target)
            real_run_lint = ap.run_lint
            target_calls = 0

            def fail_final(package, repo_root, **kwargs):
                nonlocal target_calls
                result = real_run_lint(package, repo_root, **kwargs)
                if package.resolve() == target.resolve():
                    target_calls += 1
                    if target_calls == 2:
                        return {
                            **COHERENT_PASS,
                            "exit_code": 1,
                            "status": "fail",
                            "blocking_hard": 1,
                            "hard_failures": ["simulated final failure"],
                        }
                return result

            with mock.patch.object(ap, "run_lint", side_effect=fail_final):
                result, code = ap.publish_package(
                    scratch, root, "team-invitations", **APPROVAL
                )
            self.assertEqual(code, 1, result)
            self.assertEqual(result["status"], "rolled-back")
            self.assertTrue(result["rollback"]["restored"])
            self.assertEqual(_fingerprint(target), before)
            self.assertEqual(
                list(target.parent.glob(".architecture-publish-*")), []
            )

    def test_incoherent_pre_lint_is_runtime_error_without_mutation(self):
        with tempfile.TemporaryDirectory() as td:
            root, target, scratch, _ = _valid_prior_case(Path(td))
            before = _fingerprint(target)

            def corrupt_pre(package, repo_root, **kwargs):
                if kwargs.get("allow_proposed"):
                    return {
                        "exit_code": 0,
                        "status": "error",
                        "error": "simulated non-JSON output",
                    }
                return ap.run_lint(package, repo_root, **kwargs)

            real_run_lint = ap.run_lint

            def routed(package, repo_root, **kwargs):
                if kwargs.get("allow_proposed"):
                    return corrupt_pre(package, repo_root, **kwargs)
                return real_run_lint(package, repo_root, **kwargs)

            with mock.patch.object(ap, "run_lint", side_effect=routed):
                result, code = ap.publish_package(
                    scratch, root, "team-invitations", **APPROVAL
                )
            self.assertEqual(code, 2, result)
            self.assertEqual(result["status"], "error")
            self.assertFalse(result["prelint_validation"]["coherent"])
            self.assertEqual(_fingerprint(target), before)
            self.assertEqual(
                list(target.parent.glob(".architecture-publish-*")), []
            )

    def test_incoherent_stage_lint_is_error_without_target_mutation(self):
        with tempfile.TemporaryDirectory() as td:
            root, target, scratch, _ = _valid_prior_case(Path(td))
            before = _fingerprint(target)
            real_run_lint = ap.run_lint

            def corrupt_stage(package, repo_root, **kwargs):
                if package.name.startswith(".architecture-publish-stage-"):
                    return {
                        **COHERENT_PASS,
                        "status": "fail",
                        "blocking_hard": 1,
                        "hard_failures": ["contradictory stage result"],
                    }
                return real_run_lint(package, repo_root, **kwargs)

            with mock.patch.object(ap, "run_lint", side_effect=corrupt_stage):
                result, code = ap.publish_package(
                    scratch, root, "team-invitations", **APPROVAL
                )
            self.assertEqual(code, 2, result)
            self.assertEqual(result["status"], "error")
            self.assertFalse(result["stage_lint_validation"]["coherent"])
            self.assertEqual(_fingerprint(target), before)
            self.assertEqual(
                list(target.parent.glob(".architecture-publish-*")), []
            )

    def test_incoherent_final_lint_rolls_back_valid_prior(self):
        with tempfile.TemporaryDirectory() as td:
            root, target, scratch, _ = _valid_prior_case(Path(td))
            before = _fingerprint(target)
            real_run_lint = ap.run_lint
            target_calls = 0

            def corrupt_final(package, repo_root, **kwargs):
                nonlocal target_calls
                result = real_run_lint(package, repo_root, **kwargs)
                if package.resolve() == target.resolve():
                    target_calls += 1
                    if target_calls == 2:
                        return {
                            **COHERENT_PASS,
                            "blocking_hard": 1,
                            "hard_failures": ["hidden final failure"],
                        }
                return result

            with mock.patch.object(ap, "run_lint", side_effect=corrupt_final):
                result, code = ap.publish_package(
                    scratch, root, "team-invitations", **APPROVAL
                )
            self.assertEqual(code, 1, result)
            self.assertEqual(result["status"], "rolled-back")
            self.assertFalse(result["final_lint_validation"]["coherent"])
            self.assertTrue(result["rollback"]["restored"])
            self.assertEqual(_fingerprint(target), before)

    def test_final_lint_unicode_error_is_structured_and_rolls_back(self):
        with tempfile.TemporaryDirectory() as td:
            root, target, scratch, _ = _valid_prior_case(Path(td))
            before = _fingerprint(target)
            real_run_lint = ap.run_lint
            target_calls = 0

            def unicode_final(package, repo_root, **kwargs):
                nonlocal target_calls
                if package.resolve() == target.resolve():
                    target_calls += 1
                    if target_calls == 2:
                        error = UnicodeDecodeError(
                            "utf-8",
                            b"\xff",
                            0,
                            1,
                            "simulated invalid linter output",
                        )
                        return ap._lint_runtime_error(
                            "linter result decoding failed",
                            error,
                            process_exit_code=0,
                        )
                return real_run_lint(package, repo_root, **kwargs)

            with mock.patch.object(ap, "run_lint", side_effect=unicode_final):
                result, code = ap.publish_package(
                    scratch, root, "team-invitations", **APPROVAL
                )
            self.assertEqual(code, 1, result)
            self.assertEqual(result["status"], "rolled-back")
            self.assertEqual(result["final_lint"]["exit_code"], 2)
            self.assertIn("UnicodeDecodeError", result["final_lint"]["error"])
            self.assertTrue(result["final_lint_validation"]["coherent"])
            self.assertTrue(result["rollback"]["restored"])
            self.assertEqual(_fingerprint(target), before)

    def test_missing_expected_backup_is_not_reported_as_restored(self):
        with tempfile.TemporaryDirectory() as td:
            root, target, scratch, _ = _valid_prior_case(Path(td))
            target_calls = 0

            def lose_backup(package, repo_root, **kwargs):
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
                            **COHERENT_PASS,
                            "exit_code": 1,
                            "status": "fail",
                            "blocking_hard": 1,
                            "hard_failures": ["simulated final failure"],
                        }
                return dict(COHERENT_PASS)

            with mock.patch.object(ap, "run_lint", side_effect=lose_backup):
                result, code = ap.publish_package(
                    scratch, root, "team-invitations", **APPROVAL
                )
            self.assertEqual(code, 2, result)
            self.assertEqual(result["status"], "error")
            self.assertFalse(result["rollback"]["restored"])
            self.assertIn("rollback could not be proven", result["message"])
            self.assertFalse(target.exists())
            self.assertEqual(
                len(list(target.parent.glob(".architecture-publish-rejected-*"))),
                1,
            )
            self.assertFalse((target.parent / ap.TRANSACTION_LOCK).exists())

    def test_scratch_file_symlink_is_refused_before_target_mutation(self):
        with tempfile.TemporaryDirectory() as td:
            root, target, scratch, _ = _case(Path(td), retain_target=True)
            before = _fingerprint(target)
            overview = scratch / "solution-architecture.md"
            overview.unlink()
            overview.symlink_to(target / "solution-architecture.md")
            result, code = ap.publish_package(
                scratch, root, "team-invitations", **APPROVAL
            )
            self.assertEqual(code, 1, result)
            self.assertIn("symlink entries", result["message"])
            self.assertEqual(_fingerprint(target), before)

    def test_already_published_scratch_is_refused(self):
        with tempfile.TemporaryDirectory() as td:
            root, target, scratch, _ = _case(Path(td))
            result, code = ap.publish_package(
                scratch, root, "team-invitations", **APPROVAL
            )
            self.assertEqual(code, 0, result)
            published_scratch = Path(td) / "published-scratch"
            shutil.copytree(target, published_scratch)
            before = _fingerprint(target)
            result, code = ap.publish_package(
                published_scratch, root, "team-invitations", **APPROVAL
            )
            self.assertEqual(code, 1, result)
            self.assertIn("lifecycle_status must be 'proposed'", result["message"])
            self.assertEqual(_fingerprint(target), before)

    def test_orphan_transaction_refuses_with_recovery_details(self):
        with tempfile.TemporaryDirectory() as td:
            root, target, scratch, _ = _case(Path(td), retain_target=True)
            before = _fingerprint(target)
            orphan = target.parent / ".architecture-publish-backup-crashed"
            orphan.mkdir()
            result, code = ap.publish_package(
                scratch, root, "team-invitations", **APPROVAL
            )
            self.assertEqual(code, 1, result)
            self.assertEqual(result["orphan_transactions"], [orphan.name])
            self.assertIn("explicit crash recovery", result["message"])
            self.assertEqual(_fingerprint(target), before)
            self.assertTrue(orphan.is_dir())
            self.assertEqual(
                result["transaction"]["lock"]["disposition"], "released"
            )

    def test_active_lock_blocks_concurrent_publisher(self):
        with tempfile.TemporaryDirectory() as td:
            root, target, scratch, _ = _case(Path(td), retain_target=True)
            before = _fingerprint(target)
            target_rel = Path("docs/plans/team-invitations/architecture")
            lock_path, token, lock_result = ap._acquire_transaction_lock(
                target.parent, target_rel
            )
            self.assertIsNotNone(lock_path)
            self.assertIsNotNone(token)
            try:
                result, code = ap.publish_package(
                    scratch, root, "team-invitations", **APPROVAL
                )
                self.assertEqual(code, 1, result)
                lock = result["transaction"]["lock"]
                self.assertEqual(lock["disposition"], "blocked-existing")
                self.assertEqual(
                    lock["owner"]["token"], lock_result["owner"]["token"]
                )
                self.assertTrue(lock_path.is_file())
                self.assertEqual(_fingerprint(target), before)
            finally:
                ap._release_transaction_lock(lock_path, token)

    def test_crash_leftover_lock_reports_owner_and_is_retained(self):
        with tempfile.TemporaryDirectory() as td:
            root, target, scratch, _ = _case(Path(td), retain_target=True)
            before = _fingerprint(target)
            lock_path = target.parent / ap.TRANSACTION_LOCK
            owner = {
                "schema_version": 1,
                "pid": 4242,
                "created_at": "2026-01-02T03:04:05Z",
                "target": "docs/plans/team-invitations/architecture",
                "token": "crash-leftover-token",
            }
            lock_path.write_text(json.dumps(owner), encoding="utf-8")
            result, code = ap.publish_package(
                scratch, root, "team-invitations", **APPROVAL
            )
            self.assertEqual(code, 1, result)
            lock = result["transaction"]["lock"]
            self.assertEqual(lock["disposition"], "blocked-existing")
            self.assertEqual(lock["owner"]["pid"], 4242)
            self.assertIn("crash-leftover", result["message"])
            self.assertTrue(lock_path.is_file())
            self.assertEqual(_fingerprint(target), before)

    def test_backup_cleanup_failure_keeps_published_target_and_warns(self):
        with tempfile.TemporaryDirectory() as td:
            root, target, scratch, _ = _valid_prior_case(Path(td))
            real_remove = ap._remove_path

            def refuse_backup_cleanup(path):
                if path.name.startswith(".architecture-publish-backup-"):
                    raise PermissionError("simulated cleanup denial")
                return real_remove(path)

            with mock.patch.object(
                ap, "_remove_path", side_effect=refuse_backup_cleanup
            ):
                result, code = ap.publish_package(
                    scratch, root, "team-invitations", **APPROVAL
                )
            self.assertEqual(code, 0, result)
            self.assertEqual(result["status"], "published")
            self.assertFalse(result["cleanup"]["backup_removed"])
            retained = target.parent / result["cleanup"]["retained_backup"]
            self.assertTrue(retained.is_dir())
            self.assertTrue(result["warnings"])
            published = json.loads(
                (target / "architecture.json").read_text(encoding="utf-8")
            )
            self.assertEqual(published["architecture_revision"], 2)

    def test_scratch_directory_symlink_is_refused(self):
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td)
            root, target, scratch, _ = _case(workspace, retain_target=True)
            before = _fingerprint(target)
            linked = workspace / "scratch-link"
            linked.symlink_to(scratch, target_is_directory=True)
            result, code = ap.publish_package(
                linked, root, "team-invitations", **APPROVAL
            )
            self.assertEqual(code, 1, result)
            self.assertIn("directory must not be a symlink", result["message"])
            self.assertEqual(_fingerprint(target), before)

    def test_scratch_inside_repository_is_refused(self):
        with tempfile.TemporaryDirectory() as td:
            root, target, scratch, _ = _case(Path(td), retain_target=True)
            before = _fingerprint(target)
            inside = root / "scratch-inside-repository"
            shutil.copytree(scratch, inside)
            result, code = ap.publish_package(
                inside, root, "team-invitations", **APPROVAL
            )
            self.assertEqual(code, 1, result)
            self.assertIn("outside the repository root", result["message"])
            self.assertEqual(_fingerprint(target), before)


if __name__ == "__main__":
    unittest.main()
