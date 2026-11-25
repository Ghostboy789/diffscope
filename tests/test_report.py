from dataclasses import replace
from html import unescape
from pathlib import Path

import pytest

from diffscope.report import render_markdown
from diffscope.result import DiffResult, SchemaDiff


@pytest.fixture
def example():
    path = Path(__file__).parent / "fixtures" / "example_result.json"
    return DiffResult.from_json(path.read_text())


@pytest.fixture
def identical(example):
    shift = example.numeric_shifts[0]
    return replace(
        example,
        after_rows=example.before_rows,
        added_rows=0,
        removed_rows=0,
        changed_rows=0,
        unchanged_rows=example.before_rows,
        schema=SchemaDiff(),
        column_changes=[],
        numeric_shifts=[
            replace(
                shift,
                after_mean=shift.before_mean,
                after_median=shift.before_median,
                after_p95=shift.before_p95,
                after_sum=shift.before_sum,
            )
        ],
        samples={},
    )


def test_fixture_comment(example):
    assert render_markdown(example) == """\
6 rows were added, 2 rows were removed, 37 rows changed, the sum of `amount` fell 3.3% (642,000.0 to 620,974.0), and the schema changed.

| Rows | Count |
| --- | --- |
| Before | 1,000 |
| After | 1,004 |
| Added | 6 |
| Removed | 2 |
| Changed | 37 |
| Unchanged | 961 |

### Most changed columns

| Column | Changed rows | NULL to value | Value to NULL |
| --- | --- | --- | --- |
| `amount` | 31 | 0 | 2 |
| `status` | 6 | 0 | 0 |

### Numeric shifts

| Column | Statistic | Before | After | Change | Change (%) |
| --- | --- | --- | --- | --- | --- |
| `amount` | Mean | 642.0 | 618.5 | -23.5 | -3.66% |
| `amount` | Median | 540.0 | 520.0 | -20.0 | -3.7% |
| `amount` | P95 | 1,490.0 | 1,402.0 | -88.0 | -5.91% |
| `amount` | Sum | 642,000.0 | 620,974.0 | -21,026.0 | -3.28% |

### Schema changes

- Added column `discount_code`
- Changed type of `status` from INTEGER to VARCHAR

### Example rows

<details>
<summary>Added rows</summary>

| `order_id` | `amount` | `status` |
| --- | --- | --- |
| 1,001 | 120.0 | placed |

</details>

<details>
<summary>Removed rows</summary>

| `order_id` | `amount` | `status` |
| --- | --- | --- |
| 17 | 980.0 | 2 |

</details>

<details>
<summary>Changed rows</summary>

| `order_id` | `column` | `before` | `after` |
| --- | --- | --- | --- |
| 42 | `amount` | 700.0 | 630.0 |

</details>"""


def test_identical_tables(identical):
    assert render_markdown(identical) == "No differences."
    assert render_markdown(identical, title="old_orders") == "**`old_orders`** — No differences."


def test_schema_only_changes(identical):
    schema = SchemaDiff(["new"], ["old"], {"status": ["INTEGER", "VARCHAR"]})
    comment = render_markdown(replace(identical, schema=schema))

    assert comment.startswith("The schema changed.\n\n| Rows | Count |")
    assert comment.endswith(
        "### Schema changes\n\n"
        "- Added column `new`\n"
        "- Removed column `old`\n"
        "- Changed type of `status` from INTEGER to VARCHAR"
    )


def test_verdict_ranks_sums_by_relative_change(identical):
    first = replace(
        identical.numeric_shifts[0], before_sum=1_000, after_sum=1_500,
        before_mean=1, after_mean=10,
    )
    strongest = replace(
        first, column="fee_cents", before_sum=10, after_sum=2, before_mean=1, after_mean=1,
    )
    result = replace(identical, numeric_shifts=[first, strongest], schema=SchemaDiff(["new"]))

    assert render_markdown(result).splitlines()[0] == (
        "The sum of `fee_cents` fell 80.0% (10.0 to 2.0) and the schema changed."
    )


def test_tiny_shift_and_zero_baseline(identical):
    shift = replace(
        identical.numeric_shifts[0], before_mean=100.0, after_mean=100.000001,
        before_sum=0.0, after_sum=0.0001,
    )
    comment = render_markdown(replace(identical, numeric_shifts=[shift]))

    assert comment.startswith("The average of `amount` rose 1.00e-6% (100.0 to 100.000001).\n")
    assert "| `amount` | Mean | 100.0 | 100.000001 | +1.00e-6 | +1.00e-6% |" in comment
    assert "| `amount` | Sum | 0.0 | 1.00e-4 | +1.00e-4 | — |" in comment


def test_samples_truncate_and_escape_untrusted_text(example):
    column = "`header|*_[field]\r\nname"
    value = "|\\`*_[]~@</details>&#124;\r\n| injected row | " + "界" * 1_000
    example.samples = {"added": [{column: value}, {column: "hidden sample"}]}
    comment = render_markdown(example, max_rows=1, title="New [orders] <review>")
    sample = comment.split("### Example rows\n\n", 1)[1]
    header, divider, row = [line for line in sample.splitlines() if line.startswith("|")]

    assert comment.startswith("**`New [orders] <review>`** — 6 rows were added")
    assert divider == "| --- |"
    assert row.count("|") == 2
    assert header == r"| `` `header\|*_[field] name `` |"
    value_prefix = " ".join(value.splitlines())
    decoded = unescape(row[2:-2])
    assert decoded.endswith("…")
    assert value_prefix.startswith(decoded[:-1])
    assert 50 < len(decoded) < 200
    assert sample.count("</details>") == 1
    assert "hidden sample" not in sample
    assert "### Example rows" not in render_markdown(example, max_rows=0)


def test_sample_columns_cover_all_visible_rows(example):
    example.samples = {
        "added": [{"id": 42}, {"id": 43, "value": None}, {"id": 44, "value": 1_000.000001}]
    }

    assert (
        "| `id` | `value` |\n| --- | --- |\n| 42 | — |\n| 43 | NULL |\n| 44 | 1,000.000001 |"
        in render_markdown(example)
    )


def test_changed_sample_formats_nested_key_names(example):
    result = replace(example, keys=["before", "key_name"], samples={
        "changed": [{"keys": {"before": "*", "key_name": 42},
                     "column": "amount_cents", "before": "a_b", "after": "c_d"}]
    })

    assert (
        "| `before` = &#x2a;, `key_name` = 42 | `amount_cents` | a&#x5f;b | c&#x5f;d |"
        in render_markdown(result)
    )


def test_verdict_orders_rows_then_changes_then_numbers_then_schema(identical):
    shift = replace(identical.numeric_shifts[0], before_sum=100, after_sum=150)
    result = replace(
        identical, added_rows=2, removed_rows=1, changed_rows=3,
        numeric_shifts=[shift], schema=SchemaDiff(["new"]),
    )

    assert render_markdown(result).splitlines()[0] == (
        "2 rows were added, 1 row was removed, 3 rows changed, "
        "the sum of `amount` rose 50.0% (100.0 to 150.0), and the schema changed."
    )
