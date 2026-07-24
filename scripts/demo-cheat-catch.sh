#!/usr/bin/env bash
# demo-cheat-catch.sh — the 60-second cheat-catch, fully offline (bash+git+python3).
# Builds a throwaway adopter repo from the shipped eval fixture, then shows the
# merge bar go green -> red -> green: an honest change passes, a committed
# "cheat" (test assertions gutted) is caught by test-guard, the revert passes.
# Exits 0 only when the whole sequence behaves; nonzero otherwise (testable).
set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_SYSTEM=/dev/null
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
DEMO="$TMP/adopter-repo"
TEST_FILE="$DEMO/tests/test_invitations.py"

g()   { git -C "$DEMO" -c user.name=demo -c user.email=demo@example.com \
            -c commit.gpgsign=false "$@"; }
bar() { python3 "$ROOT/scripts/gate_runner.py" --repo "$DEMO" --base "$BASE" \
            --change-class standard --declared "" \
            --plugin-root "$ROOT/plugins/core-engineering"; }

cp -R "$ROOT/evals/fixtures/implementation-ready-feature" "$DEMO" || exit 1
mkdir -p "$DEMO/tests"
cat > "$TEST_FILE" <<'EOF'
from src.invitations import create_invitation


def test_create_invitation_returns_token():
    inv = create_invitation('a@example.com', 'admin')
    assert inv['token']
    assert inv['email'] == 'a@example.com'
EOF
git -C "$DEMO" init -q -b main || exit 1
g add -A && g commit -qm "base: honest feature with a real test" || exit 1
BASE="$(g rev-parse HEAD)" || exit 1

echo "== 1/3 honest change -> bar is green =="
bar || { echo "DEMO BROKE: expected GREEN (exit 0) on the honest change"; exit 1; }

echo; echo "== 2/3 cheat committed (test assertions gutted) -> bar goes red =="
: > "$TEST_FILE"
g add -A && g commit -qm "cheat: gut the test assertions" || exit 1
bar; rc=$?
[ "$rc" -eq 1 ] || { echo "DEMO BROKE: expected RED (exit 1), got $rc"; exit 1; }

echo; echo "== 3/3 cheat reverted -> bar is green again =="
g revert --no-edit HEAD >/dev/null 2>&1 || exit 1
bar || { echo "DEMO BROKE: expected GREEN (exit 0) after the revert"; exit 1; }

echo; echo "demo complete: green -> red -> green — the cheat never had a path to merge."
