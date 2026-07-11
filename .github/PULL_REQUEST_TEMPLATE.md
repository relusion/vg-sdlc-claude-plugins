## What & why

<!-- One paragraph. Link the issue if there is one. -->

## Checklist

- [ ] `python3 scripts/check.py` green (runs corpus, authoring, supply-chain,
      managed-agent, and product-layer checks)
- [ ] `python3 -m unittest discover -s tests -q` green
- [ ] `CHANGELOG.md` updated under `## Unreleased` (user-visible plugin changes)
- [ ] Every commit includes the DCO `Signed-off-by:` trailer (`git commit -s`)
- [ ] `docs/HOW-IT-WORKS.md` + `README.md` updated if the framework's shape
      changed (skills, gates, controls, product routes, artifact paths)
- [ ] Version bump left to the pre-commit hook / `version_bump.py` (don't
      hand-edit unless cutting a deliberate minor/major)

See [CONTRIBUTING.md](../CONTRIBUTING.md) for the full battery and standards.
