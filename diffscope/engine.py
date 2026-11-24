"""Compare two DuckDB relations by key."""

from time import perf_counter

import duckdb

from diffscope.result import ColumnChange, DiffResult, KeyNotUniqueError, NumericShift, SchemaDiff

_INTEGERS = {
    "TINYINT", "SMALLINT", "INTEGER", "BIGINT", "HUGEINT",
    "UTINYINT", "USMALLINT", "UINTEGER", "UBIGINT", "UHUGEINT", "BIGNUM",
}
_FLOATS = {"FLOAT", "DOUBLE"}


def _identifier(name):
    return '"' + name.replace('"', '""') + '"'


def _fields(alias, names):
    return ", ".join(f"{alias}.{_identifier(name)}" for name in names)


def _record(alias, names):
    fields = ", ".join(f"{_identifier(name)} := {alias}.{_identifier(name)}" for name in names)
    return f"struct_pack({fields})"


def _duplicate_keys(con, source, keys):
    return con.execute(f"""
        SELECT count(*), coalesce(sum(n - 1), 0), arg_min(key_values, key_values, 3)
        FROM (
            SELECT {_record('s', keys)} AS key_values, count(*) AS n
            FROM {source} AS s
            GROUP BY {_fields('s', keys)}
            HAVING count(*) > 1
        )
    """).fetchone()


def _numeric(type_name):
    return type_name in _INTEGERS or type_name in _FLOATS or type_name.startswith("DECIMAL(")


def _difference(left, right, type_name):
    if type_name in {"HUGEINT", "UHUGEINT", "BIGNUM"}:
        return f"{left}::BIGNUM - {right}::BIGNUM"
    if type_name in _INTEGERS:
        return f"{left}::HUGEINT - {right}::HUGEINT"
    if type_name.startswith("DECIMAL(38,"):
        # Subtract like-signed decimals exactly. Opposite signs can exceed DECIMAL(38).
        return (f"CASE WHEN sign({left}) = sign({right}) "
                f"THEN {left} - {right} ELSE {left}::DOUBLE - {right}::DOUBLE END")
    if type_name in _FLOATS:
        return f"{left}::DOUBLE - {right}::DOUBLE"
    return f"{left} - {right}"


def _numeric_stats(con, source, types, columns):
    expressions = []
    for column in columns:
        value = f"s.{_identifier(column)}"
        type_name = types[column]
        if type_name in _FLOATS:
            total = f"fsum({value}::DOUBLE)"
        elif type_name in {"HUGEINT", "UHUGEINT", "BIGNUM"}:
            total = f"sum({value}::BIGNUM)::DOUBLE"
        else:
            total = f"sum({value})::DOUBLE"
            if type_name.startswith("DECIMAL("):
                width, scale = map(int, type_name[8:-1].split(","))
                if width > 30:
                    # Wide decimals can overflow the native sum accumulator.
                    units = f"replace({value}::VARCHAR, '.', '')::BIGNUM"
                    total = f"sum({units})::DOUBLE / 1e{scale}"
        mean = f"({total}) / nullif(count({value}), 0)"
        expressions.append(
            f"struct_pack(mean := {mean}, "
            f"quantiles := quantile_cont({value}::DOUBLE, [0.5, 0.95]), total := {total})"
        )
    return con.execute(f"SELECT {', '.join(expressions)} FROM {source} AS s").fetchone()


def diff_tables(
    con: duckdb.DuckDBPyConnection,
    before: str,
    after: str,
    keys: list[str],
    columns: list[str] | None = None,
    tolerance: float = 0.0,
    sample_rows: int = 5,
) -> DiffResult:
    """Compare tables, views, or parenthesized queries on a DuckDB connection."""
    start = perf_counter()
    old_types = {row[0]: row[1] for row in con.execute(f"DESCRIBE SELECT * FROM {before}").fetchall()}
    new_types = {row[0]: row[1] for row in con.execute(f"DESCRIBE SELECT * FROM {after}").fetchall()}
    if not keys or any(key not in old_types or key not in new_types for key in keys):
        raise ValueError("Keys must name one or more columns present in both tables")

    duplicates = []
    for side, source in (("before", before), ("after", after)):
        groups, excess, examples = _duplicate_keys(con, source, keys)
        if groups:
            key_label = "key" if groups == 1 else "keys"
            row_label = "row" if excess == 1 else "rows"
            duplicates.append(
                f"{side} ({source}): {groups} duplicate {key_label}, {excess} excess {row_label} "
                f"(examples: {examples})"
            )
    if duplicates:
        raise KeyNotUniqueError("; ".join(duplicates))
    if not tolerance >= 0:
        raise ValueError("Tolerance must be nonnegative")

    shared = [column for column in old_types if column in new_types]
    schema = SchemaDiff(
        added_columns=[column for column in new_types if column not in old_types],
        removed_columns=[column for column in old_types if column not in new_types],
        type_changes={
            column: [old_types[column], new_types[column]]
            for column in shared if old_types[column] != new_types[column]
        },
    )
    if columns is None:
        columns = [column for column in shared if column not in keys]
    compared = [column for column in dict.fromkeys(columns) if column in shared]

    # The presence marker distinguishes a missing row from a present row with NULL keys.
    marker = "_diffscope_present"
    names = {name.lower() for name in (*old_types, *new_types)}
    while marker in names:
        marker += "_"
    join = []
    for key in keys:
        left, right = f"b.{_identifier(key)}", f"a.{_identifier(key)}"
        if key in schema.type_changes:
            left, right = f"{left}::VARCHAR", f"{right}::VARCHAR"
        join.append(f"{left} IS NOT DISTINCT FROM {right}")

    projections = [f"b.{marker} AS has_before", f"a.{marker} AS has_after"]
    matched = "has_before AND has_after"
    checks = []
    parameters = []
    for index, column in enumerate(compared):
        left, right = f"b.{_identifier(column)}", f"a.{_identifier(column)}"
        projections += [f"{left} IS NULL AS before_null_{index}", f"{right} IS NULL AS after_null_{index}"]
        if column in schema.type_changes:
            distinct = f"{left}::VARCHAR IS DISTINCT FROM {right}::VARCHAR"
        else:
            distinct = f"{left} IS DISTINCT FROM {right}"
            if tolerance and _numeric(old_types[column]):
                gap = _difference(left, right, old_types[column])
                distinct += f" AND ({left} IS NULL OR {right} IS NULL OR abs({gap}) > ?::DOUBLE)"
                parameters.append(float(tolerance))
        flag = f"changed_{index}"
        projections.append(f"({distinct}) AS {flag}")
        checks.append(flag)

    differs = f"({' OR '.join(checks)})" if checks else "FALSE"
    aggregates = [
        "count(has_before)",
        "count(has_after)",
        "count(*) FILTER (WHERE has_before IS NULL)",
        "count(*) FILTER (WHERE has_after IS NULL)",
        f"count(*) FILTER (WHERE {matched} AND {differs})",
        f"count(*) FILTER (WHERE {matched} AND NOT {differs})",
    ]
    for index, flag in enumerate(checks):
        aggregates.append(f"""
            struct_pack(
                changed_rows := count(*) FILTER (WHERE {matched} AND {flag}),
                null_to_value := count(*) FILTER (WHERE {matched} AND before_null_{index}
                                                 AND NOT after_null_{index}),
                value_to_null := count(*) FILTER (WHERE {matched} AND NOT before_null_{index}
                                                 AND after_null_{index})
            )
        """)

    limit = int(sample_rows)
    if limit > 0:
        projections += [
            f"{_record('b', old_types)} AS old_row", f"{_record('a', new_types)} AS new_row",
            f"{_record('b', keys)} AS old_key", f"{_record('a', keys)} AS new_key",
        ]
        aggregates += [
            f"arg_min(new_row, new_key, {limit}) FILTER (WHERE has_before IS NULL)",
            f"arg_min(old_row, old_key, {limit}) FILTER (WHERE has_after IS NULL)",
        ]
        if checks:
            first_change = f"list_position([{', '.join(checks)}], TRUE)"
            example = f"struct_pack(old_row := old_row, new_row := new_row, position := {first_change})"
            aggregates.append(
                f"arg_min({example}, old_key, {limit}) FILTER (WHERE {matched} AND {differs})"
            )

    row = con.execute(f"""
        SELECT {', '.join(aggregates)}
        FROM (
            SELECT {', '.join(projections)}
            FROM (SELECT *, TRUE AS {marker} FROM {before}) AS b
            FULL OUTER JOIN (SELECT *, TRUE AS {marker} FROM {after}) AS a
            ON {' AND '.join(join)}
        ) AS paired
    """, parameters).fetchone()
    before_rows, after_rows, added, removed, changed, unchanged, *details = row
    column_changes = [ColumnChange(column, **counts) for column, counts in zip(compared, details)]
    column_changes.sort(key=lambda change: change.changed_rows, reverse=True)

    samples = {"added": [], "removed": [], "changed": []}
    if limit > 0:
        added_examples, removed_examples, *changed_examples = details[len(compared):]
        samples["added"] = added_examples or []
        samples["removed"] = removed_examples or []
        examples = changed_examples[0] if changed_examples else None
        for example in examples or []:
            old_row, new_row = example["old_row"], example["new_row"]
            column = compared[example["position"] - 1]
            key_values = {key: old_row[key] for key in keys}
            if key_values.keys() & {"column", "before", "after"}:
                key_values = {"keys": key_values}
            samples["changed"].append(
                {**key_values, "column": column, "before": old_row[column], "after": new_row[column]}
            )

    numeric = [column for column in compared if _numeric(old_types[column]) and _numeric(new_types[column])]
    numeric_shifts = []
    if numeric:
        old_stats = _numeric_stats(con, before, old_types, numeric)
        new_stats = _numeric_stats(con, after, new_types, numeric)
        for column, old, new in zip(numeric, old_stats, new_stats):
            old_median, old_p95 = old["quantiles"] or (None, None)
            new_median, new_p95 = new["quantiles"] or (None, None)
            numeric_shifts.append(NumericShift(
                column, old["mean"], new["mean"], old_median, new_median,
                old_p95, new_p95, old["total"], new["total"],
            ))

    return DiffResult(
        before_name=before,
        after_name=after,
        keys=list(keys),
        before_rows=before_rows,
        after_rows=after_rows,
        added_rows=added,
        removed_rows=removed,
        changed_rows=changed,
        unchanged_rows=unchanged,
        schema=schema,
        column_changes=column_changes,
        numeric_shifts=numeric_shifts,
        samples=samples,
        elapsed_seconds=perf_counter() - start,
    )
