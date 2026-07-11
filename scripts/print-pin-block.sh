#!/usr/bin/env bash
# print-pin-block.sh — THIN SHIM over scripts/print_pin_block.py.
#
# Usage: scripts/print-pin-block.sh [ref]      (default: HEAD)
#
# The P0 version of this script hard-coded five pinned paths to match one
# moment's gates.yml — every gate the policy later registered would have
# silently drifted the published checksum docs. WS2-T9 replaced it with the
# policy-derived generator scripts/print_pin_block.py, which reads
# merge-policy.json's gate registry AT THE GIVEN REF and derives the checksummed
# file set from it. This shim survives only so muscle-memory / docs that name
# the .sh keep working; it forwards to the generator in --required-only mode,
# which emits exactly the minimal set the copy-in templates' heredocs pin (the
# runner, the policy, and the REQUIRED gate scripts). For the COMPLETE block
# (every gate script, incl. advisory), call the generator directly with no flag:
#   python3 scripts/print_pin_block.py [ref]
#
# Exit codes pass through the generator: 0 = block printed; 2 = usage error,
# unresolvable ref, invalid policy, or a pinned file missing at that commit.
set -u -o pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
exec python3 "${ROOT}/scripts/print_pin_block.py" --required-only "$@"
