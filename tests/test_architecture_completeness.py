"""Adversarial completeness tests for plan-owned architecture obligations."""

import copy
import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from tests.test_architecture_lint import _make_repo, _save


def _refresh_source(manifest: dict, root: Path, suffix: str) -> None:
    path = next(row["path"] for row in manifest["sources"] if row["path"].endswith(suffix))
    digest = hashlib.sha256((root / path).read_bytes()).hexdigest()
    for row in manifest["sources"]:
        if row["path"] == path:
            row["sha256"] = digest


def _set_architecture_revision(package: Path, manifest: dict, revision: int) -> None:
    manifest["architecture_revision"] = revision
    overview = package / "solution-architecture.md"
    text = overview.read_text(encoding="utf-8")
    lines = text.splitlines()
    matches = [index for index, line in enumerate(lines) if line.startswith("> Architecture revision: ")]
    if len(matches) != 1:
        raise AssertionError("fixture must contain exactly one architecture revision banner")
    lines[matches[0]] = f"> Architecture revision: {revision}"
    overview.write_text("\n".join(lines) + "\n", encoding="utf-8")


class ArchitectureCompleteness(unittest.TestCase):
    def test_complete_data_cannot_drop_a_plan_durable_noun(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            arch_dir, manifest = _make_repo(root)
            manifest["data_entities"] = [manifest["data_entities"][0]]
            manifest["integration_flows"][0]["data_entity_ids"] = ["DATA-001"]
            manifest["feature_mappings"][1]["data_ids"] = ["DATA-001"]
            hard, _ = self._check(arch_dir, root, manifest)
            self.assertTrue(
                any("plan durable noun(s) are missing: invitation" in item for item in hard),
                hard,
            )

    def test_complete_security_and_integrations_cannot_drop_plan_ids(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            arch_dir, manifest = _make_repo(root)
            manifest["integration_flows"][0]["contract_refs"] = []
            hard, _ = self._check(arch_dir, root, manifest)
            self.assertTrue(any("plan TZ obligation(s) are missing: TZ-001" in item for item in hard), hard)
            self.assertTrue(any("plan IC obligation(s) are missing: IC-001" in item for item in hard), hard)

    def test_gap_reason_must_name_each_omitted_plan_obligation(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            arch_dir, manifest = _make_repo(root)
            manifest["status"] = "approved-with-gaps"
            manifest["approval"]["decision"] = "approved-with-gaps"
            manifest["integration_flows"][0]["contract_refs"] = []
            manifest["coverage"]["security"] = {
                "status": "gap", "material": False, "reason": "obligation evidence missing"
            }
            manifest["coverage"]["integrations"] = {
                "status": "gap", "material": False, "reason": "contract evidence missing"
            }
            hard, _ = self._check(arch_dir, root, manifest)
            self.assertTrue(any("must name each omitted TZ obligation" in item for item in hard), hard)
            self.assertTrue(any("must name each omitted IC obligation" in item for item in hard), hard)

            manifest["coverage"]["security"]["reason"] = "TZ-001 is not projected"
            manifest["coverage"]["integrations"]["reason"] = "IC-001 is not projected"
            hard, _ = self._check(arch_dir, root, manifest)
            self.assertFalse(any("omitted TZ obligation" in item for item in hard), hard)
            self.assertFalse(any("omitted IC obligation" in item for item in hard), hard)

    def test_scoped_closure_parser_ignores_durable_noun_in_notes(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            arch_dir, manifest = _make_repo(root)
            plan_path = root / "docs/plans/team-invitations/feature-plan.md"
            text = plan_path.read_text(encoding="utf-8")
            invitation = (
                "| invitation | personal | owned-by:02-team-invitations | "
                "owned-by:02-team-invitations | owned-by:02-team-invitations |\n"
            )
            text = text.replace(invitation, "")
            text += (
                "\n## Notes\n| Noun | Data-class | retain | export | erase |\n"
                "|---|---|---|---|---|\n" + invitation
            )
            plan_path.write_text(text, encoding="utf-8")
            _refresh_source(manifest, root, "feature-plan.md")
            hard, _ = self._check(arch_dir, root, manifest)
            self.assertTrue(
                any("noun 'invitation' does not resolve to a plan data row" in item for item in hard),
                hard,
            )

    def test_data_values_cannot_move_between_plan_owned_columns(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            arch_dir, manifest = _make_repo(root)
            entity = manifest["data_entities"][0]
            entity["data_class"] = "owned-by:01-roles-authz-foundation"
            entity["lifecycle"]["retain"] = "personal"
            hard, _ = self._check(arch_dir, root, manifest)
            self.assertTrue(any("plan column 'data-class' value 'personal'" in item for item in hard), hard)
            self.assertTrue(any("plan column 'retain'" in item for item in hard), hard)

    def test_scratch_revision_must_advance_readable_prior(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            current, manifest = _make_repo(root)
            scratch = root / "scratch"
            shutil.copytree(current, scratch)
            proposed = copy.deepcopy(manifest)
            proposed["status"] = "proposed"
            proposed["approval"]["decision"] = "pending"
            proposed["approval"]["recorded_by"] = "pending"
            _set_architecture_revision(scratch, proposed, 2)
            _save(scratch, proposed)
            hard, _ = self._check(scratch, root, proposed, allow_proposed=True)
            self.assertEqual(hard, [])
            _set_architecture_revision(scratch, proposed, 3)
            _save(scratch, proposed)
            hard, _ = self._check(scratch, root, proposed, allow_proposed=True)
            self.assertTrue(any("must be 2" in item for item in hard), hard)

    def test_malformed_prior_requires_durable_human_reset(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            current, manifest = _make_repo(root)
            scratch = root / "scratch"
            shutil.copytree(current, scratch)
            (current / "architecture.json").write_text("{broken", encoding="utf-8")
            proposed = copy.deepcopy(manifest)
            proposed["status"] = "proposed"
            proposed["approval"]["decision"] = "pending"
            proposed["approval"]["recorded_by"] = "pending"
            _save(scratch, proposed)
            hard, _ = self._check(scratch, root, proposed, allow_proposed=True)
            self.assertTrue(any("revision_reset" in item for item in hard), hard)
            proposed["revision_reset"] = {
                "reason": "The architecture owner approved reset of the unreadable prior package.",
                "recorded_by": "human",
                "gate": "Invalid Architecture Package Recovery",
            }
            _save(scratch, proposed)
            hard, _ = self._check(scratch, root, proposed, allow_proposed=True)
            self.assertEqual(hard, [])

    @staticmethod
    def _check(arch_dir: Path, root: Path, manifest: dict, **kwargs):
        # Import lazily so this module follows the same canonical linter loaded
        # by the base fixture tests.
        from tests.test_architecture_lint import al

        kwargs["allow_legacy_v1"] = True
        return al.check_package(arch_dir, root, manifest, **kwargs)


if __name__ == "__main__":
    unittest.main()
