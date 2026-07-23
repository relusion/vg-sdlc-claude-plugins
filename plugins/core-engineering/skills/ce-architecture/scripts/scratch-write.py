#!/usr/bin/env python3
"""Safely write one ce-architecture scratch artifact from standard input.

The helper deliberately accepts content only on stdin. This keeps untrusted
requirement and repository text out of shell arguments. It writes only one of
the five canonical filenames, only below the operating system temporary
directory, and replaces that file atomically within the scratch directory.
An ``architecture.json`` write must already identify strict schema v2.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path


REQUIRED_FILES = {
    "solution-architecture.md",
    "views.md",
    "data-and-integrations.md",
    "quality-attributes.md",
    "architecture.json",
}
MAX_BYTES = 10 * 1024 * 1024
ARCHITECTURE_SCHEMA_URN = "urn:vg-sdlc:ce-architecture:architecture:v2"
ARCHITECTURE_SCHEMA_VERSION = 2


def _strict_object_pairs(pairs: list[tuple[str, object]]) -> dict:
    result: dict = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON object key: {key}")
        result[key] = value
    return result


def _inside(base: Path, candidate: Path) -> bool:
    try:
        candidate.resolve().relative_to(base.resolve())
        return True
    except (OSError, ValueError):
        return False


def write_scratch(scratch_dir: Path, filename: str, payload: bytes) -> Path:
    if filename not in REQUIRED_FILES:
        raise ValueError(f"filename is not a canonical architecture artifact: {filename}")
    if not payload:
        raise ValueError("scratch artifact input is empty")
    if len(payload) > MAX_BYTES:
        raise ValueError(f"scratch artifact exceeds {MAX_BYTES} bytes")

    temp_root = Path(tempfile.gettempdir()).resolve()
    if scratch_dir.is_symlink() or not scratch_dir.is_dir():
        raise ValueError("scratch directory must be an existing non-symlink directory")
    resolved_dir = scratch_dir.resolve()
    if resolved_dir == temp_root or not _inside(temp_root, resolved_dir):
        raise ValueError("scratch directory must be a child of the OS temporary directory")

    target = resolved_dir / filename
    if target.is_symlink() or (target.exists() and not target.is_file()):
        raise ValueError("scratch artifact target must be absent or a regular file")
    if filename == "architecture.json":
        try:
            parsed = json.loads(
                payload.decode("utf-8"),
                object_pairs_hook=_strict_object_pairs,
            )
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"architecture.json input is invalid: {exc}") from exc
        if not isinstance(parsed, dict):
            raise ValueError("architecture.json input must contain an object")
        if (
            parsed.get("$schema") != ARCHITECTURE_SCHEMA_URN
            or parsed.get("schema_version") != ARCHITECTURE_SCHEMA_VERSION
        ):
            raise ValueError(
                "architecture.json must be ce-architecture schema v2; "
                "legacy schema v1 requires regeneration"
            )
    else:
        try:
            payload.decode("utf-8")
        except UnicodeError as exc:
            raise ValueError(f"Markdown input must be UTF-8: {exc}") from exc

    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{filename}.", suffix=".tmp", dir=resolved_dir
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    finally:
        if temporary.exists():
            temporary.unlink()
    return target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Write one canonical ce-architecture scratch artifact from stdin"
    )
    parser.add_argument("scratch_dir", type=Path)
    parser.add_argument("filename")
    args = parser.parse_args(argv)
    try:
        target = write_scratch(args.scratch_dir, args.filename, sys.stdin.buffer.read())
    except (OSError, ValueError) as exc:
        print(f"scratch-write: {exc}", file=sys.stderr)
        return 2
    print(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
