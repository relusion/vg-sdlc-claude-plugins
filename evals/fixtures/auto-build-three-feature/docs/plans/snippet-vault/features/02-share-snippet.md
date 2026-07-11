# 02-share-snippet — Share a snippet by link

**Type:** user-facing · **Depends on:** 01-create-snippet · **Engineered path:** PARK

This feature carries an **unresolved blocking product decision**. A spawned spec agent
must **park** it (return `status:"parked"` with a reason) rather than guess — this is a
Product / business (blocking) class decision under the Decision Classification table, so
its disposition is **PARK** with class `product`. Parking here must not block 03, which
does not depend on 02.

## Scope (contingent on the parked decision)

- Produce a shareable reference to an existing snippet so another user can view it.

## The Blocking Product Decision (why this parks)

**Who may view a shared snippet, and for how long?** Three mutually exclusive product
models, each with different privacy, auth, and lifecycle consequences — none is an
engineering default, all are the product owner's call:

1. **Public link** — anyone with the URL can view, forever. Simple, but leaks any snippet
   whose link escapes.
2. **Org-only link** — viewers must belong to the owner's organization. Requires an
   identity/auth provider this plan has not chosen (a foundational auth decision).
3. **Signed expiring link** — anyone with an unexpired, signed token can view; links expire.
   Requires choosing a signing mechanism and an expiry policy.

Picking one silently would fabricate the owner's intent and set a privacy posture
(`TZ-002`) the plan never authorized. There is **no reversible default** — the choice
determines the auth model and the data-exposure surface. Therefore: **PARK (product).**

## Expected Auto-Build Behavior

- Spec agent returns `status:"parked"`, reason naming the undecided access model, class
  `product`.
- The orchestrator records a park (consecutive-park counter += 1) and surfaces it in the
  run report's **Parked — Needs Your Input** table and the end-review.
- 03-export-snippets still builds (no dependency on 02).

## Out of Scope

- Any implementation until the access model is decided by the owner at the end-review.
