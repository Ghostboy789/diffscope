import duckdb
import pytest

from diffscope.engine import diff_tables
from diffscope.result import ColumnChange, KeyNotUniqueError, NumericShift, SchemaDiff


@pytest.fixture
def con():
    with duckdb.connect() as connection:
        yield connection


def test_identical_tables(con):
    con.execute("CREATE TABLE old AS SELECT * FROM (VALUES (1, 10), (2, 20)) t(id, amount)")
    con.execute("CREATE VIEW new AS SELECT * FROM old")

    result = diff_tables(con, "old", "new", ["id"])

    assert (result.before_name, result.after_name, result.keys) == ("old", "new", ["id"])
    assert (result.before_rows, result.after_rows) == (2, 2)
    assert (result.added_rows, result.removed_rows, result.changed_rows, result.unchanged_rows) == (
        0, 0, 0, 2
    )
    assert result.schema == SchemaDiff()
    assert result.column_changes == [ColumnChange("amount", 0, 0, 0)]
    assert result.numeric_shifts == [NumericShift("amount", 15, 15, 15, 15, 19.5, 19.5, 30, 30)]
    assert result.samples == {"added": [], "removed": [], "changed": []}
    assert result.elapsed_seconds >= 0


def test_only_additions(con):
    con.execute("CREATE TABLE old AS SELECT 2 AS id, 20 AS amount")
    con.execute("CREATE TABLE new AS SELECT * FROM (VALUES (3, 30), (2, 20), (1, 10)) t(id, amount)")

    result = diff_tables(con, "old", "new", ["id"], sample_rows=1)

    assert (result.before_rows, result.after_rows) == (1, 3)
    assert (result.added_rows, result.removed_rows, result.changed_rows, result.unchanged_rows) == (
        2, 0, 0, 1
    )
    assert result.numeric_shifts == [NumericShift("amount", 20, 20, 20, 20, 20, 29, 20, 60)]
    assert result.samples == {"added": [{"id": 1, "amount": 10}], "removed": [], "changed": []}


def test_only_removals(con):
    con.execute("CREATE TABLE old AS SELECT * FROM (VALUES (3, 30), (1, 10)) t(id, amount)")
    con.execute("CREATE TABLE new AS SELECT * FROM old WHERE FALSE")

    result = diff_tables(con, "old", "new", ["id"])

    assert (result.before_rows, result.after_rows) == (2, 0)
    assert (result.added_rows, result.removed_rows, result.changed_rows, result.unchanged_rows) == (
        0, 2, 0, 0
    )
    assert result.numeric_shifts == [NumericShift("amount", 20, None, 20, None, 29, None, 40, None)]
    assert result.samples == {
        "added": [], "removed": [{"id": 1, "amount": 10}, {"id": 3, "amount": 30}], "changed": []
    }


def test_changed_values_and_null_transitions(con):
    old = "(SELECT * FROM (VALUES (3, 10, 'a'), (2, 20, 'a'), (1, NULL, 'a'), (4, NULL, 'b')) "
    old += "t(id, amount, status))"
    new = "(SELECT * FROM (VALUES (4, NULL, 'b'), (3, 11, 'b'), (2, NULL, 'a'), (1, 30, 'a')) "
    new += "t(id, amount, status))"

    result = diff_tables(con, old, new, ["id"], sample_rows=2)

    assert (result.added_rows, result.removed_rows, result.changed_rows, result.unchanged_rows) == (
        0, 0, 3, 1
    )
    assert result.column_changes == [ColumnChange("amount", 3, 1, 1), ColumnChange("status", 1, 0, 0)]
    assert result.samples["changed"] == [
        {"id": 1, "column": "amount", "before": None, "after": 30},
        {"id": 2, "column": "amount", "before": 20, "after": None},
    ]


def test_tolerance_and_selected_columns(con):
    old = "(SELECT * FROM (VALUES (1, 10.00, 1), (2, 10.00, 2), (3, NULL, 3)) t(id, amount, qty))"
    new = "(SELECT * FROM (VALUES (1, 10.50, 4), (2, 10.51, 2), (3, 0.00, 3)) t(id, amount, qty))"

    result = diff_tables(con, old, new, ["id"], ["amount"], tolerance=0.5, sample_rows=0)

    assert (result.changed_rows, result.unchanged_rows) == (2, 1)
    assert result.column_changes == [ColumnChange("amount", 2, 1, 0)]
    assert [shift.column for shift in result.numeric_shifts] == ["amount"]
    assert result.samples == {"added": [], "removed": [], "changed": []}


def test_tolerance_preserves_bigint_gaps(con):
    old = "(SELECT 1 AS id, 9007199254740992::BIGINT AS amount)"
    new = "(SELECT 1 AS id, 9007199254740993::BIGINT AS amount)"

    assert diff_tables(con, old, new, ["id"], tolerance=0.5).changed_rows == 1
    assert diff_tables(con, old, new, ["id"], tolerance=1).unchanged_rows == 1


@pytest.mark.parametrize("precision", [18, 38])
def test_decimal_totals_preserve_cents(con, precision):
    source = (
        f"(SELECT id, v::DECIMAL({precision}, 2) AS amount "
        "FROM (VALUES (1, '9999999999999999.00'), (2, '-9999999999999998.99')) t(id, v))"
    )

    stats = diff_tables(con, source, source, ["id"]).numeric_shifts[0]

    assert (stats.before_sum, stats.after_sum) == (0.01, 0.01)
    assert (stats.before_mean, stats.after_mean) == (0.005, 0.005)


def test_composite_keys_with_null_and_quoted_column(con):
    old = '(SELECT * FROM (VALUES (1, NULL, 2), (1, 1, 3), (2, 1, 4)) t("group", kind, v))'
    new = '(SELECT * FROM (VALUES (1, NULL, 5), (1, 1, 3), (1, 2, 4)) t("group", kind, v))'

    result = diff_tables(con, old, new, ["group", "kind"])

    assert (result.added_rows, result.removed_rows, result.changed_rows, result.unchanged_rows) == (
        1, 1, 1, 1
    )
    assert result.samples == {
        "added": [{"group": 1, "kind": 2, "v": 4}],
        "removed": [{"group": 2, "kind": 1, "v": 4}],
        "changed": [{"group": 1, "kind": None, "column": "v", "before": 2, "after": 5}],
    }


def test_duplicate_keys_report_counts_and_three_examples(con):
    con.execute(
        "CREATE TABLE old AS SELECT * FROM (VALUES (9), (9), (1), (1), (1), "
        "(4), (4), (2), (2), (NULL), (NULL)) t(id)"
    )
    con.execute("CREATE TABLE new AS SELECT * FROM (VALUES (NULL), (NULL)) t(id)")

    with pytest.raises(KeyNotUniqueError) as error:
        diff_tables(con, "old", "new", ["id"], sample_rows=0)

    detail = str(error.value)
    assert "before (old): 5 duplicate keys, 6 excess rows" in detail
    assert "[{'id': 1}, {'id': 2}, {'id': 4}]" in detail
    assert "after (new): 1 duplicate key, 1 excess row" in detail
    assert "[{'id': None}]" in detail


def test_schema_changes_and_text_comparison(con):
    old = "(SELECT * FROM (VALUES (1, 2, 20, 9), (2, 3, 30, 8)) t(id, status, qty, old_col))"
    new = "(SELECT id, status, qty::BIGINT AS qty, new_col FROM "
    new += "(VALUES (1, '2', 20, 9), (2, '03', 30, 8)) t(id, status, qty, new_col))"

    result = diff_tables(con, old, new, ["id"], ["status", "qty", "old_col", "new_col"])

    assert result.schema == SchemaDiff(
        added_columns=["new_col"],
        removed_columns=["old_col"],
        type_changes={"status": ["INTEGER", "VARCHAR"], "qty": ["INTEGER", "BIGINT"]},
    )
    assert (result.changed_rows, result.unchanged_rows) == (1, 1)
    assert result.column_changes == [ColumnChange("status", 1, 0, 0), ColumnChange("qty", 0, 0, 0)]
    assert result.numeric_shifts == [NumericShift("qty", 25, 25, 25, 25, 29.5, 29.5, 50, 50)]
    assert result.samples["changed"] == [
        {"id": 2, "column": "status", "before": 3, "after": "03"}
    ]


def test_parenthesized_query_and_qualified_table(con):
    con.execute("CREATE SCHEMA shop")
    con.execute('CREATE TABLE shop."order rows" AS SELECT 1 AS id')

    result = diff_tables(con, 'shop."order rows"', "(SELECT 1 AS id UNION ALL SELECT 2)", ["id"])

    assert (result.before_rows, result.after_rows, result.added_rows, result.unchanged_rows) == (1, 2, 1, 1)
    assert result.column_changes == result.numeric_shifts == []
    assert result.samples == {"added": [{"id": 2}], "removed": [], "changed": []}
