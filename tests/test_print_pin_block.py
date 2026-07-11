"""Offline tests for scripts/print_pin_block.py — the policy-derived pin-block
generator (and its thin scripts/print-pin-block.sh shim).

Runs the generator as a subprocess (python3 + git + coreutils only, no network,
no Claude) and asserts its whole contract: the `# TOOLKIT_REF` comment line
carries the 40-hex COMMIT SHA (an annotated tag peels to the commit, never the
tag object), the checksum lines DERIVE from merge-policy.json's gate registry
(complete = runner + policy + every gate script; --required-only = runner +
policy + the required-gate union), the sums are committed-state truth (immune to
working-tree dirt, round-trippable through `sha256sum -c` which skips the comment
line), the required-only set matches the copy-in templates' CHECKSUMS heredoc,
and exit 2 fires on an unresolvable ref / missing file / invalid policy.
"""

import hashlib
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "print_pin_block.py"
SHIM = REPO / "scripts" / "print-pin-block.sh"
PLUGIN_DIR = "plugins/core-engineering"
POLICY_REL = f"{PLUGIN_DIR}/merge-policy.json"
RUNNER_REL = "scripts/gate_runner.py"


def run_py(*args, cwd=None):
    script = (cwd / "scripts" / "print_pin_block.py") if cwd else SCRIPT
    return subprocess.run(
        ["python3", str(script), *args],
        capture_output=True, text=True, timeout=120, cwd=cwd or REPO,
    )


def run_shim(*args, cwd=None):
    script = (cwd / "scripts" / "print-pin-block.sh") if cwd else SHIM
    return subprocess.run(
        ["bash", str(script), *args],
        capture_output=True, text=True, timeout=120, cwd=cwd or REPO,
    )


def git(repo: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(repo), "-c", "user.name=t", "-c",
         "user.email=t@example.com", "-c", "commit.gpgsign=false", *args],
        text=True,
    ).strip()


def show_blob(repo: Path, ref: str, path: str) -> bytes:
    return subprocess.check_output(["git", "-C", str(repo), "show", f"{ref}:{path}"])


def block_paths(stdout: str) -> list[str]:
    """The pinned paths from a block's checksum lines (skips the comment line)."""
    return [ln.split("  ", 1)[1] for ln in stdout.splitlines()
            if ln and not ln.startswith("#")]


def committed_policy(repo: Path, ref: str = "HEAD") -> dict:
    return json.loads(show_blob(repo, ref, POLICY_REL).decode("utf-8"))


def expected_complete_paths(repo: Path, ref: str = "HEAD") -> list[str]:
    policy = committed_policy(repo, ref)
    paths = [RUNNER_REL, POLICY_REL]
    for gate in policy["gates"].values():
        paths.append(f"{PLUGIN_DIR}/{gate['script']}")
    return paths


def expected_required_paths(repo: Path, ref: str = "HEAD") -> list[str]:
    policy = committed_policy(repo, ref)
    req = set()
    for bar in [policy.get("defaults", {})] + list(policy.get("change_classes", {}).values()):
        req.update(bar.get("required_integrity_gates", []))
    paths = [RUNNER_REL, POLICY_REL]
    for gid, gate in policy["gates"].items():
        if gid in req:
            paths.append(f"{PLUGIN_DIR}/{gate['script']}")
    return paths


@unittest.skipUnless(shutil.which("git"), "needs git")
@unittest.skipUnless(shutil.which("bash"), "needs bash")
@unittest.skipUnless(shutil.which("sha256sum"), "needs coreutils sha256sum")
class PrintPinBlockGenerator(unittest.TestCase):
    def test_complete_block_derives_from_policy_and_is_committed_truth(self):
        res = run_py("HEAD")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        lines = res.stdout.splitlines()

        head = git(REPO, "rev-parse", "HEAD^{commit}")
        self.assertEqual(lines[0], f"# TOOLKIT_REF: '{head}'")

        # The pinned paths are exactly runner + policy + every policy-registered
        # gate script (derived, not hard-coded).
        self.assertEqual(block_paths(res.stdout), expected_complete_paths(REPO))

        # Every checksum is the committed HEAD blob, not the (possibly dirty)
        # working tree — the whole point of git-show sourcing.
        for line in lines[1:]:
            digest, sep, path = line.partition("  ")
            self.assertEqual(sep, "  ", f"not sha256sum format: {line!r}")
            self.assertRegex(digest, r"^[0-9a-f]{64}$")
            expected = hashlib.sha256(show_blob(REPO, "HEAD", path)).hexdigest()
            self.assertEqual(digest, expected, path)

    def test_required_only_is_runner_policy_and_required_gates(self):
        res = run_py("HEAD", "--required-only")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertEqual(block_paths(res.stdout), expected_required_paths(REPO))
        # Required-only is a subset of the complete set.
        complete = run_py("HEAD")
        self.assertTrue(
            set(block_paths(res.stdout)) <= set(block_paths(complete.stdout)))

    def test_required_only_matches_templates_checksums_heredoc(self):
        # The generator's minimal set is exactly what the copy-in templates pin
        # in their CHECKSUMS heredoc — so the two can never drift apart.
        req_paths = block_paths(run_py("HEAD", "--required-only").stdout)
        for tmpl in ("gates.yml", "gates.gitlab-ci.yml", "azure-pipelines-gates.yml"):
            text = (REPO / "templates" / "adopter-ci" / tmpl).read_text()
            body = text.split("<<'CHECKSUMS'")[1].split("CHECKSUMS")[0]
            tmpl_paths = [ln.split()[-1] for ln in body.splitlines() if ln.strip()]
            self.assertEqual(tmpl_paths, req_paths, tmpl)

    def test_complete_block_round_trips_through_sha256sum_c(self):
        # The FULL block (comment line included) pipes into `sha256sum -c` — the
        # `# TOOLKIT_REF` line is ignored as a comment; every file verifies OK
        # when the committed blobs are laid down at their paths.
        res = run_py("HEAD")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        with tempfile.TemporaryDirectory() as td:
            for path in block_paths(res.stdout):
                dest = Path(td) / path
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(show_blob(REPO, "HEAD", path))
            check = subprocess.run(
                ["sha256sum", "-c", "-"], input=res.stdout,
                capture_output=True, text=True, cwd=td)
        self.assertEqual(check.returncode, 0, check.stdout + check.stderr)

    def test_bogus_ref_exits_2_with_empty_stdout(self):
        res = run_py("no-such-ref-anywhere")
        self.assertEqual(res.returncode, 2, res.stdout + res.stderr)
        self.assertEqual(res.stdout, "")
        self.assertIn("cannot resolve", res.stderr)


@unittest.skipUnless(shutil.which("git"), "needs git")
@unittest.skipUnless(shutil.which("sha256sum"), "needs coreutils sha256sum")
class PrintPinBlockFixtures(unittest.TestCase):
    """Self-contained fixture repos prove derivation and failure modes without
    leaning on the real repo (a shallow CI checkout could graft blobs back)."""

    def _fixture(self, td: Path, policy: dict, files: dict, *, drop=()):
        repo = td / "repo"
        (repo / "scripts").mkdir(parents=True)
        shutil.copy(SCRIPT, repo / "scripts" / "print_pin_block.py")
        (repo / "scripts" / "gate_runner.py").write_text("# dummy runner\n")
        pol = repo / POLICY_REL
        pol.parent.mkdir(parents=True, exist_ok=True)
        pol.write_text(json.dumps(policy))
        for rel, content in files.items():
            if rel in drop:
                continue
            dest = repo / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(content)
        git(repo, "init", "-q", "-b", "main")
        git(repo, "add", "-A")
        git(repo, "commit", "-qm", "pin fixture")
        return repo

    def test_derives_the_exact_gate_set_from_a_custom_policy(self):
        policy = {
            "schema_version": 1,
            "gates": {
                "alpha": {"script": "skills/x/scripts/alpha.py", "args": [], "proves": "a"},
                "beta": {"script": "skills/y/scripts/beta.py", "args": [], "proves": "b"},
            },
            "change_classes": {"standard": {
                "required_integrity_gates": ["alpha"], "validity": "human",
                "advisory_gates": ["beta"]}},
            "defaults": {"required_integrity_gates": ["alpha"],
                         "validity": "two-human", "advisory_gates": ["beta"]},
        }
        files = {
            f"{PLUGIN_DIR}/skills/x/scripts/alpha.py": "print('a')\n",
            f"{PLUGIN_DIR}/skills/y/scripts/beta.py": "print('b')\n",
        }
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._fixture(Path(tmp), policy, files)
            res = run_py("HEAD", cwd=repo)
            self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
            self.assertEqual(block_paths(res.stdout), [
                RUNNER_REL, POLICY_REL,
                f"{PLUGIN_DIR}/skills/x/scripts/alpha.py",
                f"{PLUGIN_DIR}/skills/y/scripts/beta.py",
            ])
            req = run_py("HEAD", "--required-only", cwd=repo)
            self.assertEqual(block_paths(req.stdout), [
                RUNNER_REL, POLICY_REL,
                f"{PLUGIN_DIR}/skills/x/scripts/alpha.py",
            ])

    def test_annotated_tag_peels_to_commit_sha(self):
        policy = {"schema_version": 1,
                  "gates": {"alpha": {"script": "skills/x/scripts/alpha.py",
                                      "args": [], "proves": "a"}},
                  "defaults": {"required_integrity_gates": ["alpha"],
                               "validity": "two-human"}}
        files = {f"{PLUGIN_DIR}/skills/x/scripts/alpha.py": "print('a')\n"}
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._fixture(Path(tmp), policy, files)
            git(repo, "tag", "-a", "v9.9.9", "-m", "annotated")
            commit = git(repo, "rev-parse", "HEAD^{commit}")
            tag_obj = git(repo, "rev-parse", "v9.9.9")
            self.assertNotEqual(commit, tag_obj, "fixture must be annotated")
            res = run_py("v9.9.9", cwd=repo)
            self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
            self.assertEqual(res.stdout.splitlines()[0], f"# TOOLKIT_REF: '{commit}'")
            self.assertNotIn(tag_obj, res.stdout)

    def test_gate_script_missing_at_commit_exits_2_empty_stdout(self):
        policy = {"schema_version": 1,
                  "gates": {"alpha": {"script": "skills/x/scripts/alpha.py",
                                      "args": [], "proves": "a"}},
                  "defaults": {"required_integrity_gates": ["alpha"],
                               "validity": "two-human"}}
        # The policy names alpha.py but the file is never committed.
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._fixture(Path(tmp), policy, {}, drop=())
            res = run_py("HEAD", cwd=repo)
            self.assertEqual(res.returncode, 2, res.stdout + res.stderr)
            self.assertEqual(res.stdout, "")
            self.assertIn("does not exist at commit", res.stderr)

    def test_invalid_policy_exits_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            (repo / "scripts").mkdir(parents=True)
            shutil.copy(SCRIPT, repo / "scripts" / "print_pin_block.py")
            (repo / "scripts" / "gate_runner.py").write_text("# dummy\n")
            pol = repo / POLICY_REL
            pol.parent.mkdir(parents=True, exist_ok=True)
            pol.write_text("{ not json ")
            git(repo, "init", "-q", "-b", "main")
            git(repo, "add", "-A")
            git(repo, "commit", "-qm", "bad policy")
            res = run_py("HEAD", cwd=repo)
            self.assertEqual(res.returncode, 2, res.stdout + res.stderr)
            self.assertEqual(res.stdout, "")
            self.assertIn("not valid JSON", res.stderr)


@unittest.skipUnless(shutil.which("git"), "needs git")
@unittest.skipUnless(shutil.which("bash"), "needs bash")
class PrintPinBlockShim(unittest.TestCase):
    def test_shim_forwards_to_required_only(self):
        shim = run_shim("HEAD")
        direct = run_py("HEAD", "--required-only")
        self.assertEqual(shim.returncode, 0, shim.stdout + shim.stderr)
        self.assertEqual(shim.stdout, direct.stdout)

    def test_shim_passes_through_error_exit(self):
        res = run_shim("no-such-ref")
        self.assertEqual(res.returncode, 2, res.stdout + res.stderr)


if __name__ == "__main__":
    unittest.main()
