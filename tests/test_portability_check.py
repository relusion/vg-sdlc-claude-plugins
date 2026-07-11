"""Tests for scripts/portability_check.py — the portability-guarantee prover.

The positive case doubles as the live guarantee: it runs the checker against
THIS repo, so the test suite itself fails the moment any shipped hook/gate
script grows a non-stdlib import or stops running without the harness.
"""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "portability_check.py"


def run(*args):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True, text=True, timeout=300,
    )


class Portability(unittest.TestCase):
    def test_this_repo_is_portable(self):
        res = run()
        self.assertEqual(res.returncode, 0,
                         f"stdout={res.stdout}\nstderr={res.stderr}")
        self.assertIn("portability: OK", res.stdout)

    def test_non_stdlib_import_is_flagged(self):
        with tempfile.TemporaryDirectory() as tmp:
            scripts = Path(tmp) / "plugins" / "p" / "skills" / "s" / "scripts"
            scripts.mkdir(parents=True)
            (scripts / "bad-gate.py").write_text(
                "import requests\nprint('hi')\n")
            res = run("--root", tmp)
            self.assertEqual(res.returncode, 1)
            self.assertIn("non-stdlib import(s): requests", res.stderr)

    def test_coshipped_sibling_import_is_allowed(self):
        # A `<name>.py` beside a gate script ships in the same scripts/ dir (a shared
        # helper like merge_disposition.py) — importing it is not a third-party dep, so
        # it must PASS. A non-stdlib import in the sibling is still caught when the scan
        # reaches the sibling itself.
        with tempfile.TemporaryDirectory() as tmp:
            scripts = Path(tmp) / "plugins" / "p" / "skills" / "s" / "scripts"
            scripts.mkdir(parents=True)
            (scripts / "helper.py").write_text("VALUE = 1\n")
            (scripts / "gate.py").write_text(
                "import sys, os\n"
                "sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))\n"
                "import helper\n"
                "sys.exit(0)\n")
            res = run("--root", tmp)
            self.assertEqual(res.returncode, 0, f"{res.stdout}\n{res.stderr}")

    def test_sibling_allowance_does_not_hide_its_own_bad_import(self):
        # The sibling itself is scanned: a third-party import inside it is still flagged,
        # so the sibling-allow can never launder a real dependency.
        with tempfile.TemporaryDirectory() as tmp:
            scripts = Path(tmp) / "plugins" / "p" / "skills" / "s" / "scripts"
            scripts.mkdir(parents=True)
            (scripts / "helper.py").write_text("import requests\n")
            (scripts / "gate.py").write_text(
                "import sys, os\n"
                "sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))\n"
                "import helper\n"
                "sys.exit(0)\n")
            res = run("--root", tmp)
            self.assertEqual(res.returncode, 1)
            self.assertIn("helper.py", res.stderr)
            self.assertIn("requests", res.stderr)

    def test_harness_env_dependence_is_flagged(self):
        # A script that crashes when CLAUDE_* vars are absent violates the
        # degrade-loudly rule; the scrubbed-env execution must catch it.
        with tempfile.TemporaryDirectory() as tmp:
            scripts = Path(tmp) / "plugins" / "p" / "hooks"
            scripts.mkdir(parents=True)
            (scripts / "needy.py").write_text(
                "import os, sys\n"
                "sys.exit(int(os.environ['CLAUDE_PROJECT_DIR'] is None))\n")
            res = run("--root", tmp)
            self.assertEqual(res.returncode, 1)
            self.assertIn("needy.py", res.stderr)

    def test_empty_layout_fails_loudly(self):
        # check.py's require() principle: an empty glob is a layout change,
        # never a green result.
        with tempfile.TemporaryDirectory() as tmp:
            res = run("--root", tmp)
            self.assertEqual(res.returncode, 1)
            self.assertIn("did the layout change", res.stderr)

    def test_benign_importerror_in_usage_text_is_not_flagged(self):
        # Anchored markers: a script that exits 0 and merely mentions
        # 'ImportError' in help prose must PASS, not false-FAIL.
        with tempfile.TemporaryDirectory() as tmp:
            scripts = Path(tmp) / "plugins" / "p" / "skills" / "s" / "scripts"
            scripts.mkdir(parents=True)
            (scripts / "gate.py").write_text(
                "import sys\n"
                "sys.stderr.write('usage: gate.py — stdlib only, no ImportError risk\\n')\n"
                "sys.exit(0)\n")
            res = run("--root", tmp)
            self.assertEqual(res.returncode, 0, res.stderr)

    def test_one_unreadable_file_is_attributed_not_a_blank_abort(self):
        # A non-UTF-8 source must become one attributed failure line, and the
        # scan must still complete (not exit 2 with no file named).
        with tempfile.TemporaryDirectory() as tmp:
            scripts = Path(tmp) / "plugins" / "p" / "skills" / "s" / "scripts"
            scripts.mkdir(parents=True)
            (scripts / "ok.py").write_text("import sys\nsys.exit(0)\n")
            (scripts / "bad.py").write_bytes(b"\xff\xfe import sys\n")
            res = run("--root", tmp)
            self.assertEqual(res.returncode, 1)
            self.assertIn("bad.py", res.stderr)
            self.assertIn("unreadable source", res.stderr)


if __name__ == "__main__":
    unittest.main()
