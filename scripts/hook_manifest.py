#!/usr/bin/env python3
"""hook_manifest.py — generate / verify the hook self-integrity manifest.

The PreToolUse guards (git-guard, env-guard, write-scope-guard, net-guard)
police tool calls but cannot detect their OWN subversion — an in-session
`sed -i` on env-guard.py silently disarms the credential-read confinement and
no guard notices (the trust finding's "guards cannot detect their own
subversion"). This script is the commit-time half of the fix: it records the
sha256 of every `hooks/*.py` + `hooks.json` into a shipped, CI-verified
`integrity-manifest.json`, and re-checks it so a hook edited without refreshing
the manifest goes CI-red (the version-bump-hook pattern: mechanical freshness).
The runtime half is `hooks/hook-integrity.py`, a SessionStart hook that verifies
the same manifest and warns loudly on drift.

Honest bound — tamper-EVIDENCE, not tamper-proofing: an agent with Bash can
rewrite the manifest too, so the guarantee is only that the committed manifest
is CI-verified and any drift is therefore auditable in the reviewable diff (the
same claim class as the merge bar's `sha256sum -c` step), never that tampering
is impossible.

Modes (mutually exclusive; `--check` is the default):
  --write   regenerate integrity-manifest.json from the current hooks dir.
  --check   compare on-disk hooks to the committed manifest.
            exit 0 fresh · 1 stale/missing/mismatch · 2 could-not-run.

Stdlib-only.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOOKS_DIR = ROOT / "plugins" / "core-engineering" / "hooks"
MANIFEST_NAME = "integrity-manifest.json"
ALGORITHM = "sha256"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tracked_files(hooks_dir: Path) -> list:
    """The hooks whose integrity the manifest records: every ``*.py`` plus
    ``hooks.json`` in *hooks_dir*, sorted by basename. The manifest excludes
    itself (a ``.json`` that is not ``hooks.json``) and never descends into
    ``__pycache__``. hooks/hook-integrity.py keeps this selection rule identical
    so the runtime and commit-time checks agree on the exact file set.
    """
    files = [p for p in hooks_dir.glob("*.py")
             if p.is_file() and "__pycache__" not in p.parts]
    hooks_json = hooks_dir / "hooks.json"
    if hooks_json.is_file():
        files.append(hooks_json)
    return sorted(files, key=lambda p: p.name)


def compute(hooks_dir: Path) -> dict:
    """basename → sha256 for every tracked hook file."""
    return {p.name: _sha256(p) for p in tracked_files(hooks_dir)}


def build_manifest(hooks_dir: Path) -> dict:
    return {
        "_comment": ("sha256 of each hooks/*.py + hooks.json — regenerate with "
                     "`python3 scripts/hook_manifest.py --write` after an "
                     "intentional hook edit. hooks/hook-integrity.py verifies it "
                     "at SessionStart; scripts/check.py enforces its freshness at "
                     "commit time. Excludes itself."),
        "schema_version": 1,
        "algorithm": ALGORITHM,
        "hooks": compute(hooks_dir),
    }


def diff(hooks_dir: Path, manifest_path: Path) -> list:
    """Drift messages comparing on-disk hooks to *manifest_path*; [] when fresh.

    A missing or unreadable manifest is itself a (loud) drift message, so
    `--check` returns non-zero rather than passing on absence.
    """
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return [f"{manifest_path.name} is missing — run "
                f"`python3 scripts/hook_manifest.py --write`"]
    except (OSError, ValueError) as e:
        return [f"{manifest_path.name} could not be read/parsed: {e}"]
    recorded = manifest.get("hooks") if isinstance(manifest, dict) else None
    if not isinstance(recorded, dict):
        return [f"{manifest_path.name} has no 'hooks' object"]
    actual = compute(hooks_dir)
    problems = []
    for name in sorted(set(recorded) | set(actual)):
        if name not in actual:
            problems.append(f"{name}: recorded in the manifest but missing on disk")
        elif name not in recorded:
            problems.append(f"{name}: present on disk but absent from the manifest "
                            f"(unmanifested hook)")
        elif recorded[name] != actual[name]:
            problems.append(f"{name}: sha256 mismatch — recorded "
                            f"{str(recorded[name])[:12]}…, on disk {actual[name][:12]}…")
    return problems


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Generate/verify the hook self-integrity manifest.")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--write", action="store_true",
                      help="regenerate the manifest from the current hooks dir")
    mode.add_argument("--check", action="store_true",
                      help="verify on-disk hooks against the manifest (default)")
    ap.add_argument("--hooks-dir", default=str(HOOKS_DIR),
                    help="hooks directory (default: core-engineering hooks)")
    ap.add_argument("--manifest", default=None,
                    help="manifest path (default: <hooks-dir>/integrity-manifest.json)")
    args = ap.parse_args(argv)

    hooks_dir = Path(args.hooks_dir)
    manifest_path = (Path(args.manifest) if args.manifest
                     else hooks_dir / MANIFEST_NAME)
    if not hooks_dir.is_dir():
        print(f"hook_manifest: hooks dir {hooks_dir} does not exist", file=sys.stderr)
        return 2

    if args.write:
        manifest = build_manifest(hooks_dir)
        manifest_path.write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8")
        print(f"hook_manifest: wrote {manifest_path} "
              f"({len(manifest['hooks'])} hook file(s))")
        return 0

    # default = --check
    problems = diff(hooks_dir, manifest_path)
    if problems:
        for p in problems:
            print(f"hook self-integrity manifest is stale: {p}", file=sys.stderr)
        print("refresh with `python3 scripts/hook_manifest.py --write` after an "
              "intentional hook edit", file=sys.stderr)
        return 1
    print(f"hook_manifest: OK — {len(compute(hooks_dir))} hook file(s) match "
          f"{manifest_path.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
