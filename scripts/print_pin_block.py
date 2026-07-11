#!/usr/bin/env python3
"""print_pin_block.py — emit the adopter merge-bar pin block for one toolkit commit,
DERIVED from merge-policy.json's gate registry (never a hand-kept file list).

Usage:
    python3 scripts/print_pin_block.py [ref] [--required-only]   (default ref: HEAD)

WHY THIS EXISTS
    The P0 predecessor (scripts/print-pin-block.sh, now a thin shim over this
    generator) HARD-CODED five pinned paths to match one moment's gates.yml.
    Every gate the policy later registers (WS2-T8 added sca-guard,
    implement-scope, review-gate, plan-lint) would have silently drifted the
    published checksum docs. This generator reads the policy AT THE GIVEN REF
    and derives the checksummed file set from it, so a gate addition can never
    again leave a published pin block incomplete.

WHAT IT EMITS (stdout, all-or-nothing — a half-filled block never publishes)
    A `# TOOLKIT_REF` comment line carrying the 40-hex COMMIT SHA the ref peels
    to (an annotated tag yields the commit it points at, never the tag object's
    own SHA — the adopter templates' 40-hex guard demands a commit SHA), then
    one `<sha256>  <path>` line per pinned file, in the policy's gate-declaration
    order:

        # TOOLKIT_REF: '<40-hex-commit-sha>'
        <sha256>  scripts/gate_runner.py
        <sha256>  plugins/core-engineering/merge-policy.json
        <sha256>  plugins/core-engineering/skills/ce-spec/scripts/spec-lint.py
        ...one line per policy-registered gate script...

    The TOOLKIT_REF line is a `#` comment so the whole block pipes straight into
    `sha256sum -c` (which ignores comment lines) for a one-shot round-trip check
    in a clean checkout:  `python3 scripts/print_pin_block.py HEAD | sha256sum -c`.

    Default: the COMPLETE set — the runner, the policy, and EVERY policy-registered
    gate script (required AND advisory), so a published block gives tamper-evidence
    on advisory scripts too. This is what release-pin-block.yml publishes.

    --required-only: the runner, the policy, and only the REQUIRED gate scripts
    (the union of every bar's required_integrity_gates) — the minimal set the
    copy-in gates.yml / gates.gitlab-ci.yml / azure-pipelines-gates.yml heredocs
    pin. Same policy-declaration order, so its lines are a stable prefix an
    adopter pastes over those templates' <PIN-ME-*> placeholders.

CHECKSUMS ARE COMMITTED-STATE TRUTH
    Every checksum is computed from `git show <sha>:<path>` — the committed blob
    at that commit — so working-tree dirt (even staged) can never leak into a
    published pin. The gate LIST likewise comes from the policy AS COMMITTED at
    the ref, not the working-tree policy.

Offline floor: python3 + git, nothing else (stdlib only — the portability
guarantee; this tool ships in scripts/ like check.py/gate_runner.py, not inside
the plugin, so portability_check.py does not scan it, but it stays stdlib anyway).

Exit codes (house contract subset):
    0  block printed
    2  usage error, unresolvable ref, policy missing/invalid at the ref, or a
       pinned file missing at that commit (argparse also exits 2 on bad usage)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

# The generator lives at <repo>/scripts/print_pin_block.py; git operations target
# the repo the script resides in (mirrors the .sh's BASH_SOURCE-relative ROOT so
# a copy dropped into a fixture repo operates on that fixture).
ROOT = Path(__file__).resolve().parents[1]

# The runner and the policy always pin; the policy dir is where plugin-relative
# gate `script` paths resolve.
RUNNER_PATH = "scripts/gate_runner.py"
PLUGIN_DIR = "plugins/core-engineering"
POLICY_PATH = f"{PLUGIN_DIR}/merge-policy.json"


class PinBlockError(Exception):
    """Any reason a complete block cannot be produced -> exit 2 (never a partial)."""


def _git(root: Path, *args: str) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(["git", "-C", str(root), *args],
                              capture_output=True, timeout=60)
    except FileNotFoundError as e:
        raise PinBlockError("git is not on PATH — the generator reads committed "
                            "blobs and cannot run without git") from e
    except subprocess.TimeoutExpired as e:
        raise PinBlockError(f"git {' '.join(args[:2])} timed out in {root}") from e


def resolve_commit(root: Path, ref: str) -> str:
    """Peel <ref> to the commit SHA it names — `^{commit}` makes an annotated tag
    yield the commit, never the tag object, matching the adopter templates' guard."""
    proc = _git(root, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}")
    if proc.returncode != 0:
        raise PinBlockError(f"cannot resolve '{ref}' to a commit in {root}")
    return proc.stdout.decode().strip()


def show_blob(root: Path, sha: str, path: str) -> bytes:
    """The committed blob at <sha>:<path>; a missing path fails the whole block."""
    proc = _git(root, "show", f"{sha}:{path}")
    if proc.returncode != 0:
        raise PinBlockError(f"'{path}' does not exist at commit {sha}")
    return proc.stdout


def _gate_script_rel(gate_id: str, gate: object) -> str:
    """The repo-relative pinned path for one policy gate, hardened against a
    script value that would escape the plugin dir (defensive — check.py §14 and
    gate_runner already reject these on the shipped policy, but a --ref may name
    an older/edited committed policy this generator never validated)."""
    if not isinstance(gate, dict) or not isinstance(gate.get("script"), str) \
            or not gate["script"]:
        raise PinBlockError(f"gate '{gate_id}': missing/invalid 'script'")
    script = gate["script"]
    parts = Path(script).parts
    if Path(script).is_absolute() or ".." in parts:
        raise PinBlockError(
            f"gate '{gate_id}': script path must be plugin-relative without "
            f"'..', got '{script}'")
    return f"{PLUGIN_DIR}/{script}"


def required_gate_ids(policy: dict) -> set[str]:
    """The union of every bar's required_integrity_gates (defaults + each change
    class) — the gates any PR's verdict can turn on, i.e. the minimal pin set."""
    ids: set[str] = set()
    bars: list[object] = [policy.get("defaults")]
    classes = policy.get("change_classes")
    if isinstance(classes, dict):
        bars.extend(classes.values())
    for bar in bars:
        if isinstance(bar, dict):
            req = bar.get("required_integrity_gates")
            if isinstance(req, list):
                ids.update(g for g in req if isinstance(g, str))
    return ids


def derive_pinned_paths(policy: dict, required_only: bool) -> list[str]:
    """runner + policy + gate scripts (in policy gate-declaration order). With
    required_only, keep only gates in the required union."""
    gates = policy.get("gates")
    if not isinstance(gates, dict) or not gates:
        raise PinBlockError("policy 'gates' must be a non-empty object")
    keep = required_gate_ids(policy) if required_only else None
    paths = [RUNNER_PATH, POLICY_PATH]
    for gate_id, gate in gates.items():
        if keep is not None and gate_id not in keep:
            continue
        paths.append(_gate_script_rel(gate_id, gate))
    return paths


def build_block(root: Path, ref: str, required_only: bool) -> str:
    """The full pin block as one string (no trailing newline). Everything is
    computed before anything is returned — the caller prints all-or-nothing."""
    sha = resolve_commit(root, ref)
    try:
        policy = json.loads(show_blob(root, sha, POLICY_PATH).decode("utf-8"))
    except ValueError as e:
        raise PinBlockError(f"policy at {sha}:{POLICY_PATH} is not valid JSON: {e}") from e
    if not isinstance(policy, dict):
        raise PinBlockError(f"policy at {sha}:{POLICY_PATH} must be a JSON object")

    lines = [f"# TOOLKIT_REF: '{sha}'"]
    for path in derive_pinned_paths(policy, required_only):
        digest = hashlib.sha256(show_blob(root, sha, path)).hexdigest()
        lines.append(f"{digest}  {path}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Emit the policy-derived merge-bar pin block for one toolkit "
                    "commit (checksums from committed blobs).")
    parser.add_argument("ref", nargs="?", default="HEAD",
                        help="git ref to pin (default: HEAD; an annotated tag "
                             "peels to its commit)")
    parser.add_argument("--required-only", action="store_true",
                        help="pin only the runner, policy, and REQUIRED gate "
                             "scripts (the minimal set the copy-in templates' "
                             "heredocs use); default pins every gate script")
    args = parser.parse_args(argv)
    try:
        print(build_block(ROOT, args.ref, args.required_only))
        return 0
    except PinBlockError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
