"""Tests for scripts/enterprise_evidence.py, the optional evidence collector."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "enterprise_evidence.py"


def run(*args, env=None):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        timeout=30,
        env=env,
    )


def make_inventory(root: Path) -> None:
    release = root / "release"
    release.mkdir(parents=True)
    (release / "sbom.cdx.json").write_text('{"bomFormat":"CycloneDX"}\n', encoding="utf-8")
    (release / "provenance.intoto.jsonl").write_text("{}\n", encoding="utf-8")
    (release / "artifact.sig").write_text("sig\n", encoding="utf-8")
    (release / "checksums.txt").write_text("abc  artifact.tar.gz\n", encoding="utf-8")
    (release / "scorecard.json").write_text('{"score":8.1}\n', encoding="utf-8")
    (release / "osv.json").write_text('{"results":[]}\n', encoding="utf-8")


class EnterpriseEvidence(unittest.TestCase):
    def test_inventory_finds_local_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_inventory(root)
            res = run("--root", str(root), "--json")
            self.assertEqual(res.returncode, 0, res.stderr)
            doc = json.loads(res.stdout)

            self.assertEqual(doc["schema_version"], 1)
            self.assertEqual(doc["mode"], "inventory")
            self.assertIn("release/sbom.cdx.json", doc["evidence"]["sbom"])
            self.assertIn("release/provenance.intoto.jsonl", doc["evidence"]["provenance"])
            self.assertIn("release/artifact.sig", doc["evidence"]["signatures"])
            self.assertIn("release/checksums.txt", doc["evidence"]["checksums"])
            self.assertIn("release/scorecard.json", doc["evidence"]["scorecard"])
            self.assertIn("release/osv.json", doc["evidence"]["security_scans"])
            self.assertFalse(any(gap.startswith("no local sbom") for gap in doc["gaps"]))
            self.assertIn("syft dir:.", doc["recommended_commands"]["sbom"][1])

    def test_out_writes_json_without_stdout(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_inventory(root)
            out = root / "reports" / "evidence.json"
            res = run("--root", str(root), "--out", str(out))
            self.assertEqual(res.returncode, 0, res.stderr)
            self.assertEqual(res.stdout, "")
            doc = json.loads(out.read_text(encoding="utf-8"))
            self.assertIn("release/checksums.txt", doc["evidence"]["checksums"])

    def test_execute_runs_available_local_generators(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            root.mkdir()
            fakebin = Path(tmp) / "bin"
            fakebin.mkdir()
            syft = fakebin / "syft"
            syft.write_text("#!/bin/sh\nprintf '{\"bomFormat\":\"CycloneDX\"}\\n'\n", encoding="utf-8")
            syft.chmod(0o755)
            osv = fakebin / "osv-scanner"
            osv.write_text("#!/bin/sh\nprintf '{\"results\":[]}\\n'\n", encoding="utf-8")
            osv.chmod(0o755)
            env = os.environ.copy()
            env["PATH"] = f"{fakebin}:{env.get('PATH', '')}"
            out_dir = root / "evidence"

            res = run(
                "--root", str(root),
                "--execute",
                "--evidence-dir", str(out_dir),
                "--json",
                env=env,
            )
            self.assertEqual(res.returncode, 0, res.stderr)
            doc = json.loads(res.stdout)
            self.assertEqual(doc["mode"], "execute")
            self.assertTrue((out_dir / "sbom.cdx.json").is_file())
            self.assertTrue((out_dir / "osv.json").is_file())
            self.assertIn("evidence/sbom.cdx.json", doc["evidence"]["sbom"])
            self.assertIn("evidence/osv.json", doc["evidence"]["security_scans"])
            self.assertEqual({item["kind"] for item in doc["generated"]}, {"sbom", "security_scans"})

    def test_fail_on_gaps_is_opt_in(self):
        with tempfile.TemporaryDirectory() as tmp:
            res = run("--root", tmp, "--fail-on-gaps")
            self.assertEqual(res.returncode, 1)
            self.assertIn("no local sbom evidence", res.stdout)


if __name__ == "__main__":
    unittest.main()
