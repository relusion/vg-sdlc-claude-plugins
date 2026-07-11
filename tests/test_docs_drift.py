"""Tests for scripts/docs_drift.py, the manifest-driven docs-replay gate."""

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "docs_drift.py"
MANIFEST_REL = "docs/examples-manifest.json"
EXAMPLES_REL = "docs/EXAMPLES.md"
GOLDEN_SPEC_REL = "evals/golden/EVAL-005/specs/01-invite-user/spec.md"


def run(*args):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        timeout=120,
    )


def copy_repo(tmp: Path) -> Path:
    """Copy just the trees docs_drift touches: the manifest + EXAMPLES.md under
    docs/, the spec-lint.py the golden replay runs under plugins/, and the
    golden artifact under evals/ (never the gitignored evals/runs/)."""
    dst = tmp / "repo"
    for sub in ("docs", "plugins", "scripts"):
        shutil.copytree(REPO / sub, dst / sub,
                        ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(REPO / "evals", dst / "evals",
                    ignore=shutil.ignore_patterns("__pycache__", "runs"))
    return dst


def load_manifest(repo: Path) -> dict:
    return json.loads((repo / MANIFEST_REL).read_text(encoding="utf-8"))


def dump_manifest(repo: Path, data: dict) -> None:
    (repo / MANIFEST_REL).write_text(json.dumps(data, indent=2), encoding="utf-8")


def golden_entry(data: dict) -> dict:
    return next(e for e in data["examples"] if e["id"] == "EVAL-005")


class DocsDrift(unittest.TestCase):
    def test_this_repo_docs_drift_passes(self):
        res = run()
        self.assertEqual(res.returncode, 0, f"stdout={res.stdout}\nstderr={res.stderr}")
        self.assertIn("docs-drift: OK", res.stdout)

    def test_mutated_golden_makes_docs_drift_red(self):
        # The done-when: a mutated golden output turns the checker red. Dropping
        # the [SURFACE] tag flips spec-lint's surface_acs 1 -> 0, so the doc's
        # `"surface_acs": 1` anchor no longer appears in the replay output.
        with tempfile.TemporaryDirectory() as tmp:
            repo = copy_repo(Path(tmp))
            spec = repo / GOLDEN_SPEC_REL
            spec.write_text(
                spec.read_text(encoding="utf-8").replace("[SURFACE:", "[XXXXX:"),
                encoding="utf-8",
            )
            res = run("--root", str(repo))
            self.assertEqual(res.returncode, 1, res.stdout)
            self.assertIn("docs drift", res.stderr)
            self.assertIn("surface_acs", res.stderr)

    def test_uncovered_provenance_line_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = copy_repo(Path(tmp))
            examples = repo / EXAMPLES_REL
            examples.write_text(
                examples.read_text(encoding="utf-8")
                + "\n## 9. `/ce-plan` — a new uncovered example\n\n"
                "Provenance: live `EVAL-099`, 2026-07-05.\n",
                encoding="utf-8",
            )
            res = run("--root", str(repo))
            self.assertEqual(res.returncode, 1, res.stdout)
            self.assertIn("Provenance line but no", res.stderr)

    def test_anchor_pointing_at_missing_section_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = copy_repo(Path(tmp))
            data = load_manifest(repo)
            golden_entry(data)["doc_anchor"] = "## 9. `/ce-nonexistent`"
            dump_manifest(repo, data)
            res = run("--root", str(repo))
            self.assertEqual(res.returncode, 1, res.stdout)
            self.assertIn("matches no `## ` heading", res.stderr)

    def test_missing_anchor_in_output_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = copy_repo(Path(tmp))
            data = load_manifest(repo)
            golden_entry(data)["expected_anchors"].append("this-string-is-not-in-lint-output")
            dump_manifest(repo, data)
            res = run("--root", str(repo))
            self.assertEqual(res.returncode, 1, res.stdout)
            self.assertIn("docs drift", res.stderr)

    def test_wrong_expected_exit_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = copy_repo(Path(tmp))
            data = load_manifest(repo)
            golden_entry(data)["expected_exit"] = 3
            dump_manifest(repo, data)
            res = run("--root", str(repo))
            self.assertEqual(res.returncode, 1, res.stdout)
            self.assertIn("expected 3", res.stderr)

    def test_deterministic_entry_requires_anchors(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = copy_repo(Path(tmp))
            data = load_manifest(repo)
            golden_entry(data)["expected_anchors"] = []
            dump_manifest(repo, data)
            res = run("--root", str(repo))
            self.assertEqual(res.returncode, 1, res.stdout)
            self.assertIn("at least one", res.stderr)

    def test_unknown_source_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = copy_repo(Path(tmp))
            data = load_manifest(repo)
            golden_entry(data)["source"] = "made-up"
            dump_manifest(repo, data)
            res = run("--root", str(repo))
            self.assertEqual(res.returncode, 1, res.stdout)
            self.assertIn("'source'", res.stderr)

    def test_duplicate_ids_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = copy_repo(Path(tmp))
            data = load_manifest(repo)
            data["examples"].append(dict(golden_entry(data)))
            dump_manifest(repo, data)
            res = run("--root", str(repo))
            self.assertEqual(res.returncode, 1, res.stdout)
            self.assertIn("duplicate example id", res.stderr)

    def test_missing_manifest_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = copy_repo(Path(tmp))
            (repo / MANIFEST_REL).unlink()
            res = run("--root", str(repo))
            self.assertEqual(res.returncode, 1, res.stdout)
            self.assertIn("missing", res.stderr)

    def test_live_eval_entry_is_not_executed(self):
        # deterministic:false (model-run) entries must never be replayed. Point
        # a live-eval entry's command at a token that would fail loudly if run;
        # the checker must still pass because it never launches it.
        with tempfile.TemporaryDirectory() as tmp:
            repo = copy_repo(Path(tmp))
            data = load_manifest(repo)
            live = next(e for e in data["examples"] if not e["deterministic"])
            live["command"] = ["definitely-not-a-real-binary-xyz", "--boom"]
            dump_manifest(repo, data)
            res = run("--root", str(repo))
            self.assertEqual(res.returncode, 0, f"stdout={res.stdout}\nstderr={res.stderr}")


if __name__ == "__main__":
    unittest.main()
