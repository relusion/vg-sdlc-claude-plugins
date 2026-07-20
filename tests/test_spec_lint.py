"""Tests for skills/ce-spec/scripts/spec-lint.py — the H5 fail-open contract.

The regression that matters most: H5 (security-criteria coverage) is deliberately
miss-safe, so a threat-model.md that exists but yields no ids for the feature used
to silently become H5-N/A — a formatting slip could switch the one security gate
off with no signal anywhere (the silent-disarm class WS6-T1 closes). This suite
pins the three-state `h5_status` contract:

  ran      — threat-ids resolved, H5 executed (and can hard-FAIL on a miss);
  na       — no threat-model file and no --threat-ids/--threat-model flag;
  disarmed — H5 was armed but could not run (present-but-unmatching threat-model,
             parse failure, empty --threat-ids, missing explicit --threat-model);
             exit-safe, but LOUD via an advisory naming the feature id.

It also pins the patch-lint import compat: `run_checks(spec, tasks)` with no
threat_ids keyword keeps working (patch-lint calls exactly that).
"""

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "plugins/core-engineering/skills/ce-spec/scripts/spec-lint.py"

_spec = importlib.util.spec_from_file_location("spec_lint_mod", SCRIPT)
sl = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sl)

# Minimal spec that passes H1–H4: one AC (security-marked), one TC proving it,
# one task verifying the TC.
SPEC_MD = """# Spec

## AC-1 rejects bad input [SECURITY: TZ-001]

## TC-1 (proves AC-1)
modality: cli
verification: auto
"""

TASKS_JSON = {"feature_id": "feat-1", "tasks": [{"id": "T-1", "verifies": ["TC-1"]}]}

THREAT_MODEL_MATCHING = """security_obligations:
  - feature: feat-1
    threat_ids: [TZ-001]
"""

THREAT_MODEL_UNMATCHING = """security_obligations:
  - feature: some-other-feature
    threat_ids: [TZ-001]
"""

# The feature block exists but its threat_ids list is garbled — the parse-failure
# flavor of the disarm class (read_feature_threat_ids returns a falsy result).
THREAT_MODEL_GARBLED = """security_obligations:
  - feature: feat-1
    notes: threat ids got reformatted away by an edit
"""


def write_plan(root: Path, threat_model: str | None) -> Path:
    """Lay out docs/plans/demo/specs/feat-1 so H5's ../../threat-model.md
    auto-discovery path is exercised exactly as shipped."""
    spec_dir = root / "docs/plans/demo/specs/feat-1"
    spec_dir.mkdir(parents=True)
    (spec_dir / "ce-spec.md").write_text(SPEC_MD, encoding="utf-8")
    (spec_dir / "tasks.json").write_text(json.dumps(TASKS_JSON), encoding="utf-8")
    if threat_model is not None:
        (root / "docs/plans/demo/threat-model.md").write_text(
            threat_model, encoding="utf-8")
    return spec_dir


def run_lint(*argv: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *argv],
        capture_output=True, text=True, timeout=30,
    )


def run_lint_json(*argv: str) -> tuple[dict, int]:
    proc = run_lint(*argv, "--json")
    return json.loads(proc.stdout), proc.returncode


DISARM_NEEDLE = "matched no security_obligations entry"


class H5StatusRan(unittest.TestCase):
    def test_auto_build_fixture_declares_every_feature_obligation(self):
        threat_model = (
            REPO
            / "evals/fixtures/auto-build-three-feature/docs/plans/snippet-vault/threat-model.md"
        )
        expected = {
            "01-create-snippet": {"TZ-001"},
            "02-share-snippet": {"TZ-002"},
            "03-export-snippets": {"TZ-003"},
        }
        for feature, threat_ids in expected.items():
            self.assertEqual(sl.read_feature_threat_ids(threat_model, feature), threat_ids)

    def test_matching_threat_model_reports_ran_and_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            spec_dir = write_plan(Path(tmp), THREAT_MODEL_MATCHING)
            payload, rc = run_lint_json(str(spec_dir))
        self.assertEqual(rc, 0)
        self.assertEqual(payload["status"], "pass")
        self.assertEqual(payload["h5_status"], "ran")
        self.assertEqual(payload["threat_ids"], ["TZ-001"])
        self.assertEqual(payload["advisory"], [])

    def test_ran_still_hard_fails_on_uncovered_threat(self):
        tm = "security_obligations:\n  - feature: feat-1\n    threat_ids: [TZ-001, TZ-002]\n"
        with tempfile.TemporaryDirectory() as tmp:
            spec_dir = write_plan(Path(tmp), tm)
            payload, rc = run_lint_json(str(spec_dir))
        self.assertEqual(rc, 1)
        self.assertEqual(payload["status"], "fail")
        self.assertEqual(payload["h5_status"], "ran")
        self.assertTrue(any(f.startswith("H5 TZ-002") for f in payload["hard_failures"]))

    def test_explicit_threat_ids_report_ran_without_any_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            spec_dir = write_plan(Path(tmp), None)
            payload, rc = run_lint_json(str(spec_dir), "--threat-ids", "TZ-001")
        self.assertEqual(rc, 0)
        self.assertEqual(payload["h5_status"], "ran")

    def test_human_pass_line_names_h1_h5(self):
        with tempfile.TemporaryDirectory() as tmp:
            spec_dir = write_plan(Path(tmp), THREAT_MODEL_MATCHING)
            proc = run_lint(str(spec_dir))
        self.assertEqual(proc.returncode, 0)
        self.assertIn("(H1-H5) hold (H5 ran)", proc.stdout)


class H5StatusNa(unittest.TestCase):
    def test_no_threat_model_and_no_flags_reports_na(self):
        with tempfile.TemporaryDirectory() as tmp:
            spec_dir = write_plan(Path(tmp), None)
            payload, rc = run_lint_json(str(spec_dir))
        self.assertEqual(rc, 0)
        self.assertEqual(payload["h5_status"], "na")
        self.assertEqual(payload["advisory"], [])  # na is a genuine skip — never loud

    def test_human_pass_line_names_h5_na(self):
        with tempfile.TemporaryDirectory() as tmp:
            spec_dir = write_plan(Path(tmp), None)
            proc = run_lint(str(spec_dir))
        self.assertIn("(H1-H4) hold (H5 n/a)", proc.stdout)


class H5StatusDisarmed(unittest.TestCase):
    def test_present_but_unmatching_threat_model_disarms_loudly(self):
        with tempfile.TemporaryDirectory() as tmp:
            spec_dir = write_plan(Path(tmp), THREAT_MODEL_UNMATCHING)
            payload, rc = run_lint_json(str(spec_dir))
        self.assertEqual(rc, 0)  # disarm never manufactures a FAIL
        self.assertEqual(payload["h5_status"], "disarmed")
        advisories = [a for a in payload["advisory"] if DISARM_NEEDLE in a]
        self.assertEqual(len(advisories), 1)
        self.assertIn("feat-1", advisories[0])  # names the unmatched feature id
        self.assertIn("threat-model.md is present", advisories[0])

    def test_garbled_threat_ids_block_disarms(self):
        with tempfile.TemporaryDirectory() as tmp:
            spec_dir = write_plan(Path(tmp), THREAT_MODEL_GARBLED)
            payload, rc = run_lint_json(str(spec_dir))
        self.assertEqual(rc, 0)
        self.assertEqual(payload["h5_status"], "disarmed")
        self.assertTrue(any(DISARM_NEEDLE in a for a in payload["advisory"]))

    def test_missing_explicit_threat_model_disarms_not_na(self):
        with tempfile.TemporaryDirectory() as tmp:
            spec_dir = write_plan(Path(tmp), None)
            payload, rc = run_lint_json(
                str(spec_dir), "--threat-model", str(Path(tmp) / "nope.md"))
        self.assertEqual(rc, 0)
        self.assertEqual(payload["h5_status"], "disarmed")
        self.assertTrue(any("--threat-model was passed" in a for a in payload["advisory"]))

    def test_empty_threat_ids_flag_disarms_not_na(self):
        with tempfile.TemporaryDirectory() as tmp:
            spec_dir = write_plan(Path(tmp), None)
            payload, rc = run_lint_json(str(spec_dir), "--threat-ids", " , ")
        self.assertEqual(rc, 0)
        self.assertEqual(payload["h5_status"], "disarmed")
        self.assertTrue(any("--threat-ids was passed" in a for a in payload["advisory"]))

    def test_human_pass_line_names_h5_disarmed(self):
        with tempfile.TemporaryDirectory() as tmp:
            spec_dir = write_plan(Path(tmp), THREAT_MODEL_UNMATCHING)
            proc = run_lint(str(spec_dir))
        self.assertIn("(H1-H4) hold (H5 DISARMED)", proc.stdout)
        self.assertIn(DISARM_NEEDLE, proc.stdout)


class ResolveThreatIdsUnit(unittest.TestCase):
    """resolve_threat_ids returns (ids, h5_status) — pinned at the function level
    so a signature regression is caught without a subprocess."""

    class Args:
        threat_ids = None
        threat_model = None
        feature = None

    def test_returns_tuple_na(self):
        with tempfile.TemporaryDirectory() as tmp:
            spec_dir = write_plan(Path(tmp), None)
            ids, status = sl.resolve_threat_ids(
                self.Args(), spec_dir / "ce-spec.md", TASKS_JSON)
        self.assertIsNone(ids)
        self.assertEqual(status, "na")

    def test_returns_tuple_ran(self):
        with tempfile.TemporaryDirectory() as tmp:
            spec_dir = write_plan(Path(tmp), THREAT_MODEL_MATCHING)
            ids, status = sl.resolve_threat_ids(
                self.Args(), spec_dir / "ce-spec.md", TASKS_JSON)
        self.assertEqual(ids, {"TZ-001"})
        self.assertEqual(status, "ran")

    def test_returns_tuple_disarmed(self):
        with tempfile.TemporaryDirectory() as tmp:
            spec_dir = write_plan(Path(tmp), THREAT_MODEL_UNMATCHING)
            ids, status = sl.resolve_threat_ids(
                self.Args(), spec_dir / "ce-spec.md", TASKS_JSON)
        self.assertFalse(ids)
        self.assertEqual(status, "disarmed")


class PatchLintImportCompat(unittest.TestCase):
    def test_run_checks_signature_without_threat_ids_still_works(self):
        # patch-lint calls sl.run_checks(parsed, tasks) — exactly this shape.
        parsed = sl.parse_spec(SPEC_MD)
        hard, advisory = sl.run_checks(parsed, TASKS_JSON)
        self.assertEqual(hard, [])

    def test_fork_copy_is_byte_identical(self):
        copy = REPO / "plugins/core-engineering/skills/ce-auto-build/scripts/spec-lint.py"
        self.assertEqual(SCRIPT.read_bytes(), copy.read_bytes())


if __name__ == "__main__":
    unittest.main()
