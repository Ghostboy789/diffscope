import json
import re
from dataclasses import asdict

import duckdb
import pytest

from bench.make_scenarios import AFTER_QUERIES, EXPECTED, build_scenario
from diffscope.engine import diff_tables
from diffscope.result import KeyNotUniqueError


@pytest.mark.parametrize("scenario", AFTER_QUERIES)
def test_scenario(scenario):
    expected = json.loads((EXPECTED / f"{scenario}.json").read_text(encoding="utf-8"))

    with duckdb.connect(config={"memory_limit": "4GB"}) as con:
        before, after = build_scenario(con, scenario)
        if expected.get("error") == "KeyNotUniqueError":
            with pytest.raises(KeyNotUniqueError) as error:
                diff_tables(con, before, after, keys=["id"])

            numbers = {int(value) for value in re.findall(r"\b\d+\b", str(error.value))}
            assert expected["duplicate_key_count"] in numbers
            assert len(numbers.intersection(expected["duplicate_keys"])) == expected["example_count"]
            return

        result = diff_tables(con, before, after, keys=["id"])

    assert (result.before_name, result.after_name, result.keys) == (before, after, ["id"])
    for field in (
        "before_rows", "after_rows", "added_rows", "removed_rows", "changed_rows", "unchanged_rows",
    ):
        assert getattr(result, field) == expected[field], field

    assert asdict(result.schema) == expected["schema"]
    changes = {}
    for change in result.column_changes:
        counts = asdict(change)
        column = counts.pop("column")
        assert column not in result.schema.added_columns + result.schema.removed_columns
        if any(counts.values()):
            changes[column] = counts
    assert changes == expected["column_changes"]

    shifts = {shift.column: asdict(shift) for shift in result.numeric_shifts}
    for column, values in expected["numeric_shifts"].items():
        for field, value in values.items():
            assert shifts[column][field] == pytest.approx(value)
