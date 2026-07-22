"""Pre-prompt coverage for architecture-options-lint.py."""

import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
SCRIPT = (
    REPO
    / "plugins/core-engineering/skills/ce-architecture/scripts/architecture-options-lint.py"
)
SELECTION_TEST = REPO / "tests/test_architecture_selection_lint.py"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ol = _load("architecture_options_lint_mod", SCRIPT)
fixtures = _load("architecture_selection_fixture_helpers", SELECTION_TEST)


def _decision_ready_report(data: dict) -> str:
    rendered = fixtures.render_options_report(data)
    start = rendered.index("## What Needs Your Decision")
    end = rendered.index("## Evaluation Frame")
    recommendation = data["recommendation"]
    selected = next(
        row for row in data["options"] if row["option_id"] == recommendation["option_id"]
    )
    triage = "\n".join(
        [
            "## What Needs Your Decision",
            "",
            "- **Decision:** Choose the whole-solution direction that will bind decomposition.",
            "- **Why now:** Runtime boundaries and data ownership change the feature cut.",
            f"- **Recommendation:** {selected['option_id']} — {selected['title']}",
            f"- **Recommendation basis:** {recommendation['basis']}",
            "- **Confidence / sensitivity:** high / stable",
            "- **Cost if wrong:** Rework boundaries, migration, and operational ownership.",
            "- **Material gaps and inferences:** None — all score evidence is recorded.",
            "",
        ]
    )
    return rendered[:start] + triage + rendered[end:]


def _write_valid_report(root: Path) -> tuple[Path, dict]:
    _, data = fixtures.build_artifact(root)
    report = root / "docs/plans/.drafts/smoke/architecture-options.md"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(_decision_ready_report(data), encoding="utf-8")
    frame = data["evaluation_frame"]
    exploration = {
        "schema_version": 1,
        "project_slug": data["project_slug"],
        "capability_revision": data["source_capability_revision"],
        "exploration_attempt": data["source_exploration_attempt"],
        "parent_gate_index": 2,
        "parent_gate_total": 8,
        "project_intent": frame["project_intent"],
        "non_goals": frame["non_goals"],
        "architecture_applicability": frame["architecture_applicability"],
        "driver_screen": frame["driver_screen"],
        "accepted_decisions": frame["accepted_decisions"],
        "material_gaps": frame["material_gaps"],
        "capabilities": frame["capabilities"],
        "journeys": frame["journeys"],
        "hard_constraints": data["hard_constraints"],
        "quality_attribute_scenarios": frame["quality_attribute_scenarios"],
        "criteria": data["criteria"],
        "sources": data["sources"],
    }
    report.with_name("architecture-exploration.json").write_text(
        json.dumps(exploration, indent=2) + "\n", encoding="utf-8"
    )
    return report, data


def _mutate_projection(report: Path, mutate) -> None:
    text = report.read_text(encoding="utf-8")
    match = ol.PROJECTION_PATTERN.search(text)
    projection = json.loads(match.group(1))
    mutate(projection)
    replacement = json.dumps(projection, ensure_ascii=False, indent=2, sort_keys=True)
    report.write_text(
        text[: match.start(1)] + replacement + text[match.end(1) :],
        encoding="utf-8",
    )


class ArchitectureOptionsLintContract(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.report, self.data = _write_valid_report(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_valid_report_passes_without_approval_state(self):
        projection, failures = ol.validate_file(self.report, repo_root=self.root)
        self.assertEqual([], failures)
        self.assertNotIn("selection", projection)
        self.assertNotIn("decided_by", projection)

    def test_cli_json_contract_and_exit_codes(self):
        passed = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                str(self.report),
                "--repo-root",
                str(self.root),
                "--json",
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(0, passed.returncode, passed.stderr)
        self.assertEqual("pass", json.loads(passed.stdout)["status"])

        self.report.write_text("# incomplete\n", encoding="utf-8")
        failed = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                str(self.report),
                "--repo-root",
                str(self.root),
                "--json",
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(1, failed.returncode)
        self.assertEqual("fail", json.loads(failed.stdout)["status"])

        errored = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                str(self.report.with_name("missing.md")),
                "--repo-root",
                str(self.root),
                "--json",
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(2, errored.returncode)
        self.assertEqual("error", json.loads(errored.stdout)["status"])

    def test_missing_decision_triage_field_fails(self):
        text = self.report.read_text(encoding="utf-8")
        text = text.replace(
            "- **Cost if wrong:** Rework boundaries, migration, and operational ownership.\n",
            "",
        )
        self.report.write_text(text, encoding="utf-8")
        _, failures = ol.validate_file(self.report, repo_root=self.root)
        self.assertTrue(any("'Cost if wrong'" in failure for failure in failures))

    def test_gate_locator_must_match_current_exploration_input(self):
        text = self.report.read_text(encoding="utf-8").replace(
            "`Gate 2 of 8 — Architecture Direction Selection`",
            "`Gate 3 of 8 — Architecture Direction Selection`",
            1,
        )
        self.report.write_text(text, encoding="utf-8")
        _, failures = ol.validate_file(self.report, repo_root=self.root)
        self.assertTrue(any("Gate locator must match" in item for item in failures))

    def test_hidden_report_container_fails(self):
        text = self.report.read_text(encoding="utf-8")
        text = text.replace(
            "## Machine-Readable Comparison Projection",
            "<select>\n## Machine-Readable Comparison Projection",
        )
        self.report.write_text(text, encoding="utf-8")
        _, failures = ol.validate_file(self.report, repo_root=self.root)
        self.assertTrue(any("hide decision content" in failure for failure in failures))

    def test_empty_human_comparison_section_cannot_be_backfilled_by_projection(self):
        text = self.report.read_text(encoding="utf-8")
        text, count = re.subn(
            r"(^## Weighted Comparison\s*$\n).*?(?=^##\s|\Z)",
            r"\1\n",
            text,
            count=1,
            flags=re.MULTILINE | re.DOTALL,
        )
        self.assertEqual(count, 1)
        self.report.write_text(text, encoding="utf-8")
        _, failures = ol.validate_file(self.report, repo_root=self.root)
        self.assertTrue(
            any("## Weighted Comparison" in item and "must not be empty" in item for item in failures),
            failures,
        )

    def test_stale_and_invalid_source_hashes_fail(self):
        source = self.root / "docs/briefs/smoke.md"
        source.write_text("# changed\n", encoding="utf-8")
        _, stale = ol.validate_file(self.report, repo_root=self.root)
        self.assertTrue(any("sha256 is stale" in failure for failure in stale))

        self.report, self.data = _write_valid_report(self.root)
        _mutate_projection(
            self.report,
            lambda projection: projection["sources"][0].__setitem__("sha256", "bad"),
        )
        _, invalid = ol.validate_file(self.report, repo_root=self.root)
        self.assertTrue(any("64 lowercase hex" in failure for failure in invalid))

    def test_stale_self_consistent_report_from_another_attempt_fails(self):
        exploration_path = self.report.with_name("architecture-exploration.json")
        exploration = json.loads(exploration_path.read_text(encoding="utf-8"))
        exploration["exploration_attempt"] = 2
        exploration_path.write_text(
            json.dumps(exploration, indent=2) + "\n", encoding="utf-8"
        )
        _, failures = ol.validate_file(self.report, repo_root=self.root)
        self.assertTrue(
            any("does not match current architecture-exploration.json" in row for row in failures)
        )

    def test_unsafe_exploration_input_is_an_error(self):
        exploration_path = self.report.with_name("architecture-exploration.json")
        real_input = exploration_path.with_name("real-exploration.json")
        exploration_path.rename(real_input)
        exploration_path.symlink_to(real_input.name)
        with self.assertRaises(ol.OptionsLintError):
            ol.validate_file(self.report, repo_root=self.root)

    def test_option_hash_and_option_set_hash_tampering_fail(self):
        _mutate_projection(
            self.report,
            lambda projection: projection["options"][0].__setitem__(
                "option_sha256", "0" * 64
            ),
        )
        _, option_failures = ol.validate_file(self.report, repo_root=self.root)
        self.assertTrue(any("option_sha256 mismatch" in failure for failure in option_failures))

        self.report, self.data = _write_valid_report(self.root)
        _mutate_projection(
            self.report,
            lambda projection: projection.__setitem__("option_set_sha256", "0" * 64),
        )
        _, set_failures = ol.validate_file(self.report, repo_root=self.root)
        self.assertTrue(any("option_set_sha256 mismatch" in failure for failure in set_failures))

    def test_integrity_row_tampering_fails(self):
        text = self.report.read_text(encoding="utf-8")
        text = text.replace(
            f"| Option-set SHA-256 | `{self.data['option_set_sha256']}` |",
            "| Option-set SHA-256 | `tampered` |",
        )
        self.report.write_text(text, encoding="utf-8")
        _, failures = ol.validate_file(self.report, repo_root=self.root)
        self.assertTrue(any("integrity row 'Option-set SHA-256'" in failure for failure in failures))

    def test_missing_projection_key_fails(self):
        _mutate_projection(
            self.report, lambda projection: projection.pop("hard_constraints")
        )
        _, failures = ol.validate_file(self.report, repo_root=self.root)
        self.assertTrue(any("projection missing key" in failure for failure in failures))

    def test_symlink_and_hardlink_reports_are_errors(self):
        original = self.report.with_name("real-options.md")
        self.report.rename(original)
        self.report.symlink_to(original.name)
        with self.assertRaises(ol.OptionsLintError):
            ol.validate_file(self.report, repo_root=self.root)

        self.report.unlink()
        original.rename(self.report)
        alias = self.report.with_name("hardlink-copy.md")
        os.link(self.report, alias)
        with self.assertRaises(ol.OptionsLintError):
            ol.validate_file(self.report, repo_root=self.root)

    def test_invalid_utf8_is_an_error(self):
        self.report.write_bytes(b"\xff\xfe")
        with self.assertRaises(ol.OptionsLintError):
            ol.validate_file(self.report, repo_root=self.root)

    def test_non_draft_or_outside_path_is_an_error(self):
        final_report = self.root / "docs/plans/smoke/architecture-options.md"
        final_report.parent.mkdir(parents=True, exist_ok=True)
        final_report.write_bytes(self.report.read_bytes())
        with self.assertRaises(ol.OptionsLintError):
            ol.validate_file(final_report, repo_root=self.root)

        outside = Path(self.tmp.name).parent / "architecture-options.md"
        try:
            outside.write_bytes(self.report.read_bytes())
            with self.assertRaises(ol.OptionsLintError):
                ol.validate_file(outside, repo_root=self.root)
        finally:
            outside.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
