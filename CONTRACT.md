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
- Fails before joining with `KeyNotUniqueError` if a key repeats in either table, with counts and up to three examples per side. Retyped keys are also checked after conversion to text.
- NULL equals NULL for comparison purposes. Text key matching uses exact UTF-8 values.
- Column names follow DuckDB's ASCII case rules and retain whitespace. Names shared across versions use the before spelling in summaries. Columns present in just one version appear only in `schema`. Requested names missing from both sides are errors.
- A changed type (e.g. INTEGER to VARCHAR) is reported in `schema.type_changes`. Retyped values are compared as text. The absolute tolerance is finite and nonnegative and applies to same-type numeric comparisons.
- All work happens in DuckDB SQL. Python only orchestrates. It must handle 10 million rows per side on a 16 GB machine.

## `render_markdown`

```python
def render_markdown(result: DiffResult, max_rows: int = 10, title: str | None = None) -> str
```

The comment leads with a plain-English verdict, prioritizing key type changes and numeric shifts. Row counts, schema and numeric changes, changed columns, and collapsible examples follow when available. Display limits include omission counts. Reported figures come from the `DiffResult`.

## The data model

See `diffscope/result.py` for the exact fields. A complete example lives in
`tests/fixtures/example_result.json`. JSON encodes nonfinite floating-point values as
`"NaN"`, `"Infinity"`, and `"-Infinity"`. Nanosecond timestamp samples are strings so
the final three fractional digits remain visible.
