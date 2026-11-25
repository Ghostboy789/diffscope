# diffscope

diffscope shows what changed in your data when you change a SQL or dbt model. It compares the two built versions and posts a comment on the pull request with added, removed, and changed rows, shifts in numeric columns, schema changes, and example values. Reviewers can see the effect of a query change before it merges.

## What the comment looks like

This is the original PR #1 comment. The current format leads with key type changes and the strongest numeric signal, and shows when details are omitted. [PR #1](https://github.com/Ghostboy789/diffscope/pull/1)

The demo shows an intended status rename on order `101` and a currency-unit bug on order `103`. The bug changes the order from 760 to 76,000 cents and also raises the affected customer's total. These are exact values from the synthetic [Jaffle Shop demo](examples/jaffle_demo/).

**`orders`** — 2 rows changed and the sum of `amount_cents` rose 1,361.8% (5,525.0 to 80,765.0).

| Rows | Count |
| --- | --- |
| Before | 8 |
| After | 8 |
| Added | 0 |
| Removed | 0 |
| Changed | 2 |
| Unchanged | 6 |

### Most changed columns

| Column | Changed rows | NULL to value | Value to NULL |
| --- | --- | --- | --- |
| `status` | 1 | 0 | 0 |
| `amount_cents` | 1 | 0 | 0 |

### Numeric shifts

| Column | Statistic | Before | After | Change | Change (%) |
| --- | --- | --- | --- | --- | --- |
| `amount_cents` | Mean | 690.62 | 10,095.62 | +9,405.0 | +1,361.81% |
| `amount_cents` | P95 | 1,045.0 | 49,802.5 | +48,757.5 | +4,665.79% |
| `amount_cents` | Sum | 5,525.0 | 80,765.0 | +75,240.0 | +1,361.81% |

### Example rows

<details>
<summary>Changed rows</summary>

| `order_id` | `column` | `before` | `after` |
| --- | --- | --- | --- |
| 101 | `status` | complete | completed |
| 103 | `amount_cents` | 760 | 76,000 |

</details>

---

**`customers`** — 1 row changed and the sum of `total_amount_cents` rose 1,361.8% (5,525.0 to 80,765.0).

| Rows | Count |
| --- | --- |
| Before | 4 |
| After | 4 |
| Added | 0 |
| Removed | 0 |
| Changed | 1 |
| Unchanged | 3 |

### Most changed columns

| Column | Changed rows | NULL to value | Value to NULL |
| --- | --- | --- | --- |
| `total_amount_cents` | 1 | 0 | 0 |

### Numeric shifts

| Column | Statistic | Before | After | Change | Change (%) |
| --- | --- | --- | --- | --- | --- |
| `total_amount_cents` | Mean | 1,381.25 | 20,191.25 | +18,810.0 | +1,361.81% |
| `total_amount_cents` | Median | 1,637.5 | 2,137.5 | +500.0 | +30.53% |
| `total_amount_cents` | P95 | 2,216.25 | 65,354.0 | +63,137.75 | +2,848.86% |
| `total_amount_cents` | Sum | 5,525.0 | 80,765.0 | +75,240.0 | +1,361.81% |

### Example rows

<details>
<summary>Changed rows</summary>

| `customer_id` | `column` | `before` | `after` |
| --- | --- | --- | --- |
| 2 | `total_amount_cents` | 1,250 | 76,490 |

</details>

<details>
<summary>The same comment as raw Markdown</summary>

````markdown
**`orders`** — 2 rows changed and the sum of `amount_cents` rose 1,361.8% (5,525.0 to 80,765.0).

| Rows | Count |
| --- | --- |
| Before | 8 |
| After | 8 |
| Added | 0 |
| Removed | 0 |
| Changed | 2 |
| Unchanged | 6 |

### Most changed columns

| Column | Changed rows | NULL to value | Value to NULL |
| --- | --- | --- | --- |
| `status` | 1 | 0 | 0 |
| `amount_cents` | 1 | 0 | 0 |

### Numeric shifts

| Column | Statistic | Before | After | Change | Change (%) |
| --- | --- | --- | --- | --- | --- |
| `amount_cents` | Mean | 690.62 | 10,095.62 | +9,405.0 | +1,361.81% |
| `amount_cents` | P95 | 1,045.0 | 49,802.5 | +48,757.5 | +4,665.79% |
| `amount_cents` | Sum | 5,525.0 | 80,765.0 | +75,240.0 | +1,361.81% |

### Example rows

<details>
<summary>Changed rows</summary>

| `order_id` | `column` | `before` | `after` |
| --- | --- | --- | --- |
| 101 | `status` | complete | completed |
| 103 | `amount_cents` | 760 | 76,000 |

</details>

---

**`customers`** — 1 row changed and the sum of `total_amount_cents` rose 1,361.8% (5,525.0 to 80,765.0).

| Rows | Count |
| --- | --- |
| Before | 4 |
| After | 4 |
| Added | 0 |
| Removed | 0 |
| Changed | 1 |
| Unchanged | 3 |

### Most changed columns

| Column | Changed rows | NULL to value | Value to NULL |
| --- | --- | --- | --- |
| `total_amount_cents` | 1 | 0 | 0 |

### Numeric shifts

| Column | Statistic | Before | After | Change | Change (%) |
| --- | --- | --- | --- | --- | --- |
| `total_amount_cents` | Mean | 1,381.25 | 20,191.25 | +18,810.0 | +1,361.81% |
| `total_amount_cents` | Median | 1,637.5 | 2,137.5 | +500.0 | +30.53% |
| `total_amount_cents` | P95 | 2,216.25 | 65,354.0 | +63,137.75 | +2,848.86% |
| `total_amount_cents` | Sum | 5,525.0 | 80,765.0 | +75,240.0 | +1,361.81% |

### Example rows

<details>
<summary>Changed rows</summary>

| `customer_id` | `column` | `before` | `after` |
| --- | --- | --- | --- |
| 2 | `total_amount_cents` | 1,250 | 76,490 |

</details>
````

</details>

## Quick start

From the repository root, install with `python -m pip install .` using Python 3.10 or newer.

### Compare tables or files

```sh
diffscope tables baseline.orders candidate.orders --db shop.duckdb --key order_id
diffscope tables before.csv after.parquet --key order_id
```

Files can be CSV or Parquet. Repeat `--key` for a composite key. Use `--format json` for machine-readable output.

### Compare built dbt models

From the repository root, build the demo's two targets in the same DuckDB file and compare them.

```sh
python -m pip install 'dbt-duckdb>=1.11,<1.12' 'dbt-core>=1.11,<1.12'
bash examples/jaffle_demo/build.sh
diffscope dbt --project-dir examples/jaffle_demo --models orders customers \
  --base-schema baseline --target-schema candidate
```

The command reads `meta.diffscope_keys` from the dbt manifest. Use `--key` to override the manifest keys. Use `--db` to choose the target DuckDB file and `--base-db` if the base models are built in a separate local DuckDB file. Both files open read-only. If a relation is missing, diffscope names the model and the side to build.

For CI, use `--max-affected-rows N` with either command. diffscope writes the report and exits with code `3` when added, removed, and changed rows together exceed `N` in any one comparison. Schema and numeric summaries are reported independently of the gate. A completed comparison within the limit exits with `0`. Comparison errors use `1`, and invalid arguments use `2`.

Both commands accept `--tolerance`, `--sample-rows`, `--memory-limit`, and `--format json`. Use `--sample-rows 0` to skip examples. The default DuckDB memory limit is 4 GB. dbt JSON returns a `models` array with a `model` name and a `diff` result for each requested model.

### Post to a pull request

In a `pull_request` workflow, grant comment permission and group runs by pull request.

```yaml
permissions:
  contents: read
  pull-requests: write
concurrency:
  group: diffscope-${{ github.event.pull_request.number }}
  cancel-in-progress: true
```

After checkout, Python setup, and the build of both dbt schemas, add the comparison step. The action uses `gh` to create or update one comment. The [demo workflow](.github/workflows/demo.yml) runs the action from this checkout with `uses: ./` and skips the comment step on fork pull requests, where GitHub provides a read-only token.

```yaml
- uses: Ghostboy789/diffscope@main
  with:
    project-dir: examples/jaffle_demo
    models: orders customers
    base-schema: baseline
    target-schema: candidate
```

For separate local snapshots, set the action's `base-db` and `db` inputs. The Markdown report limits long tables and shows how much was omitted. If a combined dbt report exceeds 60,000 UTF-8 bytes, it shows model verdicts with an omission notice. JSON retains the underlying counts and column details.

## How it works

- DuckDB checks that the key columns uniquely identify rows on each side, then joins the two versions with a full outer join. Keys found on only one side identify added or removed rows.
- Matching is null-safe. Two `NULL`s are equal, and a `NULL` paired with a value is a change. Text keys match by exact UTF-8 value so a collation on one side cannot create extra matches. Both commands accept a finite, nonnegative absolute `--tolerance` for same-type numeric columns. The default is zero.
- Identifiers follow DuckDB's ASCII case rules and preserve whitespace. The diff lists added, removed, and retyped columns. Retyped values are compared as text, and retyped keys are checked for collisions after the text cast. Numeric summaries use the full version on each side, including added and removed rows.
- The checks, joins, counts, and summaries run in DuckDB SQL. Python runs the queries and formats the result.

## Benchmark

DuckDB 2.0.1 on Darwin arm64 with a 4 GB DuckDB memory limit. Each duration is a single wall-clock observation and excludes table creation. A confidence interval requires repeated runs. [Benchmark results](bench/results.md)

| Rows per side | Changed rows | Wall-clock seconds |
| ---: | ---: | ---: |
| 100,000 | 1,000 | 0.023 |
| 1,000,000 | 10,000 | 0.071 |
| 10,000,000 | 100,000 | 0.541 |

## Tests with known answers

Each scenario starts with 1,000 synthetic rows. The counts and aggregate values are properties of those tables, so they have no sampling uncertainty. [Scenario fixtures and verification plan](bench/README.md)

| Scenario | Expected result | What it checks |
| --- | --- | --- |
| `identical` | 1,000 unchanged rows | Equal values, including two `NULL`s, stay unchanged. |
| `value_changes` | 10 changed rows, all in `amount` | Changes are counted at the row and column level. |
| `additions_removals` | 20 added, 10 removed, 0 changed | Rows are matched by key, and the sum reflects rows added or removed. |
| `null_flips` | 20 changed, with 10 flips in each direction | `NULL` to value and value to `NULL` are counted separately. |
| `retyped_column` | `amount` changes from `INTEGER` to `VARCHAR`, with 0 changed rows | A type change is reported even when the text values match. |
| `renamed_column` | `memo` added, `note` removed, 0 changed rows | A rename appears as an added column and a removed column. |
| `fanout_join` | 10 duplicate keys, with 3 examples in the error | A join fanout fails the uniqueness check before comparison. |
| `currency_unit` | 10 changed rows, sum rises from 120,000 to 219,000, mean rises from 120 to 219 | A unit error shifts the sum and mean even when the median and P95 stay fixed. |

## Limits

- The dbt integration currently supports the DuckDB adapter only.
- The key or key combination must be unique in each version.
- Both versions of each dbt model must be built before comparison.
- The dbt command can compare two local DuckDB files. For other engines, export each version to CSV or Parquet and use the `tables` command.
- Views and SQL queries should return stable rows throughout a comparison. Wide diffs can be more expensive with samples enabled.

Datafold archived its widely used open-source table comparison tool in May 2024. [datafold/data-diff archive](https://github.com/datafold/data-diff)

**Author** Medhansh Shekhawat · [GitHub](https://github.com/Ghostboy789) · [LinkedIn](https://www.linkedin.com/in/medhansh-shekhawat)
