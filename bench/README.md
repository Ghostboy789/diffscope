# Testbed verification plan

## Scenarios

Build each pair from 1,000 rows keyed by `id`. Check the result against exact counts
written under `expected/`. Counts are properties of the generated tables and have no
sampling uncertainty.

| Scenario | Added | Removed | Changed | Unchanged | Other checks |
| --- | ---: | ---: | ---: | ---: | --- |
| `identical` | 0 | 0 | 0 | 1,000 | No schema or value changes, including where both values are NULL. |
| `value_changes` | 0 | 0 | 10 | 990 | Only `amount` changes. |
| `additions_removals` | 20 | 10 | 0 | 990 | Added and removed rows contribute to the numeric summaries. |
| `null_flips` | 0 | 0 | 20 | 980 | `note` changes, with 10 flips in each direction. |
| `retyped_column` | 0 | 0 | 0 | 1,000 | `amount` changes from `INTEGER` to `VARCHAR`, with equal text values. |
| `renamed_column` | 0 | 0 | 0 | 1,000 | `memo` is added and `note` is removed. |
| `fanout_join` | | | | | The after table repeats 10 keys. Require `KeyNotUniqueError` with the count and three example keys. |
| `currency_unit` | 0 | 0 | 10 | 990 | Only `amount` changes. Check the exact sum and mean and unchanged median and p95. |

Use `../diffscope/.venv/bin/python -m bench.make_scenarios` from the repository root to
build the tables and regenerate the expected JSON files. Use
`../diffscope/.venv/bin/python -m pytest -q` to check the engine results. The engine
checks skip when the module or its implementation is missing.

## Benchmark

Run one timed comparison for each of 100,000, 1,000,000 and 10,000,000 rows per side
using the 1% value-change scenario and a 4 GB DuckDB memory limit. Exclude data creation
from the timing. A run passes if the row counts and change counts match at every size.
Report each wall-clock measurement as one observation, without a confidence interval.
Write results to `results.md` and record a skip if the engine is unavailable.

Run from the repository root with `../diffscope/.venv/bin/python -m bench.bench`.

## dbt demo

Run `dbt build` for both targets and confirm that both schemas contain `orders` and
`customers`. The only order differences should be one intended status update and one
unintended 100× amount increase. The affected customer's total should reflect the
amount error. Run `ruff check .` and the full pytest suite before finishing.
