"""Build deterministic DuckDB table pairs and their expected results."""

import argparse
import json
from pathlib import Path

import duckdb

ROW_COUNT = 1_000
DATA = Path(__file__).resolve().parent / "data"
EXPECTED = Path(__file__).resolve().parent / "expected"

AFTER_QUERIES = {
    "identical": "SELECT * FROM {before}",
    "value_changes": """
        SELECT * REPLACE (amount + CASE WHEN id % 100 = 0 THEN 1 ELSE 0 END AS amount)
        FROM {before}
    """,
    "additions_removals": """
        SELECT * FROM {before} WHERE id > 10
        UNION ALL
        SELECT * REPLACE (id + {rows} AS id) FROM {before} WHERE id <= 20
    """,
    "null_flips": """
        SELECT * REPLACE (
            CASE WHEN id <= 20 AND note IS NULL THEN 'standard'
                 WHEN id <= 20 THEN NULL
                 ELSE note END AS note
        )
        FROM {before}
    """,
    "retyped_column": "SELECT * REPLACE (amount::VARCHAR AS amount) FROM {before}",
    "renamed_column": "SELECT * RENAME (note AS memo) FROM {before}",
    "fanout_join": """
        WITH order_items AS (
            SELECT id FROM {before}
            UNION ALL
            SELECT id FROM {before} WHERE id % 100 = 0
        )
        SELECT orders.* FROM {before} AS orders JOIN order_items USING (id)
    """,
    "currency_unit": """
        SELECT * REPLACE (
            CASE WHEN segment = 'partner' THEN amount * 100 ELSE amount END AS amount
        )
        FROM {before}
    """,
}


def build_scenario(
    con: duckdb.DuckDBPyConnection, scenario: str, rows: int = ROW_COUNT
) -> tuple[str, str]:
    after_query = AFTER_QUERIES[scenario]
    before = f"{scenario}.before_rows"
    after = f"{scenario}.after_rows"
    con.execute(f"CREATE SCHEMA IF NOT EXISTS {scenario}")
    con.execute(
        f"""
        CREATE OR REPLACE TABLE {before} AS
        SELECT i::INTEGER AS id,
               (100 + 10 * (i % 5))::INTEGER AS amount,
               CASE WHEN i % 100 = 0 THEN 'partner' ELSE 'direct' END AS segment,
               CASE WHEN i % 2 = 0 THEN 'standard' END AS note
        FROM range(1, ?) AS ids(i)
        """,
        [rows + 1],
    )
    con.execute(f"CREATE OR REPLACE TABLE {after} AS " + after_query.format(before=before, rows=rows))
    return before, after


def expected_counts(
    *,
    added=0,
    removed=0,
    changed=0,
    column_changes=None,
    added_columns=(),
    removed_columns=(),
    type_changes=None,
    numeric_shifts=None,
):
    return {
        "before_rows": ROW_COUNT,
        "after_rows": ROW_COUNT + added - removed,
        "added_rows": added,
        "removed_rows": removed,
        "changed_rows": changed,
        "unchanged_rows": ROW_COUNT - removed - changed,
        "schema": {
            "added_columns": list(added_columns),
            "removed_columns": list(removed_columns),
            "type_changes": type_changes or {},
        },
        "column_changes": column_changes or {},
        "numeric_shifts": numeric_shifts or {},
    }


EXPECTED_RESULTS = {
    "identical": expected_counts(),
    "value_changes": expected_counts(
        changed=10,
        column_changes={"amount": {"changed_rows": 10, "null_to_value": 0, "value_to_null": 0}},
    ),
    "additions_removals": expected_counts(
        added=20,
        removed=10,
        numeric_shifts={"amount": {"before_sum": 120_000, "after_sum": 121_200}},
    ),
    "null_flips": expected_counts(
        changed=20,
        column_changes={"note": {"changed_rows": 20, "null_to_value": 10, "value_to_null": 10}},
    ),
    "retyped_column": expected_counts(type_changes={"amount": ["INTEGER", "VARCHAR"]}),
    "renamed_column": expected_counts(added_columns=["memo"], removed_columns=["note"]),
    "fanout_join": {
        "before_rows": 1_000,
        "after_rows": 1_010,
        "error": "KeyNotUniqueError",
        "duplicate_keys": list(range(100, 1_001, 100)),
        "duplicate_key_count": 10,
        "example_count": 3,
    },
    "currency_unit": expected_counts(
        changed=10,
        column_changes={"amount": {"changed_rows": 10, "null_to_value": 0, "value_to_null": 0}},
        numeric_shifts={
            "amount": {
                "before_sum": 120_000,
                "after_sum": 219_000,
                "before_mean": 120,
                "after_mean": 219,
                "before_median": 120,
                "after_median": 120,
                "before_p95": 140,
                "after_p95": 140,
            },
        },
    ),
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scenario", nargs="?", choices=AFTER_QUERIES)
    args = parser.parse_args()
    scenarios = [args.scenario] if args.scenario else AFTER_QUERIES

    DATA.mkdir(exist_ok=True)
    EXPECTED.mkdir(exist_ok=True)
    with duckdb.connect(str(DATA / "scenarios.duckdb"), config={"memory_limit": "4GB"}) as con:
        for scenario in scenarios:
            build_scenario(con, scenario)
            (EXPECTED / f"{scenario}.json").write_text(
                json.dumps(EXPECTED_RESULTS[scenario], indent=2) + "\n", encoding="utf-8"
            )


if __name__ == "__main__":
    main()
