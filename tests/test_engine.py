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


def test_retyped_key_collisions_are_rejected_before_join(con):
    old = """(SELECT union_value(a := 1)::UNION(a INTEGER, b VARCHAR) AS id
              UNION ALL SELECT union_value(b := '1')::UNION(a INTEGER, b VARCHAR))"""
    new = "(SELECT '1' AS id)"

    with pytest.raises(KeyNotUniqueError, match="1 duplicate key, 1 excess row after casting"):
        diff_tables(con, old, new, ["id"])


def test_retyped_composite_keys_still_match_as_text(con):
    old = "(SELECT * FROM (VALUES (1, NULL, 10), (2, 0, 20)) t(id, region, value))"
    new = "(SELECT * FROM (VALUES ('1', NULL, 15), ('02', 0, 20)) t(id, region, value))"

    result = diff_tables(con, old, new, ["id", "region"])

    assert result.schema.type_changes == {"id": ["INTEGER", "VARCHAR"]}
    assert (result.added_rows, result.removed_rows, result.changed_rows) == (1, 1, 1)
    assert result.samples["changed"] == [
        {"id": 1, "region": None, "column": "value", "before": 10, "after": 15}
    ]


def test_identifiers_fold_ascii_case_but_keep_spaces_and_unicode(con):
    old = '(SELECT 1 AS " ID ", 10 AS "Amount ", 1 AS "Å", 7 AS "_DIFFSCOPE_PRESENT")'
    new = '(SELECT 1 AS " id ", 11 AS "amount ", 1 AS "å", 7 AS "_diffscope_present")'

    result = diff_tables(con, old, new, [" Id "], ["AMOUNT ", "amount ", "Å"])

    assert result.keys == [" ID "]
    assert result.schema == SchemaDiff(added_columns=["å"], removed_columns=["Å"])
    assert result.column_changes == [ColumnChange("Amount ", 1, 0, 0)]
    assert result.samples["changed"] == [
        {" ID ": 1, "column": "Amount ", "before": 10, "after": 11}
    ]


@pytest.mark.parametrize(("keys", "columns", "tolerance", "message"), [
    ([], None, 0, "at least one key"),
    ([" id "], None, 0, "present in both tables"),
    (["id", "ID"], None, 0, "only be specified once"),
    (["id"], ["amunt"], 0, "Unknown comparison columns: amunt"),
    (["id"], None, float("inf"), "finite and nonnegative"),
    (["id"], None, -1, "finite and nonnegative"),
])
def test_invalid_selections(con, keys, columns, tolerance, message):
    with pytest.raises(ValueError, match=message):
        source = "(SELECT 1 AS id, 2 AS amount)"
        diff_tables(con, source, source, keys, columns, tolerance)


@pytest.mark.parametrize("kind", ["UBIGINT", "HUGEINT", "UHUGEINT", "BIGNUM"])
def test_integer_tolerance_does_not_round_large_gaps(con, kind):
    old = f"(SELECT 1 AS id, 1::{kind} AS amount)"
    new = f"(SELECT 1 AS id, 9007199254740994::{kind} AS amount)"

    assert diff_tables(con, old, new, ["id"], tolerance=2**53).changed_rows == 1
    assert diff_tables(con, old, new, ["id"], tolerance=2**53 + 1).unchanged_rows == 1
    assert diff_tables(con, new, old, ["id"], tolerance=2**53).changed_rows == 1


def test_empty_tables_and_nonfinite_float_changes(con):
    old = """(SELECT * FROM (VALUES (1, 'NaN'::DOUBLE), (2, 'Infinity'::DOUBLE),
        (3, '-Infinity'::DOUBLE), (4, 2::DOUBLE), (5, 1::DOUBLE)) t(id, value))"""
    new = """(SELECT * FROM (VALUES (1, 'NaN'::DOUBLE), (2, 'Infinity'::DOUBLE),
        (3, 0::DOUBLE), (4, 'NaN'::DOUBLE), (5, 1.1::DOUBLE)) t(id, value))"""

    assert diff_tables(con, old, new, ["id"], tolerance=0.2).changed_rows == 2
    empty = f"(SELECT * FROM {old} WHERE FALSE)"
    result = diff_tables(con, empty, empty, ["id"])
    assert (result.before_rows, result.after_rows, result.unchanged_rows) == (0, 0, 0)
    assert result.numeric_shifts == [NumericShift("value", *([None] * 8))]


def test_nanosecond_timestamp_examples_keep_the_changed_digits(con):
    old = "(SELECT 1 AS id, '2025-01-01 00:00:00.000000001'::TIMESTAMP_NS AS stamp)"
    new = "(SELECT 1 AS id, '2025-01-01 00:00:00.000000002'::TIMESTAMP_NS AS stamp)"

    result = diff_tables(con, old, new, ["id"])

    assert result.samples["changed"] == [{
        "id": 1, "column": "stamp", "before": "2025-01-01 00:00:00.000000001",
        "after": "2025-01-01 00:00:00.000000002",
    }]


def test_text_key_collation_cannot_turn_two_keys_into_one_join_match(con):
    old = "(SELECT * FROM (VALUES ('a'), ('A')) t(id))"
    new = "(SELECT 'a' COLLATE NOCASE AS id)"

    result = diff_tables(con, old, new, ["id"])

    assert (result.before_rows, result.after_rows) == (2, 1)
    assert (result.removed_rows, result.added_rows, result.unchanged_rows) == (1, 0, 1)
    assert result.samples["removed"] == [{"id": "A"}]


def test_native_integer_quantiles_keep_interpolation(con):
    source = "(SELECT * FROM (VALUES (1, -1::SMALLINT), (2, 0::SMALLINT)) t(id, amount))"

    stats = diff_tables(con, source, source, ["id"]).numeric_shifts[0]

    assert (stats.before_median, stats.before_p95) == pytest.approx((-0.5, -0.05))


def test_wide_comparison_can_sample_a_change_in_the_last_column(con):
    for name, last in (("before_wide", "old"), ("after_wide", "new")):
        fields = [f"'old' AS c{i}" for i in range(127)] + [f"'{last}' AS c127"]
        con.execute(f"CREATE TABLE {name} AS SELECT 1 AS id, {', '.join(fields)}")

    result = diff_tables(con, "before_wide", "after_wide", ["id"])

    assert result.changed_rows == 1
    assert len(result.column_changes) == 128
    assert result.column_changes[0] == ColumnChange("c127", 1, 0, 0)
    assert result.samples["changed"] == [{"id": 1, "column": "c127", "before": "old", "after": "new"}]
