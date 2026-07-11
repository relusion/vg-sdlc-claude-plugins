# Shared Context — snippet-vault

## Codebase Profile

- **Language / runtime:** Python 3 (standard library only; no third-party deps).
- **Core module:** `snippets.py` — an in-memory `Store` of `Snippet` records plus
  validation constants (`MAX_BODY`, `ALLOWED_LANGUAGES`) and the `list_snippets` reader.
  Features extend this one module; there is no database.
- **Entry point:** `app.py` (a smoke target for integration verify).
- **Tests:** `checks/` holds pytest files. `checks/snippets_check.py` is the green
  baseline; `checks/export_check.py` is a dormant acceptance test that activates only
  once `export_csv` exists (see `features/03-export-snippets.md`).

## Build / Test / Lint

Test files use the `checks/*_check.py` convention (functions are `test_*`), so pytest is
told to collect them with `-o python_files="*_check.py"`.

| Command | Purpose |
|---|---|
| `python3 -m pytest checks/ -q -o python_files="*_check.py"` | Run the whole test suite (all features). |
| `python3 -m pytest checks/export_check.py -q` | Run 03's acceptance test in isolation (explicit file path needs no override). |
| `python3 -c "import ast,glob; [ast.parse(open(f).read()) for f in glob.glob('**/*.py', recursive=True)]"` | Lint floor (parse every module). |
| `python3 app.py` | Integration smoke — prints the store size. |

There is no separate lint tool configured; the parse-floor above stands in.

## Known Pitfalls

- `checks/export_check.py` asserts a **deliberately unsatisfiable** golden — do not
  weaken or delete it. It exists to exercise the retry-exhaustion path; the fix is not
  to touch the test but to record the failure (see 03's feature file).

## Resolved Project Decisions

- Storage is **in-memory only** for this plan — no persistence, no schema, no migrations.
- Validation lives in `snippets.py`; every feature reuses `ALLOWED_LANGUAGES` and `MAX_BODY`.
