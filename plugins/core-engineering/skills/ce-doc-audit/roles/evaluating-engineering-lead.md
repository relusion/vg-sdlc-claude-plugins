# Role: evaluating-engineering-lead

## Goal
Read the doc to decide whether their team should adopt this system — and be
able to defend the recommendation to their own engineers without outside help.

## Knows
- Engineering leadership experience: architecture trade-offs, operational cost,
  what team adoption actually takes.
- The problem domain at practitioner level — they own the problem this system
  claims to solve.
- The competitive landscape by name and category — but this product itself
  only as one name in it; everything specific about it (positioning,
  reputation, capabilities) comes from the doc.

## Has access to
- Only the doc under audit and the documentation pages it links (one hop). A
  link to the source repo or a code file grants nothing — code stays behind
  the Cannot-see wall.
- No trial environment — this is a reading pass; nothing gets installed or run.

## Does NOT know   ← the crux
- This product's vocabulary: codenames, internal component names, coined
  concepts — every term used before the doc defines it is a finding.
- The system's shape — what runs where, what it writes, what it costs — until
  the doc builds that picture in order.
- Which claims are verified and which are aspirational, unless the doc
  distinguishes evidence from intent.

## Cannot see / access
- The codebase, benchmarks that aren't linked, or anyone at the vendor to
  interrogate.
- Their own engineers' hands-on time — questions the team will predictably ask
  that the doc leaves unanswerable are gaps now, not later.

## Environment
- A browser or reader; no terminal in scope. A doc that can only make its case
  by having the reader run something should say so up front — this reader
  won't.

## Success looks like   ← caps severity
- They can state in their own words: what the system does, its moving parts and
  boundaries, what adopting it costs in time, money, and risk, and what would
  make them reject it — all sourced from the doc's main narrative.
  After-success: end-of-doc reference tables, appendices, changelogs, and any
  hands-on/quickstart tail (validation gets delegated) — findings there cap at
  low unless they block one of the four items above.
