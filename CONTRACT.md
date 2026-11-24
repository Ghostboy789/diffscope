# diffscope: module contract

diffscope compares two versions of a table and explains, in plain English, what changed:
rows added, removed and changed, changes per column, and shifts in numeric distributions.
Its first home is a pull-request comment for dbt projects.

Every module builds against this file. Change it only by agreement.

## Package layout

| Path | Owner branch | What it does |
|---|---|---|
| `diffscope/result.py` | main (fixed) | The `DiffResult` data model and its JSON round-trip |
| `diffscope/engine.py` | `engine` | `diff_tables(...)` computes a `DiffResult` with DuckDB |
| `diffscope/report.py` | `report` | `render_markdown(result, ...)` turns a `DiffResult` into a PR comment |
| `diffscope/cli.py`, `diffscope/dbt.py`, `action.yml` | `integrations` | The command line, dbt integration and GitHub Action |
| `bench/`, `examples/`, `tests/test_scenarios.py` | `testbed` | Synthetic scenarios with known answers, benchmarks, a dbt demo |

Each branch owns only its paths, plus its own `tests/test_<area>.py`.

## `diff_tables`

```python
def diff_tables(
    con: duckdb.DuckDBPyConnection,
    before: str,              # a table name, view name, or a SQL query in parentheses
    after: str,
    keys: list[str],          # columns that identify a row; must be unique in each table
    columns: list[str] | None = None,   # columns to compare; default: all shared non-key columns
    tolerance: float = 0.0,   # absolute tolerance for numeric equality
    sample_rows: int = 5,     # example rows kept per category
) -> DiffResult
```

Rules:
- Fails with `KeyNotUniqueError` (in `result.py`) if a key repeats in either table, reporting how many duplicates and three examples.
- NULL equals NULL for comparison purposes.
- Columns present in only one table are reported in `schema`, never compared.
- A changed type (e.g. INTEGER to VARCHAR) is reported in `schema.type_changes`; values are compared as text.
- All work happens in DuckDB SQL. Python only orchestrates. It must handle 10 million rows per side on a 16 GB machine.

## `render_markdown`

```python
def render_markdown(result: DiffResult, max_rows: int = 10, title: str | None = None) -> str
```

The comment must lead with a one-line verdict in plain English, then counts, then the columns that changed most, then numeric shifts, then example rows in collapsible `<details>` blocks. Nothing in it may be invented: every number comes from the `DiffResult`.

## The data model

See `diffscope/result.py` for the exact fields. A complete example lives in
`tests/fixtures/example_result.json`, built from a known scenario, for modules that need a
`DiffResult` before the engine exists.
