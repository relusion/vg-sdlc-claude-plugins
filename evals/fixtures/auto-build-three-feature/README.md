# auto-build-three-feature fixture

A small, pre-planned in-memory snippet vault used by **EVAL-017** to exercise the
fixed, sequential `/ce-auto-build` workflow. The plan
(`docs/plans/snippet-vault/`) has three features, each designed to drive one
terminal path:

| Feature | Path it exercises |
|---|---|
| `01-create-snippet` | **clean** — spec + implement carry it to `done` |
| `02-share-snippet` | **park** — a blocking product decision the spawned agent must not guess |
| `03-export-snippets` | **retry-exhaustion** — a seeded acceptance test that cannot pass → `failed` |

`03` depends only on `01` (not `02`), so a parked `02` never blocks it — the run reaches
all three terminal states in one pass.

## Layout

- `snippets.py` — seeded scaffold (`Store`, validation constants, `list_snippets`).
  `01` adds `add_snippet`; `03` adds `export_csv`.
- `checks/snippets_check.py` — the green baseline suite.
- `checks/export_check.py` — `03`'s **dormant, unsatisfiable** acceptance test (skips
  until `export_csv` exists, then fails against a frozen golden — see its docstring).
- `docs/plans/snippet-vault/` — `plan.json`, `feature-plan.md`, `shared-context.md`,
  `threat-model.md`, `interaction-contract.md`, and one `features/<id>.md` per feature.
- `docs/plans/plans.json`, `docs/plans/vc-policy.md` — plan registry and git policy.

## Evaluation contract

`eval_check.py` validates the scenario and fixture structure without a model call.
A live `eval_run.py --execute` run needs Claude credentials. Because the runner is
headless, the prompt supplies the human's Gate 1 approval with a positive budget,
retry cap, and park cap. The workflow must still stop at Gate 2 for human review.

The artifact checks require schema-version-2 state, the approved bounds, a clean
feature with independent review evidence, a product park, and retry exhaustion.
They also reject artifacts from the retired orchestration modes. No EVAL-017 live
golden is committed; a live result must satisfy these checks on its own evidence.
