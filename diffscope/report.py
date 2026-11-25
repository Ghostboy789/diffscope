"""Render a table diff as a pull-request comment."""

from __future__ import annotations

import re
from decimal import Decimal

from diffscope.result import DiffResult, NumericShift

_MARKDOWN_SPECIAL = re.compile(r"[&<>|\\`*_\[\]~@$]")
_COMMENT_BYTES = 60_000
_SCHEMA_ITEMS = 12
_COLUMN_ROWS = 12
_NUMERIC_ROWS = 16
_SAMPLE_COLUMNS = 8


def _text(value: object) -> str:
    text = " ".join(str(value).splitlines())
    if len(text) > 120:
        text = text[:119] + "…"
    # Escape after truncation so a single value cannot change the comment structure.
    return _MARKDOWN_SPECIAL.sub(lambda match: f"&#x{ord(match[0]):x};", text)


def _identifier(name: str, *, in_table: bool = False) -> str:
    name = " ".join(name.splitlines())
    if len(name) > 80:
        name = name[:79] + "…"
    if in_table:
        name = name.replace("|", r"\|")
    fence = "`" * (1 + max(map(len, re.findall(r"`+", name)), default=0))
    padded = name.startswith(" ") and name.endswith(" ") and name.strip(" ")
    if name.startswith("`") or name.endswith("`") or padded:
        name = f" {name} "
    return f"{fence}{name}{fence}"


def _number(value: Decimal | None, places: int = 2, signed: bool = False) -> str:
    if value is None:
        return "—"
    if not value.is_finite():
        return str(value)
    prefix = "+" if signed and value > 0 else ""
    if value == 0:
        return "0.0"
    rounded = f"{value:,.{places}f}"
    if value.adjusted() >= 18 or Decimal(rounded.replace(",", "")) == 0:
        return prefix + f"{value:.2e}"
    trimmed = rounded.rstrip("0")
    return prefix + (trimmed + "0" if trimmed.endswith(".") else trimmed)


def _sample_cell(value: object) -> str:
    if value is None:
        return "NULL"
    if type(value) is int:
        return _text(f"{value:,}")
    if isinstance(value, (float, Decimal)):
        return _text(f"{Decimal(str(value)):,}")
    return _text(value)


def _table(headers: tuple[str, ...], rows: list[tuple[str, ...]]) -> str:
    return "\n".join(
        "| " + " | ".join(row) + " |" for row in (headers, ("---",) * len(headers), *rows)
    )


def _numeric_rows(shifts: list[NumericShift]) -> tuple[list[tuple[str, ...]], str]:
    rows = []
    strongest = None
    for shift in shifts:
        start_index = len(rows)
        column = _identifier(shift.column, in_table=True)
        candidates = {}
        statistics = (
            ("Mean", shift.before_mean, shift.after_mean),
            ("Median", shift.before_median, shift.after_median),
            ("P95", shift.before_p95, shift.after_p95),
            ("Sum", shift.before_sum, shift.after_sum),
        )
        for label, before_value, after_value in statistics:
            before = Decimal(str(before_value)) if before_value is not None else None
            after = Decimal(str(after_value)) if after_value is not None else None
            if before == after or (
                before is not None and after is not None and before.is_nan() and after.is_nan()
            ):
                continue

            start, end = _number(before), _number(after)
            change = percent = None
            if before is not None and after is not None and before.is_finite() and after.is_finite():
                change = after - before
                if before != 0:
                    percent = change / abs(before) * 100
                if start == end:
                    start, end = f"{before:,}", f"{after:,}"
                candidates[label] = (percent, change, start, end)
            percent_text = f"{_number(percent, signed=True)}%" if percent is not None else "—"
            rows.append((column, label, start, end, _number(change, signed=True), percent_text))

        order = ("Sum", "Mean", "P95", "Median")
        if "Sum" in candidates and candidates["Sum"][0] is None:
            order = ("Mean", "Sum", "P95", "Median")
        label = next((name for name in order if name in candidates), None)
        if label is not None:
            percent, change, start, end = candidates[label]
            statistic = {
                "Sum": "the sum of", "Mean": "the average of",
                "P95": "the P95 of", "Median": "the median of",
            }[label]
            score = abs(percent) if percent is not None else Decimal(-1)
            if strongest is None or score > strongest[0]:
                direction = "rose" if change > 0 else "fell"
                prefix = f"{statistic} {_identifier(shift.column)} {direction}"
                if percent is None:
                    phrase = f"{prefix} from {start} to {end}"
                else:
                    magnitude = _number(abs(percent), places=1)
                    phrase = f"{prefix} {magnitude}% ({start} to {end})"
                strongest = (score, phrase, start_index, len(rows))
    if strongest is None:
        return rows, ""
    _, verdict, first, last = strongest
    return rows[first:last] + rows[:first] + rows[last:], verdict


def _with_omitted(body: str, hidden: int, label: str) -> str:
    return f"{body}\n\n{hidden:,} more {label}." if hidden > 0 else body


def render_markdown(result: DiffResult, max_rows: int = 10, title: str | None = None) -> str:
    """Render a verdict, summaries, and up to max_rows examples per category."""
    title_prefix = f"**{_identifier(title)}** — " if title else ""
    row_changes = (
        ("added", result.added_rows), ("removed", result.removed_rows),
        ("changed", result.changed_rows),
    )
    schema = result.schema
    retyped_keys = [key for key in result.keys if key in schema.type_changes]
    schema_items = [f"- Added column {_identifier(column)}" for column in schema.added_columns]
    schema_items.extend(
        f"- Removed column {_identifier(column)}" for column in schema.removed_columns
    )
    type_items = {
        column: f"- Changed type of {_identifier(column)} from {_text(before)} to {_text(after)}"
        for column, (before, after) in schema.type_changes.items()
    }
    schema_items = (
        [type_items[key] for key in retyped_keys]
        + schema_items
        + [item for column, item in type_items.items() if column not in retyped_keys]
    )
    numeric_rows, numeric_verdict = _numeric_rows(result.numeric_shifts)

    verdict = []
    if retyped_keys:
        first_key = _identifier(retyped_keys[0])
        if len(retyped_keys) == 1:
            verdict.append(f"key column {first_key} changed type")
        else:
            verdict.append(f"{len(retyped_keys):,} key columns changed type, including {first_key}")
    if numeric_rows:
        verdict.append(numeric_verdict or "numeric statistics changed")
    for label, count in row_changes:
        if count:
            subject = "row" if count == 1 else "rows"
            verb = ("was " if count == 1 else "were ") if label != "changed" else ""
            verdict.append(f"{count:,} {subject} {verb}{label}")
    if len(schema_items) > len(retyped_keys):
        verdict.append("the schema changed")
    if not verdict:
        return title_prefix + "No differences."
    separator = ", " if len(verdict) > 2 else " "
    if len(verdict) > 1:
        verdict[-1] = f"and {verdict[-1]}"
    lead = separator.join(verdict)
    lead = lead[0].upper() + lead[1:] + "."

    counts = (
        ("Before", result.before_rows), ("After", result.after_rows),
        ("Added", result.added_rows), ("Removed", result.removed_rows),
        ("Changed", result.changed_rows), ("Unchanged", result.unchanged_rows),
    )
    sections = [title_prefix + lead, _table(("Rows", "Count"), [
        (label, f"{count:,}") for label, count in counts
    ])]

    if schema_items:
        sections.extend(("### Schema changes", _with_omitted(
            "\n".join(schema_items[:_SCHEMA_ITEMS]), len(schema_items) - _SCHEMA_ITEMS, "schema changes",
        )))
    if numeric_rows:
        table = _table(
            ("Column", "Statistic", "Before", "After", "Change", "Change (%)"),
            numeric_rows[:_NUMERIC_ROWS],
        )
        sections.extend(("### Numeric shifts", _with_omitted(
            table, len(numeric_rows) - _NUMERIC_ROWS, "numeric shifts",
        )))
    changed_columns = sorted(
        (change for change in result.column_changes if change.changed_rows),
        key=lambda change: (-change.changed_rows, change.column),
    )
    columns = [
        (_identifier(change.column, in_table=True), f"{change.changed_rows:,}",
         f"{change.null_to_value:,}",
         f"{change.value_to_null:,}")
        for change in changed_columns[:_COLUMN_ROWS]
    ]
    if columns:
        table = _table(
            ("Column", "Changed rows", "NULL to value", "Value to NULL"), columns
        )
        sections.extend(("### Most changed columns", _with_omitted(
            table, len(changed_columns) - _COLUMN_ROWS, "changed columns",
        )))

    details = []
    nested_keys = {"column", "before", "after"}.intersection(result.keys)
    for category, total in row_changes:
        samples = result.samples.get(category, [])[:max(0, max_rows)]
        available = dict.fromkeys(column for row in samples for column in row)
        if not available:
            continue
        keys = [key for key in result.keys if key in available]
        fields = []
        if category == "changed":
            fields = [field for field in ("column", "before", "after") if field in available]
            if nested_keys and "keys" in available:
                keys = ["keys"]
        visible_keys = keys[:_SAMPLE_COLUMNS - len(fields)]
        ordered = dict.fromkeys((*visible_keys, *fields, *available))
        columns_in_samples = tuple(ordered)[:_SAMPLE_COLUMNS]
        headers = tuple(_identifier(column, in_table=True) for column in columns_in_samples)
        rows = []
        for row in samples:
            cells = {
                column: _sample_cell(row[column]) for column in columns_in_samples if column in row
            }
            if category == "changed" and "column" in row:
                cells["column"] = _identifier(row["column"], in_table=True)
            if category == "changed" and nested_keys and isinstance(row.get("keys"), dict):
                key_values = list(row["keys"].items())
                keys_shown = _SAMPLE_COLUMNS - len(fields)
                cells["keys"] = ", ".join(
                    f"{_identifier(key, in_table=True)} = {_sample_cell(value)}"
                    for key, value in key_values[:keys_shown]
                )
                if len(key_values) > keys_shown:
                    cells["keys"] += f", … ({len(key_values) - keys_shown:,} more keys)"
            rows.append(tuple(cells.get(column, "—") for column in columns_in_samples))
        caption = f"{category.title()} rows"
        if total > len(samples):
            caption += f" ({len(samples):,} of {total:,})"
        table = _with_omitted(
            _table(headers, rows), len(available) - _SAMPLE_COLUMNS, "sample columns",
        )
        details.append(
            f"<details>\n<summary>{caption}</summary>\n\n{table}\n\n</details>"
        )
    if details:
        sections.extend(("### Example rows", *details))
    return "\n\n".join(sections)


def combine_model_reports(reports: list[str]) -> str:
    """Fit a dbt report into the comment budget without cutting Markdown blocks."""
    separator = "\n\n---\n\n"
    full = separator.join(reports)
    if len(full.encode()) <= _COMMENT_BYTES:
        return full

    headlines = []
    # Reserve room for the omission notice, comment marker and final newline.
    remaining = _COMMENT_BYTES - 256
    for report in reports:
        headline = report.partition("\n")[0]
        remaining -= len(headline.encode()) + 2
        if remaining < 0:
            break
        headlines.append(headline)
    hidden = len(reports) - len(headlines)
    notice = f"Details omitted for all {len(reports):,} models to fit the comment."
    if hidden:
        notice += f" {hidden:,} model verdicts also omitted."
    return "\n\n".join([*headlines, notice])
