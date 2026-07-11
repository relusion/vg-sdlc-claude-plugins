"""Offline test for scripts/demo-cheat-catch.sh — the 60-second cheat-catch.

Runs the demo end to end as a subprocess (bash + git + python3 only, no
network, no Claude) and asserts the full green -> red -> green sequence, in
order, with test-guard named as the catcher. The demo script itself exits
nonzero if any step misbehaves, so the exit-code assertion is the demo's own
self-test contract.
"""

import shutil
import subprocess
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "demo-cheat-catch.sh"


@unittest.skipUnless(shutil.which("git"), "the demo needs git")
@unittest.skipUnless(shutil.which("bash"), "the demo needs bash")
class DemoCheatCatch(unittest.TestCase):
    def test_green_red_green_sequence(self):
        res = subprocess.run(["bash", str(SCRIPT)], capture_output=True,
                             text=True, timeout=600)
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        out = res.stdout
        markers = [
            "== 1/3 honest change -> bar is green ==",
            "merge bar [standard]: integrity conjunct PASS",
            "== 2/3 cheat committed (test assertions gutted) -> bar goes red ==",
            "merge bar [standard]: integrity conjunct FAIL",
            "== 3/3 cheat reverted -> bar is green again ==",
            "merge bar [standard]: integrity conjunct PASS",
            "demo complete: green -> red -> green",
        ]
        pos = -1
        for marker in markers:
            found = out.find(marker, pos + 1)
            self.assertGreater(found, pos,
                               f"marker missing or out of order: {marker!r}\n{out}")
            pos = found
        self.assertIn("test-guard", out)  # the red verdict names its catcher
        # Piped stdout is not a TTY: the runner must emit no ANSI color.
        self.assertNotIn("\x1b", out)
