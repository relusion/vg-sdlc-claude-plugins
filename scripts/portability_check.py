#!/usr/bin/env python3
"""
portability_check.py — prove the shipped gate/hook scripts run with zero
Claude Code dependencies.

The portability guarantee (docs/HOW-IT-WORKS.md §6): every durable artifact is
plain text in the repo and every gate is plain stdlib Python, so the SDLC
state and its enforcement survive any harness or vendor change. This script
makes the gate half of that guarantee a CI-checked fact instead of a claim:

  A. Static: every shipped runtime script (plugins/*/hooks/*.py and
     plugins/*/skills/*/scripts/*.py) imports only the Python standard
     library (AST-parsed, including imports nested inside functions).
  B. Dynamic: each script executes under a scrubbed environment (no CLAUDE_*
     variables, bare PATH/HOME) with empty stdin and no arguments, and exits
     within the house contract {0, 1, 2} with no ImportError/Traceback —
     i.e. it degrades loudly or reports usage, it never crashes on the
     absence of the harness.

Honest scope: this proves the gates RUN outside Claude Code. It does not (and
cannot) prove the workflows around them — skill auto-invocation, hooks
enforcement, progressive disclosure — which are harness features by design.

Exit codes: 0 all portable · 1 violations found · 2 could-not-run.
Stdlib-only itself, obviously.
"""

import argparse
import ast
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

DEFAULT_ROOT = Path(__file__).resolve().parents[1]

# argparse exits 2 on bad usage; the house gate contract is {0,1,2}.
ALLOWED_EXIT_CODES = {0, 1, 2}
# Anchored to REAL crash shapes (line-start), so benign usage prose mentioning
# "ImportError" in help text is not a false FAIL.
CRASH_RE = re.compile(
    r"^Traceback \(most recent call last\)|^\s*(ModuleNotFoundError|ImportError):",
    re.MULTILINE,
)
RUN_TIMEOUT_SECONDS = 30


def shipped_scripts(root: Path) -> list:
    pats = ["plugins/*/hooks/*.py", "plugins/*/skills/*/scripts/*.py"]
    found: list = []
    for pat in pats:
        found.extend(sorted(root.glob(pat)))
    return [p for p in found if "__pycache__" not in p.parts]


def nonstdlib_imports(script: Path) -> list:
    """Top-level module names imported anywhere in the file that are neither stdlib nor a
    co-shipped sibling. A `<name>.py` beside this script ships in the same skill scripts/
    dir (a shared gate helper like merge_disposition.py), so importing it stays harness-
    and third-party-free — and any non-stdlib import IT carries is caught independently
    when this same scan reaches the sibling. The dynamic run below proves it resolves."""
    tree = ast.parse(script.read_text(encoding="utf-8"), filename=str(script))
    mods = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            mods.add(node.module.split(".")[0])
    siblings = {p.stem for p in script.parent.glob("*.py")}
    return sorted(m for m in mods
                  if m not in sys.stdlib_module_names and m not in siblings)


def scrubbed_env(tmp_home: str) -> dict:
    return {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": tmp_home,
        "LANG": "C.UTF-8",
        # Deliberately NO CLAUDE_* variables: the scripts must degrade loudly
        # without the harness, not crash.
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Prove shipped gate/hook scripts run with zero Claude Code deps")
    ap.add_argument("--root", default=str(DEFAULT_ROOT),
                    help="repo root to scan (default: this repo; for tests)")
    args = ap.parse_args(argv)
    root = Path(args.root)

    scripts = shipped_scripts(root)
    if not scripts:
        # The require() principle from check.py: an empty glob is a layout
        # change, never a green result.
        print("portability: no shipped scripts matched plugins/*/hooks/*.py or "
              "plugins/*/skills/*/scripts/*.py — did the layout change?",
              file=sys.stderr)
        return 1

    failures = []
    with tempfile.TemporaryDirectory() as tmp_home:
        env = scrubbed_env(tmp_home)
        for script in scripts:
            rel = script.relative_to(root)

            # One bad file becomes ONE attributed failure line, never an
            # un-attributed abort of the whole scan.
            try:
                bad = nonstdlib_imports(script)
            except SyntaxError as e:
                failures.append(f"{rel}: does not parse: {e}")
                continue
            except (OSError, UnicodeDecodeError) as e:
                failures.append(f"{rel}: unreadable source: {e}")
                continue
            if bad:
                failures.append(f"{rel}: non-stdlib import(s): {', '.join(bad)}")
                continue

            try:
                proc = subprocess.run(
                    [sys.executable, str(script)],
                    stdin=subprocess.DEVNULL,
                    capture_output=True,  # bytes (no text=): decode defensively below
                    env=env,
                    cwd=tmp_home,  # not the repo: no accidental repo coupling
                    timeout=RUN_TIMEOUT_SECONDS,
                )
            except subprocess.TimeoutExpired:
                failures.append(f"{rel}: hung >{RUN_TIMEOUT_SECONDS}s under a "
                                f"scrubbed environment")
                continue
            except OSError as e:
                failures.append(f"{rel}: could not execute: {e}")
                continue
            combined = (proc.stdout + proc.stderr).decode("utf-8", "replace")
            if proc.returncode not in ALLOWED_EXIT_CODES:
                failures.append(f"{rel}: exit {proc.returncode} outside the "
                                f"0/1/2 contract under a scrubbed environment")
            else:
                m = CRASH_RE.search(combined)
                if m:
                    line = combined[m.start():].splitlines()[0].strip()
                    failures.append(f"{rel}: crashed without the harness: {line}")

    if failures:
        print(f"portability: FAIL — {len(failures)} of {len(scripts)} shipped "
              f"script(s) not harness-independent:\n", file=sys.stderr)
        for f in failures:
            print(f"  ✗ {f}", file=sys.stderr)
        return 1
    print(f"portability: OK — {len(scripts)} shipped script(s) are stdlib-only "
          f"and run (0/1/2, no crash) with no Claude Code present.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as e:  # noqa: BLE001 — could-not-run is 2, never a fake FAIL
        print(f"portability: unexpected error: {type(e).__name__}: {e}",
              file=sys.stderr)
        sys.exit(2)
