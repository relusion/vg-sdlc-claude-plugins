# Documentation

Start with the page that matches the job. The default workflow is adaptive; a
brief, architecture package, explicit specification, and documentation audit
are conditional rather than mandatory stages.

## Use the plugins

- [Getting Started](GETTING-STARTED.md) — install the marketplace and get a
  useful result in the first session.
- [Usage Matrix](USAGE-MATRIX.md) — choose the right `/ce-*` skill for the job.
- [Workflow Recipes](WORKFLOW-RECIPES.md) — follow one concise outcome path
  with its artifacts and stop conditions.
- [How It Works](HOW-IT-WORKS.md) — understand the architecture, artifacts,
  gates, and safety model.
- [Compatibility and Upgrades](COMPATIBILITY.md) — check the supported runtime
  floor and team-safe update sequence.
- [Real Outputs](EXAMPLES.md) — inspect captured examples with provenance.

If you are unsure where to begin, use [Getting Started](GETTING-STARTED.md). If
you only need to choose a command, use the [Usage Matrix](USAGE-MATRIX.md).

## Evaluate or adopt the project

- [Benchmarks and Evaluation Budgets](BENCHMARKS.md) — current eval evidence,
  deterministic validation coverage, configured budget caps, and known gaps.
- [Choosing a Spec-Driven Toolchain](COMPARISON.md) — dated comparison with
  alternative approaches.
- [Team Rollout](TEAM-ROLLOUT.md) — pilot, branch-protection, measurement, and
  rollback guidance.
- [Enterprise Hardening](ENTERPRISE-HARDENING.md) — controls, evidence,
  attestations, and remaining gaps.

Behavior-evaluation setup and the human grading rubric live with the corpus in
[evals/README.md](../evals/README.md).

## Project policies

- [License](../LICENSE) — Apache License 2.0 terms.
- [Third-party notices](../THIRD_PARTY_NOTICES.md) — attribution and license
  terms for incorporated data.
- [Licensing and commercial boundary](../COMMERCIAL.md) — explanatory project
  policy; it does not replace the license.
- [Security policy](../SECURITY.md) — supported versions and private reporting.
- [Contributing](../CONTRIBUTING.md) — validation, DCO sign-off, and pull-request
  expectations.

## Contribute

Repository-wide setup and validation commands are in
[CONTRIBUTING.md](../CONTRIBUTING.md). Skill authors also need:

- [Skill Authoring Standard](contributing/SKILL-AUTHORING.md)
- [Human-in-the-Loop Gate Standard](contributing/HITL-GATE-STANDARD.md)

The JSON files in this directory are validation inputs, not additional reading.
`examples-manifest.json` binds published examples to replay commands.
