#!/usr/bin/env python3
"""Inventory and optionally generate enterprise supply-chain evidence.

This utility supports the enterprise-hardening posture without pretending to be
an attestation authority. By default it only inventories local evidence files
and reports which external tools are available. With --execute it can run a
small portable subset of local generators when present (`syft` and
`osv-scanner`) and records failures as gaps.

Usage:
    python3 scripts/enterprise_evidence.py --json
    python3 scripts/enterprise_evidence.py --out docs/enterprise-evidence/inventory.json
    python3 scripts/enterprise_evidence.py --execute --evidence-dir /tmp/evidence
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_VERSION = 1
SKIP_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    "__pycache__",
    "node_modules",
}
TOOLS = [
    "syft",
    "osv-scanner",
    "scorecard",
    "cosign",
    "slsa-verifier",
    "gitleaks",
]
EVIDENCE_PATTERNS = {
    "sbom": [
        "**/sbom*.json",
        "**/*sbom*.spdx",
        "**/*.cdx.json",
        "**/bom.json",
        "**/*.spdx",
        "**/*.spdx.json",
    ],
    "provenance": [
        "**/provenance*.json",
        "**/*.intoto.jsonl",
        "**/attestation*.json",
        "**/*.attestation.json",
    ],
    "signatures": [
        "**/*.sig",
        "**/*.sigstore",
        "**/signatures/*.json",
    ],
    "checksums": [
        "**/checksums.txt",
        "**/SHA256SUMS",
        "**/*.sha256",
    ],
    "scorecard": [
        "**/scorecard*.json",
        "**/*openssf*.json",
    ],
    "security_scans": [
        "**/osv*.json",
        "**/*gitleaks*.json",
        "**/*.sarif",
    ],
}


def rel(root: Path, path: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%SZ")


def discover_tools() -> dict:
    out = {}
    for tool in TOOLS:
        path = shutil.which(tool)
        out[tool] = {"available": path is not None, "path": path}
    return out


def all_files(root: Path):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        current = Path(dirpath)
        for name in filenames:
            yield current / name


def match_pattern(rel_path: str, pattern: str) -> bool:
    if fnmatch.fnmatch(rel_path, pattern):
        return True
    if pattern.startswith("**/") and fnmatch.fnmatch(rel_path, pattern[3:]):
        return True
    return False


def inventory_evidence(root: Path) -> dict:
    out = {category: [] for category in EVIDENCE_PATTERNS}
    for path in all_files(root):
        rel_path = rel(root, path)
        for category, patterns in EVIDENCE_PATTERNS.items():
            if any(match_pattern(rel_path, pattern) for pattern in patterns):
                out[category].append(rel_path)
    for paths in out.values():
        paths.sort()
    return out


def git_remote(root: Path) -> str | None:
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), "config", "--get", "remote.origin.url"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    value = proc.stdout.strip()
    return value or None


def github_repo_url(remote: str | None) -> str:
    if not remote:
        return "<github-repo-url>"
    if remote.startswith("git@github.com:"):
        return "https://github.com/" + remote.removeprefix("git@github.com:").removesuffix(".git")
    if remote.startswith("https://github.com/"):
        return remote.removesuffix(".git")
    return remote


def recommended_commands(repo_url: str) -> dict:
    base = "docs/enterprise-evidence/<run-id>"
    return {
        "sbom": [
            f"mkdir -p {base}",
            f"syft dir:. -o cyclonedx-json > {base}/sbom.cdx.json",
            f"syft dir:. -o spdx-json > {base}/sbom.spdx.json",
        ],
        "vulnerabilities": [
            f"osv-scanner --recursive --format json . > {base}/osv.json",
        ],
        "scorecard": [
            f"scorecard --format json --repo {repo_url} > {base}/scorecard.json",
        ],
        "signatures": [
            "cosign verify-blob --certificate <cert.pem> --signature <artifact.sig> <artifact>",
        ],
        "provenance": [
            "slsa-verifier verify-artifact <artifact> --provenance-path <provenance.intoto.jsonl> --source-uri <repo-url>",
        ],
    }


def run_capture(cmd: list[str], cwd: Path, timeout: int = 180) -> tuple[int, str, str]:
    proc = subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return proc.returncode, proc.stdout, proc.stderr


def execute_generators(root: Path, evidence_dir: Path, tools: dict, gaps: list[str]) -> list[dict]:
    evidence_dir.mkdir(parents=True, exist_ok=True)
    generated: list[dict] = []

    if tools.get("syft", {}).get("available"):
        out = evidence_dir / "sbom.cdx.json"
        cmd = ["syft", f"dir:{root}", "-o", "cyclonedx-json"]
        try:
            code, stdout, stderr = run_capture(cmd, root)
            if code == 0 and stdout.strip():
                out.write_text(stdout, encoding="utf-8")
                generated.append({"kind": "sbom", "path": rel(root, out), "command": cmd})
            else:
                gaps.append(f"syft failed with exit {code}: {(stderr or stdout).strip()[:240]}")
        except (OSError, subprocess.SubprocessError) as exc:
            gaps.append(f"syft could not run: {exc}")
    else:
        gaps.append("syft not found; SBOM generation skipped")

    if tools.get("osv-scanner", {}).get("available"):
        out = evidence_dir / "osv.json"
        cmd = ["osv-scanner", "--recursive", "--format", "json", str(root)]
        try:
            code, stdout, stderr = run_capture(cmd, root)
            if code in (0, 1) and stdout.strip():
                out.write_text(stdout, encoding="utf-8")
                generated.append({"kind": "security_scans", "path": rel(root, out), "command": cmd})
                if code == 1:
                    gaps.append("osv-scanner reported vulnerabilities; inspect generated evidence")
            else:
                gaps.append(f"osv-scanner failed with exit {code}: {(stderr or stdout).strip()[:240]}")
        except (OSError, subprocess.SubprocessError) as exc:
            gaps.append(f"osv-scanner could not run: {exc}")
    else:
        gaps.append("osv-scanner not found; vulnerability evidence generation skipped")

    return generated


def collect(root: Path, execute: bool, evidence_dir: Path | None) -> dict:
    gaps: list[str] = []
    tools = discover_tools()
    remote = git_remote(root)
    repo_url = github_repo_url(remote)
    evidence = inventory_evidence(root)
    generated: list[dict] = []

    if execute:
        if evidence_dir is None:
            evidence_dir = root / "docs" / "enterprise-evidence" / utc_stamp()
        generated = execute_generators(root, evidence_dir, tools, gaps)
        evidence = inventory_evidence(root)

    for category in ("sbom", "provenance", "signatures", "checksums", "scorecard"):
        if not evidence[category]:
            gaps.append(f"no local {category} evidence found")

    return {
        "schema_version": SCHEMA_VERSION,
        "tool": "core-engineering enterprise-evidence",
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "root": str(root),
        "mode": "execute" if execute else "inventory",
        "repo_remote": remote,
        "repo_url": repo_url,
        "tools": tools,
        "evidence": evidence,
        "generated": generated,
        "recommended_commands": recommended_commands(repo_url),
        "gaps": gaps,
        "honest_limitations": [
            "Inventory/generation helper, not a signed attestation.",
            "Tool availability does not prove policy compliance; review generated artifacts externally.",
            "Scorecard, cosign, and SLSA verification are recommended commands here because they require organization-specific repo and artifact context.",
        ],
    }


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inventory optional enterprise evidence")
    parser.add_argument("--root", default=str(DEFAULT_ROOT), help="repository root")
    parser.add_argument("--json", action="store_true",
                        help="print JSON to stdout (default unless --out is used)")
    parser.add_argument("--out", help="write JSON report to FILE")
    parser.add_argument("--execute", action="store_true",
                        help="run local generators that are installed (currently syft and osv-scanner)")
    parser.add_argument("--evidence-dir",
                        help="directory for generated evidence when --execute is used")
    parser.add_argument("--fail-on-gaps", action="store_true",
                        help="exit 1 when missing evidence or tool failures are reported")
    args = parser.parse_args(argv)

    try:
        root = Path(args.root).resolve()
        evidence_dir = Path(args.evidence_dir).resolve() if args.evidence_dir else None
        report = collect(root, args.execute, evidence_dir)
        rendered = json.dumps(report, indent=2, sort_keys=True)
        if args.out:
            write_text(Path(args.out), rendered + "\n")
        if args.json or not args.out:
            print(rendered)
        return 1 if args.fail_on_gaps and report["gaps"] else 0
    except Exception as exc:  # pragma: no cover - defensive CLI boundary
        print(f"enterprise-evidence: unexpected error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
