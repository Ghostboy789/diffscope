"""Compare two DuckDB relations by key."""

from math import floor, isfinite
from string import ascii_lowercase, ascii_uppercase
from time import perf_counter

import duckdb

from diffscope.result import ColumnChange, DiffResult, KeyNotUniqueError, NumericShift, SchemaDiff

_INTEGERS = {
    "TINYINT", "SMALLINT", "INTEGER", "BIGINT", "HUGEINT",
    "UTINYINT", "USMALLINT", "UINTEGER", "UBIGINT", "UHUGEINT", "BIGNUM",
}
_FLOATS = {"FLOAT", "DOUBLE"}
_WIDE_INTEGERS = {"HUGEINT", "UHUGEINT", "BIGNUM"}
_NATIVE_QUANTILE_INTEGERS = _INTEGERS - _WIDE_INTEGERS
_ASCII_LOWER = str.maketrans(ascii_uppercase, ascii_lowercase)


def _identifier(name):
    return '"' + name.replace('"', '""') + '"'


def _name_key(name):
    return name.translate(_ASCII_LOWER)


def _record(fields):
    fields = ", ".join(f"{_identifier(name)} := {value}" for name, value in fields.items())
    return f"struct_pack({fields})"


def _sample_fields(alias, types):
    # The Python datetime returned by DuckDB has microsecond precision.
    return {
        name: f"{alias}.{_identifier(name)}" + ("::VARCHAR" if kind == "TIMESTAMP_NS" else "")
        for name, kind in types.items()
    }


def _duplicate_keys(con, source, expressions):
    return con.execute(f"""
        SELECT count(*), coalesce(sum(n - 1), 0), arg_min(key_values, key_values, 3)
        FROM (
            SELECT {_record(expressions)} AS key_values, count(*) AS n
            FROM {source} AS s
            GROUP BY {', '.join(expressions.values())}
            HAVING count(*) > 1
        )
    """).fetchone()


def _numeric(type_name):
    return type_name in _INTEGERS or type_name in _FLOATS or type_name.startswith("DECIMAL(")


def _difference(left, right, type_name):
    if type_name in _WIDE_INTEGERS:
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
        elif type_name in _WIDE_INTEGERS:
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
        # DuckDB interpolates integers as DOUBLE without widening each input in advance.
        quantile_input = value if type_name in _NATIVE_QUANTILE_INTEGERS else f"{value}::DOUBLE"
        expressions.append(
            f"struct_pack(mean := {mean}, "
            f"quantiles := quantile_cont({quantile_input}, [0.5, 0.95]), total := {total})"
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
    if not isfinite(tolerance) or tolerance < 0:
        raise ValueError("Tolerance must be finite and nonnegative")
    old_types = {row[0]: row[1] for row in con.execute(f"DESCRIBE SELECT * FROM {before}").fetchall()}
    after_types = {
        row[0]: row[1] for row in con.execute(f"DESCRIBE SELECT * FROM {after}").fetchall()
    }
    old_names = {_name_key(column): column for column in old_types}
    new_names = {_name_key(column): column for column in after_types}
    shared_names = old_names.keys() & new_names.keys()
    names = old_names.keys() | new_names.keys()
    shared = [column for name, column in old_names.items() if name in shared_names]
    new_types = {column: after_types[new_names[_name_key(column)]] for column in shared}
    if not keys:
        raise ValueError("Pass at least one key column")
    missing_keys = [key for key in keys if _name_key(key) not in shared_names]
    if missing_keys:
        raise ValueError(f"Key columns must be present in both tables: {', '.join(missing_keys)}")
    keys = [old_names[_name_key(key)] for key in keys]
    if len(set(keys)) != len(keys):
        raise ValueError("Each key column can only be specified once")

    if columns is None:
        compared = [column for column in shared if column not in keys]
    else:
        missing = [column for column in columns if _name_key(column) not in names]
        if missing:
            raise ValueError(f"Unknown comparison columns: {', '.join(missing)}")
        selected = dict.fromkeys(_name_key(column) for column in columns)
        compared = [old_names[name] for name in selected if name in shared_names]

    schema = SchemaDiff(
        added_columns=[column for name, column in new_names.items() if name not in old_names],
        removed_columns=[column for name, column in old_names.items() if name not in new_names],
        type_changes={
            column: [old_types[column], new_types[column]]
            for column in shared if old_types[column] != new_types[column]
        },
    )
    key_expressions = {
        key: _identifier(key) + ("::VARCHAR" if key in schema.type_changes else "")
        for key in keys
    }
    native_keys = {key: f"s.{_identifier(key)}" for key in keys}
    match_keys = {
        key: f'(s.{value}) COLLATE "binary"' if key in schema.type_changes else f"s.{value}"
        for key, value in key_expressions.items()
    }

    duplicates = []
    for side, source in (("before", before), ("after", after)):
        cast_note = ""
        groups, excess, examples = _duplicate_keys(con, source, native_keys)
        if not groups and match_keys != native_keys:
            # Casting retyped keys to text can collapse different native values.
            groups, excess, examples = _duplicate_keys(con, source, match_keys)
            if groups:
                cast_note = " after casting retyped keys to text"
        if groups:
            key_label = "key" if groups == 1 else "keys"
            row_label = "row" if excess == 1 else "rows"
            duplicates.append(
                f"{side} ({source}): {groups} duplicate {key_label}, {excess} excess {row_label}"
                f"{cast_note} (examples: {examples})"
            )
    if duplicates:
        raise KeyNotUniqueError("; ".join(duplicates))

    # The presence marker distinguishes a missing row from a present row with NULL keys.
    marker = "_diffscope_present"
    while marker in names:
        marker += "_"
    join = []
    for key, value in key_expressions.items():
        left, right = f"b.{value}", f"a.{value}"
        if key in schema.type_changes or old_types[key] == "VARCHAR":
            # A collation from one side must not merge distinct keys on the other.
            left, right = f"encode({left})", f"encode({right})"
        join.append(f"{left} IS NOT DISTINCT FROM {right}")

    projections = [f"b.{marker} AS has_before", f"a.{marker} AS has_after"]
    matched = "has_before AND has_after"
    checks = []
    parameters = []
    for index, column in enumerate(compared):
        left, right = f"b.{_identifier(column)}", f"a.{_identifier(column)}"
        projections += [f"{left} IS NULL AS before_null_{index}", f"{right} IS NULL AS after_null_{index}"]
        if column in schema.type_changes:
            distinct = f"encode({left}::VARCHAR) IS DISTINCT FROM encode({right}::VARCHAR)"
        else:
            distinct = f"{left} IS DISTINCT FROM {right}"
            kind = old_types[column]
            if tolerance and _numeric(kind):
                gap = _difference(left, right, kind)
                if kind in _INTEGERS:
                    # Comparing an integer difference as double can hide a one-unit change.
                    if kind in _WIDE_INTEGERS:
                        beyond = f"({gap}) NOT BETWEEN ?::BIGNUM AND ?::BIGNUM"
                        bound = floor(tolerance)
                    else:
                        beyond = f"({gap}) NOT BETWEEN ?::HUGEINT AND ?::HUGEINT"
                        bound = min(floor(tolerance), 2**64 - 1)
                    parameters.extend([str(-bound), str(bound)])
                else:
                    beyond = f"abs({gap}) > ?::DOUBLE"
                    parameters.append(tolerance)
                    if kind in _FLOATS:
                        beyond += f" OR NOT isfinite({left}) OR NOT isfinite({right})"
                distinct += f" AND ({left} IS NULL OR {right} IS NULL OR {beyond})"
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
        old_fields, new_fields = _sample_fields("b", old_types), _sample_fields("a", after_types)
        projections += [
            f"{_record(old_fields)} AS old_row", f"{_record(new_fields)} AS new_row",
            f"{_record({key: f'b.{_identifier(key)}' for key in keys})} AS old_key",
            f"{_record({key: f'a.{_identifier(key)}' for key in keys})} AS new_key",
        ]
        aggregates += [
            f"arg_min(new_row, new_key, {limit}) FILTER (WHERE has_before IS NULL)",
            f"arg_min(old_row, old_key, {limit}) FILTER (WHERE has_after IS NULL)",
        ]
        if checks:
            cases = " ".join(f"WHEN {flag} THEN {index}" for index, flag in enumerate(checks, 1))
            first_change = f"CASE {cases} END"
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
                {**key_values, "column": column, "before": old_row[column],
                 "after": new_row[new_names[_name_key(column)]]}
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
