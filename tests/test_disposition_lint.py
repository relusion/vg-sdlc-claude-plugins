"""Tests for disposition-lint.py and the shared merge_disposition.py reader.

disposition-lint validates .merge-bar/dispositions.json — the accepted-risk register the
advisory gates read. It runs both as a human CLI and as an advisory merge-bar gate, so its
exit contract (0 valid/absent · 1 errors · 2 could-not-run) is asserted at the subprocess
level; merge_disposition's pure functions are unit-tested by import.
"""

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "plugins/core-engineering/skills/ce-probe-infra/scripts/disposition-lint.py"
LIB = REPO / "plugins/core-engineering/skills/ce-probe-infra/scripts/merge_disposition.py"

_spec = importlib.util.spec_from_file_location("merge_disposition", LIB)
md = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(md)


def write_ledger(repo, *entries):
    d = Path(repo) / ".merge-bar"
    d.mkdir(parents=True, exist_ok=True)
    (d / "dispositions.json").write_text(
        json.dumps({"schema_version": 1, "dispositions": list(entries)}))


def run_lint(repo, *extra):
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--repo", str(repo), "--json", *extra],
        capture_output=True, text=True, timeout=60)


VALID = {"id": "SEC-1", "gate": "secrets-guard",
         "match": {"file": "x.env", "type": "assignment to `token`"},
         "reason": "test fixture", "accepted_by": "t",
         "date": "2026-07-09", "expires": "2999-01-01"}


class DispositionLintCLI(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_absent_ledger_passes(self):
        r = run_lint(self.tmp)
        self.assertEqual(r.returncode, 0, r.stderr)
        data = json.loads(r.stdout)
        self.assertFalse(data["ledger_present"])
        self.assertEqual(data["status"], "pass")

    def test_valid_ledger_passes(self):
        write_ledger(self.tmp, VALID)
        r = run_lint(self.tmp, "--today", "2026-07-10")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(json.loads(r.stdout)["dispositions"], 1)

    def test_expired_fails(self):
        write_ledger(self.tmp, {**VALID, "expires": "2026-07-09"})
        r = run_lint(self.tmp, "--today", "2026-08-01")
        self.assertEqual(r.returncode, 1)
        self.assertIn("expired", r.stdout)

    def test_missing_accepted_by_fails(self):
        e = dict(VALID)
        del e["accepted_by"]
        write_ledger(self.tmp, e)
        r = run_lint(self.tmp, "--today", "2026-07-10")
        self.assertEqual(r.returncode, 1)
        self.assertIn("accepted_by", r.stdout)

    def test_missing_reason_fails(self):
        e = dict(VALID)
        del e["reason"]
        write_ledger(self.tmp, e)
        r = run_lint(self.tmp, "--today", "2026-07-10")
        self.assertEqual(r.returncode, 1)
        self.assertIn("reason", r.stdout)

    def test_duplicate_id_fails(self):
        write_ledger(self.tmp, VALID, dict(VALID))
        r = run_lint(self.tmp, "--today", "2026-07-10")
        self.assertEqual(r.returncode, 1)
        self.assertIn("duplicate", r.stdout)

    def test_unknown_gate_fails(self):
        write_ledger(self.tmp, {**VALID, "gate": "not-a-gate"})
        r = run_lint(self.tmp, "--today", "2026-07-10")
        self.assertEqual(r.returncode, 1)
        self.assertIn("gate", r.stdout)

    def test_bad_sca_match_fails(self):
        write_ledger(self.tmp, {**VALID, "gate": "sca-guard", "match": {"package": "novalue"}})
        r = run_lint(self.tmp, "--today", "2026-07-10")
        self.assertEqual(r.returncode, 1)
        self.assertIn("package", r.stdout)

    def test_malformed_json_fails(self):
        d = Path(self.tmp) / ".merge-bar"
        d.mkdir(parents=True)
        (d / "dispositions.json").write_text("{ not json")
        r = run_lint(self.tmp)
        self.assertEqual(r.returncode, 1)
        self.assertIn("JSON", r.stdout)

    def test_bad_repo_is_exit_2(self):
        r = run_lint("/nonexistent/xyz")
        self.assertEqual(r.returncode, 2)

    def test_non_utf8_ledger_degrades_not_crash(self):
        # A non-UTF-8 ledger must surface as a clean error (exit 1), never a raw traceback.
        d = Path(self.tmp) / ".merge-bar"
        d.mkdir(parents=True)
        (d / "dispositions.json").write_bytes(b"\xe9\xff not utf8")
        r = run_lint(self.tmp)
        self.assertEqual(r.returncode, 1)
        self.assertNotIn("Traceback", r.stderr)


class MergeDispositionLib(unittest.TestCase):
    TODAY = date(2026, 7, 10)

    def test_parse_absent_is_clean(self):
        entries, err = md.parse_ledger("")
        self.assertEqual(entries, [])
        self.assertIsNone(err)

    def test_is_active_is_public_and_splits_on_expiry(self):
        """evidence-pack.py needs the active/expired split WITHOUT validate(),
        which correctly reports an expired `expires` as an error — right for the
        lint, wrong for a report that must still render the lapsed entry."""
        live = {"expires": "2999-01-01"}
        lapsed = {"expires": "2026-07-09"}          # yesterday, relative to TODAY
        boundary = {"expires": "2026-07-10"}        # expires today ⇒ still active
        self.assertTrue(md.is_active(live, self.TODAY))
        self.assertFalse(md.is_active(lapsed, self.TODAY))
        self.assertTrue(md.is_active(boundary, self.TODAY))

    def test_is_active_false_on_unparseable_or_missing_expiry(self):
        self.assertFalse(md.is_active({"expires": "soon"}, self.TODAY))
        self.assertFalse(md.is_active({}, self.TODAY))

    def test_partition_active_suppresses(self):
        findings = [{"file": "a.py", "type": "AWS access key id"}]
        entries = [{"id": "D1", "gate": "secrets-guard",
                    "match": {"file": "a.py"}, "reason": "r", "accepted_by": "t",
                    "date": "2026-07-01", "expires": "2999-01-01"}]
        unaccepted, accepted = md.partition(findings, entries, "secrets-guard", self.TODAY)
        self.assertEqual(unaccepted, [])
        self.assertEqual(accepted[0]["disposition_id"], "D1")

    def test_partition_wrong_gate_does_not_suppress(self):
        findings = [{"ecosystem": "PyPI", "name": "urllib3", "version": "1.24.1", "vulns": ["X"]}]
        # a secrets-guard disposition must never suppress a sca-guard finding
        entries = [{"id": "D1", "gate": "secrets-guard", "match": {"file": "x"},
                    "reason": "r", "accepted_by": "t",
                    "date": "2026-07-01", "expires": "2999-01-01"}]
        unaccepted, accepted = md.partition(findings, entries, "sca-guard", self.TODAY)
        self.assertEqual(len(unaccepted), 1)
        self.assertEqual(accepted, [])

    def test_partition_sca_package_and_version(self):
        findings = [{"ecosystem": "PyPI", "name": "urllib3", "version": "1.24.1", "vulns": ["CVE-1"]}]
        entries = [{"id": "D1", "gate": "sca-guard",
                    "match": {"package": "PyPI:urllib3", "version": "1.24.1", "advisory": "CVE-1"},
                    "reason": "r", "accepted_by": "t",
                    "date": "2026-07-01", "expires": "2999-01-01"}]
        unaccepted, accepted = md.partition(findings, entries, "sca-guard", self.TODAY)
        self.assertEqual(unaccepted, [])
        self.assertEqual(len(accepted), 1)

    def test_expired_never_suppresses(self):
        findings = [{"file": "a.py", "type": "T"}]
        entries = [{"id": "D1", "gate": "secrets-guard", "match": {"file": "a.py"},
                    "reason": "r", "accepted_by": "t",
                    "date": "2026-07-01", "expires": "2026-07-09"}]
        unaccepted, _ = md.partition(findings, entries, "secrets-guard", self.TODAY)
        self.assertEqual(len(unaccepted), 1)

    def test_validate_flags_all_defects(self):
        errors = md.validate([{"id": "", "gate": "x", "match": {}}], self.TODAY)
        self.assertTrue(any("id" in e for e in errors))
        self.assertTrue(any("gate" in e for e in errors))


if __name__ == "__main__":
    unittest.main()
