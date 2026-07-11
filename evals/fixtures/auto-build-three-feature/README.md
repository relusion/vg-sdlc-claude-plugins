# auto-build-three-feature fixture

A small, pre-planned in-memory snippet vault used by **EVAL-017** to exercise
`/ce-auto-build` end-to-end. The plan (`docs/plans/snippet-vault/`) decomposes into three
features, each engineered to drive one terminal path of an auto-build run:

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

## Notes for the live run (WS3-T13)

This fixture is **dry-run verifiable** today: `eval_check.py` validates the scenario and
fixture structure without a model call. The live run (`eval_run.py --execute`, scoped to
EVAL-017) is WS3-T13 and needs an API key. EVAL-017's prompt pre-answers every Stage-0
kickoff knob inline (sequential, advisory review, diagnose on, isolated branch, explicit
budget/caps) because a headless `-p` run cannot answer interactive HITL gates. The seeded
conditions above force the non-clean paths; T13 records which exact terminal states and
diagnosis classes land and freezes them as `evals/golden/EVAL-017/`.
