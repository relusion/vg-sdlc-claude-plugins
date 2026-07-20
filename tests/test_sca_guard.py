"""Tests for sca-guard.py — the OSV-backed known-vulnerability floor of /core-engineering:ce-probe-deps."""

import http.server
import json
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "plugins/core-engineering/skills/ce-probe-deps/scripts/sca-guard.py"
FIXTURE = REPO / "evals/fixtures/vulnerable-deps"


def run_guard(*args):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        timeout=60,
    )


class CannedOSV(http.server.BaseHTTPRequestHandler):
    """Answers every querybatch with the canned per-query vuln lists."""

    canned: list[list[str]] = []

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        queries = json.loads(self.rfile.read(length))["queries"]
        results = []
        for i, _ in enumerate(queries):
            ids = self.canned[i] if i < len(self.canned) else []
            results.append({"vulns": [{"id": vid} for vid in ids]} if ids else {})
        body = json.dumps({"results": results}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def local_osv(canned):
    CannedOSV.canned = canned
    server = http.server.HTTPServer(("127.0.0.1", 0), CannedOSV)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, f"http://127.0.0.1:{server.server_port}/v1/querybatch"


class ScaGuard(unittest.TestCase):
    def test_offline_degrades_loudly_never_passes(self):
        res = run_guard("--repo", str(FIXTURE), "--offline")
        self.assertEqual(res.returncode, 2)
        self.assertIn("DEGRADED", res.stderr)
        self.assertIn("not a pass", res.stderr)

    def test_network_failure_degrades_loudly(self):
        res = run_guard("--repo", str(FIXTURE),
                        "--osv-url", "http://127.0.0.1:9/unreachable", "--timeout", "2")
        self.assertEqual(res.returncode, 2)
        self.assertIn("DEGRADED", res.stderr)

    def test_vulnerable_pin_is_found_with_advisory_ids(self):
        server, url = local_osv([["PYSEC-2019-133", "GHSA-mh33-7rrq-662w"]])
        try:
            res = run_guard("--repo", str(FIXTURE), "--osv-url", url, "--json")
        finally:
            server.shutdown()
            server.server_close()
        self.assertEqual(res.returncode, 1, res.stderr)
        data = json.loads(res.stdout)
        self.assertEqual(data["status"], "fail")
        finding = data["findings"][0]
        self.assertEqual(finding["name"], "urllib3")
        self.assertEqual(finding["version"], "1.24.1")
        self.assertIn("PYSEC-2019-133", finding["vulns"])
        # the unpinned range must be listed as skipped, never silently dropped
        self.assertTrue(any("requests" in s for s in data["skipped_unpinned"]))
        # hard_failures carries the human-evidence line a merge-runner renders,
        # so the advisory id + package show through instead of "FAIL (no detail)".
        self.assertTrue(data["hard_failures"], "expected human-evidence lines")
        self.assertTrue(any("PYSEC-2019-133" in h and "urllib3" in h
                            for h in data["hard_failures"]), data["hard_failures"])

    def test_clean_scan_exits_zero(self):
        server, url = local_osv([[]])
        try:
            res = run_guard("--repo", str(FIXTURE), "--osv-url", url, "--json")
        finally:
            server.shutdown()
            server.server_close()
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(json.loads(res.stdout)["status"], "pass")

    def test_no_manifests_is_a_clean_noop(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "main.go").write_text("package main\n", encoding="utf-8")
            res = run_guard("--repo", tmp)
            self.assertEqual(res.returncode, 0)
            self.assertIn("no exactly-pinned dependencies", res.stdout)

    def test_package_json_ranges_are_skipped_and_pins_scanned(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "package.json").write_text(json.dumps({
                "dependencies": {"left-pad": "1.3.0", "lodash": "^4.17.0"}
            }), encoding="utf-8")
            server, url = local_osv([[]])
            try:
                res = run_guard("--repo", tmp, "--osv-url", url, "--json")
            finally:
                server.shutdown()
                server.server_close()
            data = json.loads(res.stdout)
            self.assertEqual(data["packages_scanned"], 1)
            self.assertTrue(any("lodash" in s for s in data["skipped_unpinned"]))

    def test_active_disposition_accepts_vulnerable_pin(self):
        # Additive ledger wiring: a consciously-accepted advisory moves to `accepted`
        # (shown, counted) instead of failing the gate — the anti-"cries wolf" mechanism.
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "requirements.txt").write_text("urllib3==1.24.1\n", encoding="utf-8")
            ledger = Path(tmp) / ".merge-bar"
            ledger.mkdir()
            (ledger / "dispositions.json").write_text(json.dumps({
                "schema_version": 1,
                "dispositions": [{
                    "id": "DEP-1", "gate": "sca-guard",
                    "match": {"package": "PyPI:urllib3", "version": "1.24.1"},
                    "reason": "not reachable from any entrypoint; tracked in JIRA-42",
                    "accepted_by": "t", "date": "2026-07-09", "expires": "2999-01-01"}],
            }), encoding="utf-8")
            server, url = local_osv([["PYSEC-2019-133"]])
            try:
                res = run_guard("--repo", tmp, "--osv-url", url, "--today", "2026-07-10", "--json")
            finally:
                server.shutdown()
                server.server_close()
            self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
            data = json.loads(res.stdout)
            self.assertEqual(data["findings"], [])
            self.assertEqual(len(data["accepted"]), 1)
            self.assertEqual(data["accepted"][0]["disposition_id"], "DEP-1")


if __name__ == "__main__":
    unittest.main()
