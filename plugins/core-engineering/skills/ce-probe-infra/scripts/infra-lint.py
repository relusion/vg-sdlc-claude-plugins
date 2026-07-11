#!/usr/bin/env python3
"""infra-lint.py — the offline, stdlib-only floor under /ce-probe-infra (probe-infra).

probe-infra audits Infrastructure-as-Code / Kubernetes / cloud manifests statically.
Like every gate in this corpus it is a TWO-LAYER discipline: richer findings come from
orchestrated ecosystem scanners (tfsec, checkov, kube-score, kube-linter, hadolint,
trivy config) when the human has them installed and the agent's cross-manifest reasoning
on top — but neither is guaranteed present, so THIS script is the deterministic floor
that always runs: it sweeps the repo, classifies each manifest by a parser-free
signature, and reports a small set of high-confidence facts and pattern hits offline.

The honest ceiling — why this is parser-free.  The Python standard library has `json`
and `tomllib` but NO YAML and NO HCL parser, and the portability guarantee
(docs/HOW-IT-WORKS.md §6, scripts/portability_check.py) forbids a third-party one. So
this script does what dep-guard.py does — parse JSON where it legitimately can and do the
rest by LINE-ORIENTED scanning — and it is deliberately conservative about what it will
call a FACT, because a regex that guesses at YAML/HCL block structure would manufacture
false failures and erode the one binary signal the tool offers.

  HARD checks (a FAIL -> exit 1) — provable parser-free, near-zero false positives:
    X-COPY  a Dockerfile `COPY`/`ADD` of a LOCAL source path that exists nowhere under
            the Dockerfile's directory or the scope root (URLs, globs, and `--from=`
            build-stage refs are exempt; the build context is an honest unknown, so a
            source found under either root clears the check). A missing local source is
            a fact, not an opinion.

  PATTERN hits (advisory; severity ceiling = Medium; the MODEL adjudicates) — a literal
  token on a line, never block structure:
    P-PRIVILEGED      privileged/hostNetwork/hostPID/hostIPC/allowPrivilegeEscalation: true
    P-OPEN-INGRESS    a 0.0.0.0/0 or ::/0 CIDR
    P-LATEST          an image pinned :latest or left untagged
    P-NO-USER         a Dockerfile with no USER directive (runs as root)
    P-WILDCARD-IAM    an IAM/RBAC Action/Resource/Principal/verbs/resources wildcard "*"
    P-UNENCRYPTED     encrypted=false / storage_encrypted=false
    P-PLAINTEXT-SECRET a credential signature in a manifest/env value (REDACTED on sight)

  ADVISORY signals (never change the exit code):
    overlay_context    Kustomize/Helm roots detected — the skill DEMOTES its model-judged
                       cross-reference findings (X-REF/X-VAL) to advisory here, because a
                       reference resolved by an overlay the static read cannot see is NOT
                       a broken reference.
    unsupported_formats a recognized-but-not-yet-supported family (Helm, compose,
                       CloudFormation, Kustomize, Bicep, Pulumi) — RECORDED as a coverage
                       gap, never silently skipped; the run still audits what it supports.

Cross-manifest reasoning the script does NOT assert as exit-1 (a k8s workload mounting a
ConfigMap/Secret name undefined in-repo = X-REF; a Terraform var.<x>/module output with no
definition = X-VAR; a Helm .Values.<x> absent from values.yaml = X-VAL) genuinely needs a
real YAML/HCL/Go-template parser and is left to the model lens and the orchestrated
scanners — the script flags only what it can prove without one.

Secrets are REDACTED, never exfiltrated.  A matched credential is reported by type +
file:line + a redacted excerpt; the raw value is never written to stdout/JSON. The script
does the offline detection only — no registry/cloud confirmation is ever performed here
(the dep-guard Network-Split: any live confirmation is an agent skill-prose discipline).

Supported families (v1): Terraform (.tf / .tf.json), Kubernetes (.yaml/.yml with
apiVersion+kind), Dockerfile. Helm / docker-compose / CloudFormation arrive as a per-format
module + one routing row each; the spine never changes.

Usage:
    infra-lint.py [--scope SUBPATH] [--root REPO] [--json] [--max-files N]

Exit codes (identical contract to dep-guard / spec-lint / patch-lint):
    0  PASS      — supported manifests swept, no HARD failure (status "pass"), OR no
                   supported manifests found at all (status "no-files" — reported, never
                   a silent green; a gating caller checks `status`, not just the code)
    1  FAIL      — at least one HARD failure (X-COPY)
    2  ERROR     — scope path missing/unreadable, or an unexpected crash; the caller
                   falls back to the orchestrated scanners / a manual review (loudly)
"""

from __future__ import annotations

import argparse
import base64
import json
import math
import re
import sys
from collections import Counter
from pathlib import Path

MAX_FILE_BYTES = 512 * 1024          # skip anything larger — manifests are small
DEFAULT_MAX_FILES = 5000             # a runaway-sweep backstop, surfaced when hit
SNIFF_BYTES = 4096                   # how far in we look to classify a YAML/JSON file

# Directories never worth sweeping for manifests.
SKIP_DIRS = {
    ".git", "node_modules", ".terraform", "vendor", "dist", "build", "target",
    ".venv", "venv", "env", "__pycache__", ".idea", ".vscode", ".mypy_cache",
    ".pytest_cache", ".next", ".nuxt", "coverage", ".gradle",
}


class InfraLintError(Exception):
    """Scope unreadable / inputs unloadable -> exit 2, caller falls back loudly."""


# --- detection: parser-free signatures --------------------------------------------

DOCKERFILE_RE = re.compile(r"(?:^|.*\.)?(?:Dockerfile|Containerfile)(?:\.[\w.-]+)?$")
_AWS_AK_RE = re.compile(r"\bAKIA[0-9A-Z]{16}\b")
_PEM_RE = re.compile(r"-----BEGIN (?:[A-Z0-9 ]+ )?PRIVATE KEY-----")
_ASSIGN_SECRET_RE = re.compile(
    r"""(?ix)
    \b(password|passwd|pwd|secret|secret[_-]?key|token|auth[_-]?token|
       api[_-]?key|access[_-]?key|client[_-]?secret|private[_-]?key|
       connection[_-]?string|conn[_-]?str)\b
    \s*[:=]\s*
    ['"]?(?P<val>[^\s'"#]{6,})['"]?
    """,
)
_PLACEHOLDER_RE = re.compile(
    r"""(?ix)^(
        \$\{.*\} | \{\{.*\}\} | <.*> |               # var / template / angle placeholders
        change[_-]?me | your[_-].* | example.* | sample.* | dummy.* | placeholder |
        x{3,} | todo | none | null | true | false |
        \d+(\.\d+)? |                                # bare number
        var\..* | local\..* | data\..* | module\..*  # HCL references
    )$""",
)


def classify(path_str: str, text: str | None) -> str | None:
    """Return a SUPPORTED family ('terraform'|'k8s'|'dockerfile'), 'UNSUP:<family>' for a
    recognized-but-unsupported one, or None for a non-infra file. `text` is the file's
    head (may be None when only the name is needed)."""
    name = path_str.rsplit("/", 1)[-1]
    low = name.lower()

    # Dockerfile family — name-only.
    if DOCKERFILE_RE.match(name):
        return "dockerfile"

    # Terraform — extension-only.
    if name.endswith(".tf") or name.endswith(".tf.json"):
        return "terraform"

    # Recognized-unsupported by filename.
    if low in ("kustomization.yaml", "kustomization.yml", "kustomization"):
        return "UNSUP:kustomize"
    if low in ("chart.yaml", "chart.yml"):
        return "UNSUP:helm"
    if low.startswith("pulumi.") and (low.endswith(".yaml") or low.endswith(".yml")):
        return "UNSUP:pulumi"
    if name.endswith(".bicep"):
        return "UNSUP:bicep"

    # YAML files need a content sniff to disambiguate k8s / compose / CFN / helm-template.
    if not (name.endswith(".yaml") or name.endswith(".yml")):
        return None
    if text is None:
        return None
    head = text[:SNIFF_BYTES]
    if "AWSTemplateFormatVersion" in head or re.search(r"Transform:\s*AWS::Serverless", head):
        return "UNSUP:cloudformation"
    if "/templates/" in ("/" + path_str) and "{{" in head:
        return "UNSUP:helm"
    if re.search(r"(?m)^\s{0,2}services\s*:", head) and not re.search(r"(?m)^\s*apiVersion\s*:", head):
        return "UNSUP:compose"
    if low.startswith("docker-compose") or low.startswith("compose."):
        return "UNSUP:compose"
    if re.search(r"(?m)^\s*apiVersion\s*:", head) and re.search(r"(?m)^\s*kind\s*:", head):
        if "{{" in head:                       # a Helm-templated k8s manifest
            return "UNSUP:helm"
        return "k8s"
    return None


# --- secret detection + redaction -------------------------------------------------

def _entropy(s: str) -> float:
    if not s:
        return 0.0
    n = len(s)
    return -sum((c / n) * math.log2(c / n) for c in Counter(s).values())


def _looks_secret(val: str) -> bool:
    """A generic value is a credential candidate only if it is long, high-entropy, and
    not an obvious placeholder / reference — keeps `password: changeme` from flagging."""
    if _PLACEHOLDER_RE.match(val):
        return False
    if "${" in val or "{{" in val or val.startswith("$"):
        return False
    return len(val) >= 8 and _entropy(val) >= 3.0


def _scrub(line: str) -> str:
    """Blank EVERY credential shape in a line so an excerpt can never carry a raw value —
    including a SECOND secret that shares the line with the one that triggered the finding
    (a real leak: redacting only the first match let the rest of the line through). Excerpts
    are produced only for already-flagged lines, so over-redaction here is safe by design."""
    text = _AWS_AK_RE.sub("[REDACTED]", line)
    text = _PEM_RE.sub("-----BEGIN [REDACTED] PRIVATE KEY-----", text)
    text = _ASSIGN_SECRET_RE.sub(lambda m: m.group(0).replace(m.group("val"), "[REDACTED]"), text)
    text = re.sub(r"[A-Za-z0-9+/]{20,}={0,2}", "[REDACTED]", text)  # long blobs (base64 etc.)
    return text.strip()[:200]


def scan_secrets(kind: str, lines: list[str]) -> list[dict]:
    """Return redacted secret findings. The raw value is used only to locate + redact;
    it is NEVER placed in a returned dict."""
    out: list[dict] = []
    in_secret = kind == "k8s" and any(re.match(r"\s*kind\s*:\s*Secret\b", ln) for ln in lines)
    for i, raw in enumerate(lines, 1):
        line = raw.rstrip("\n")
        if _AWS_AK_RE.search(line):
            out.append({"type": "AWS access key id", "line": i, "excerpt": _scrub(line)})
            continue
        if _PEM_RE.search(line):
            out.append({"type": "PEM private key header", "line": i, "excerpt": "-----BEGIN [REDACTED] PRIVATE KEY-----"})
            continue
        m = _ASSIGN_SECRET_RE.search(line)
        if m and _looks_secret(m.group("val")):
            out.append({"type": f"assignment to `{m.group(1).lower()}`", "line": i, "excerpt": _scrub(line)})
            continue
        # k8s Secret inline base64 data — best-effort region heuristic, never HARD.
        if in_secret:
            bm = re.match(r"\s*[\w.\-]+\s*:\s*([A-Za-z0-9+/]{16,}={0,2})\s*$", line)
            if bm:
                blob = bm.group(1)
                try:
                    decoded = base64.b64decode(blob, validate=True).decode("utf-8", "replace")
                except (ValueError, UnicodeError):
                    decoded = ""
                if _AWS_AK_RE.search(decoded) or _PEM_RE.search(decoded) or _looks_secret(decoded):
                    out.append({"type": "k8s Secret inline value (base64)", "line": i, "excerpt": _scrub(line)})
    return out


# --- pattern checks (parser-free, line-oriented) ----------------------------------

_PRIV_RE = re.compile(r"\b(privileged|hostNetwork|hostPID|hostIPC|allowPrivilegeEscalation)\s*:\s*true\b")
_OPEN_CIDR_RE = re.compile(r"(?<![\d.])0\.0\.0\.0/0|::/0")
_WILDCARD_IAM_RE = re.compile(
    r"""(?ix)
    ( "(Action|Resource|Principal)"\s*:\s*"\*" )            # JSON / TF policy
    | ( (actions|resources)\s*=\s*\[\s*"\*"\s*\] )          # HCL list
    | ( (verbs|resources|apiGroups)\s*:\s*\[?\s*['"]?\*['"]?\s*\]? )  # k8s RBAC
    """,
)
_UNENCRYPTED_RE = re.compile(r"\b(storage_encrypted|encrypted)\s*=\s*false\b")
_K8S_IMAGE_RE = re.compile(r"^\s*-?\s*image\s*:\s*['\"]?([^\s'\"#]+)")
_FROM_RE = re.compile(r"^\s*FROM\s+(?:--platform=\S+\s+)?(\S+)(?:\s+[Aa][Ss]\s+(\S+))?")
_USER_RE = re.compile(r"^\s*USER\s+\S+")
_COPY_RE = re.compile(r"^\s*(COPY|ADD)\s+(.*)$")
_GLOB_RE = re.compile(r"[*?\[\]{}]")


def _image_untagged_or_latest(ref: str, aliases: set[str]) -> bool:
    if ref in aliases or ref == "scratch":
        return False
    last = ref.rsplit("/", 1)[-1]              # strip registry/repo, keep name[:tag][@digest]
    if "@" in last:                            # digest-pinned — fine
        return False
    if ":" not in last:
        return True                            # untagged
    return last.rsplit(":", 1)[1] == "latest"


def _parse_copy_sources(args: str) -> list[str] | None:
    """Return local source paths for a COPY/ADD, or None to skip (has --from, JSON-parse
    fail, or no parseable sources)."""
    s = args.strip()
    if "--from=" in s:
        return None                            # build-stage ref, not a repo path
    if re.search(r"(?:^|\s)<<", s):
        return None                            # BuildKit here-doc — inline content, not a path
    if s.startswith("["):                      # JSON-array form: ["src",...,"dest"]
        try:
            arr = json.loads(s)
        except json.JSONDecodeError:
            return None
        toks = [str(x) for x in arr]
    else:
        toks = [t for t in s.split() if not t.startswith("--")]
    if len(toks) < 2:
        return None
    return toks[:-1]                           # all but the destination


def scan_file(kind: str, rel: str, text: str, dockerfile_dir: Path, scope_root: Path) -> tuple[list[dict], list[dict]]:
    """Return (hard_failures, pattern_findings) for one supported manifest."""
    lines = text.splitlines()
    hard: list[dict] = []
    findings: list[dict] = []

    def add(check: str, lens: str, line: int, msg: str) -> None:
        findings.append({"check": check, "lens": lens, "severity_ceiling": "medium",
                         "state": "manifest-read", "file": rel, "line": line, "message": msg})

    if kind == "dockerfile":
        aliases: set[str] = set()
        has_user = False
        for i, line in enumerate(lines, 1):
            mf = _FROM_RE.match(line)
            if mf:
                ref, alias = mf.group(1), mf.group(2)
                if alias:
                    aliases.add(alias)
                if _image_untagged_or_latest(ref, aliases):
                    add("P-LATEST", "config-hygiene", i, f"base image `{ref}` is :latest or untagged — pin a digest/version")
            if _USER_RE.match(line):
                has_user = True
            mc = _COPY_RE.match(line)
            if mc:
                srcs = _parse_copy_sources(mc.group(2))
                for src in (srcs or []):
                    if "://" in src or _GLOB_RE.search(src) or "$" in src or src in (".", ""):
                        continue                # URL, glob, or build-time var — an honest unknown, not a fact
                    rel_src = src.lstrip("/")
                    if (dockerfile_dir / rel_src).exists() or (scope_root / rel_src).exists():
                        continue
                    hard.append({"check": "X-COPY", "lens": "cross-manifest", "severity": "high",
                                 "state": "scanner-confirmed", "file": rel, "line": i,
                                 "message": f"{mc.group(1)} source `{src}` exists under neither the Dockerfile dir nor the scope root — broken build reference"})
        if not has_user:
            add("P-NO-USER", "workload-hardening", 0, "no USER directive — the container runs as root")

    if kind in ("k8s", "terraform"):
        for i, line in enumerate(lines, 1):
            if kind == "k8s" and _PRIV_RE.search(line):
                add("P-PRIVILEGED", "workload-hardening", i, "privileged/host-namespace/privilege-escalation flag set true")
            if _OPEN_CIDR_RE.search(line):
                add("P-OPEN-INGRESS", "network-exposure", i, "an open CIDR (0.0.0.0/0 or ::/0) — world-reachable")
            if _WILDCARD_IAM_RE.search(line):
                add("P-WILDCARD-IAM", "least-privilege", i, "a wildcard `*` IAM/RBAC action/resource/principal — over-broad grant")
            if kind == "terraform" and _UNENCRYPTED_RE.search(line):
                add("P-UNENCRYPTED", "config-hygiene", i, "encryption disabled (encrypted/storage_encrypted = false)")
            if kind == "k8s":
                mi = _K8S_IMAGE_RE.match(line)
                if mi and _image_untagged_or_latest(mi.group(1), set()):
                    add("P-LATEST", "config-hygiene", i, f"image `{mi.group(1)}` is :latest or untagged — pin a digest/version")

    for sec in scan_secrets(kind, lines):
        findings.append({"check": "P-PLAINTEXT-SECRET", "lens": "secrets-exposure",
                         "severity_ceiling": "medium", "state": "manifest-read",
                         "file": rel, "line": sec["line"],
                         "message": f"possible {sec['type']} in a manifest — value redacted: {sec['excerpt']}"})
    return hard, findings


# --- the sweep --------------------------------------------------------------------

def _read_head_and_text(p: Path) -> str | None:
    try:
        if p.stat().st_size > MAX_FILE_BYTES:
            return None
        data = p.read_bytes()
    except OSError:
        return None
    if b"\x00" in data[:1024]:                 # binary — not a manifest
        return None
    return data.decode("utf-8", "replace")


def run(root: Path, scope: Path, max_files: int) -> dict:
    if not scope.exists():
        raise InfraLintError(f"scope path does not exist: {scope}")
    if not _is_relative(scope, root):
        raise InfraLintError(f"--scope escapes --root (must stay under it): {scope}")
    hard: list[dict] = []
    findings: list[dict] = []
    formats: Counter = Counter()
    unsupported: list[dict] = []
    overlays: list[str] = []
    secrets_count = 0
    seen_unsup: set[str] = set()
    n_files = 0
    truncated = False

    paths = [scope] if scope.is_file() else sorted(
        p for p in scope.rglob("*")
        if p.is_file() and not (SKIP_DIRS & set(p.relative_to(scope).parts))
    )
    for p in paths:
        if n_files >= max_files:
            truncated = True
            break
        rel = str(p.relative_to(root)) if _is_relative(p, root) else str(p)
        # First classify by name (cheap); only read content for YAML disambiguation.
        kind = classify(rel, None)
        text = None
        if kind is None and (p.name.endswith(".yaml") or p.name.endswith(".yml")):
            text = _read_head_and_text(p)
            if text is None:
                continue
            kind = classify(rel, text)
        if kind is None:
            continue
        n_files += 1
        if kind.startswith("UNSUP:"):
            fam = kind.split(":", 1)[1]
            unsupported.append({"format": fam, "path": rel})
            if fam in ("kustomize", "helm") and fam not in seen_unsup:
                overlays.append(str(p.parent.relative_to(root)) if _is_relative(p, root) else str(p.parent))
            seen_unsup.add(fam)
            continue
        if text is None:
            text = _read_head_and_text(p)
            if text is None:
                continue
        formats[kind] += 1
        fhard, ffind = scan_file(kind, rel, text, p.parent, scope)
        hard.extend(fhard)
        findings.extend(ffind)
        secrets_count += sum(1 for f in ffind if f["check"] == "P-PLAINTEXT-SECRET")

    supported_total = sum(formats.values())
    status = "fail" if hard else ("pass" if supported_total else "no-files")
    return {
        "status": status,
        "scope": str(scope),
        "formats_detected": dict(formats),
        "supported_files": supported_total,
        "hard_failures": hard,
        "findings": findings,
        "secrets_redacted_count": secrets_count,
        "unsupported_formats": unsupported,
        "overlay_context": sorted(set(overlays)),
        "files_scanned_capped": truncated,
    }


def _is_relative(p: Path, root: Path) -> bool:
    try:
        p.relative_to(root)
        return True
    except ValueError:
        return False


# --- output -----------------------------------------------------------------------

def emit(result: dict, as_json: bool) -> int:
    code = 1 if result["status"] == "fail" else 0
    if as_json:
        print(json.dumps(result, indent=2))
        return code
    fd = result["formats_detected"]
    print("infra-lint: " + result["status"].upper())
    print(f"  scope: {result['scope']}")
    print(f"  supported manifests: {result['supported_files']} "
          + (", ".join(f"{k}={v}" for k, v in sorted(fd.items())) or "none"))
    if result["status"] == "no-files":
        print("  no supported manifests found under scope — nothing audited (not a clean bill of health).")
    if result["unsupported_formats"]:
        fams = sorted({u["format"] for u in result["unsupported_formats"]})
        print(f"  coverage gap — recognized but unsupported (v1): {', '.join(fams)} "
              f"({len(result['unsupported_formats'])} file(s)) — audit these with an orchestrated scanner")
    if result["overlay_context"]:
        print(f"  overlay context (Kustomize/Helm): {', '.join(result['overlay_context'])} "
              f"— cross-reference findings are advisory here, not facts")
    if result["secrets_redacted_count"]:
        print(f"  secrets redacted: {result['secrets_redacted_count']} (values never emitted)")
    if result["hard_failures"]:
        print(f"\n  FAIL — {len(result['hard_failures'])} hard reference break(s):")
        for h in result["hard_failures"]:
            print(f"    x {h['check']} {h['file']}:{h['line']} — {h['message']}")
    else:
        print("\n  no hard reference breaks." + (" (pattern findings below are advisory)" if result["findings"] else ""))
    if result["findings"]:
        print(f"\n  advisory findings ({len(result['findings'])} — Medium ceiling, model adjudicates):")
        for f in result["findings"]:
            loc = f"{f['file']}:{f['line']}" if f["line"] else f["file"]
            print(f"    ! {f['check']} [{f['lens']}] {loc} — {f['message']}")
    if result["files_scanned_capped"]:
        print("\n  WARNING — file cap hit; sweep was truncated (raise --max-files or narrow --scope).")
    print()
    return code


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Offline stdlib floor for /ce-probe-infra — static IaC/k8s/Dockerfile audit.")
    p.add_argument("--root", metavar="PATH", help="repo root for relative paths (default: cwd)")
    p.add_argument("--scope", metavar="SUBPATH", help="restrict the sweep to this path (file or dir, under root; default: root)")
    p.add_argument("--max-files", type=int, default=DEFAULT_MAX_FILES, help=f"sweep cap (default {DEFAULT_MAX_FILES}); a hit is reported, never silent")
    p.add_argument("--json", action="store_true", help="machine-readable result for infra-summary.json / a gating caller")
    args = p.parse_args(argv)

    try:
        root = Path(args.root).resolve() if args.root else Path.cwd()
        scope = (root / args.scope).resolve() if args.scope else root
        result = run(root, scope, max(1, args.max_files))
    except InfraLintError as e:
        if args.json:
            print(json.dumps({"status": "error", "message": str(e)}))
        else:
            print(f"infra-lint: ERROR — could not run: {e}", file=sys.stderr)
            print("  -> fall back to an orchestrated scanner or a manual review (loudly).", file=sys.stderr)
        return 2
    except Exception as e:  # noqa: BLE001 — any crash honors the exit-2 contract, never a fake exit-1 FAIL
        if args.json:
            print(json.dumps({"status": "error", "message": f"unexpected: {type(e).__name__}: {e}"}))
        else:
            print(f"infra-lint: ERROR — unexpected failure ({type(e).__name__}): {e}", file=sys.stderr)
            print("  -> fall back to an orchestrated scanner or a manual review (loudly).", file=sys.stderr)
        return 2
    return emit(result, args.json)


if __name__ == "__main__":
    sys.exit(main())
