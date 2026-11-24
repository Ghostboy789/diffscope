"""Render a table diff as a pull-request comment."""

from __future__ import annotations

import re
from decimal import Decimal

from diffscope.result import DiffResult, NumericShift

_MARKDOWN_SPECIAL = re.compile(r"[&<>|\\`*_\[\]~@$]")


def _text(value: object) -> str:
    text = " ".join(str(value).splitlines())
    if len(text) > 120:
        text = text[:119] + "…"
    # Escape after truncation so a single value cannot change the comment structure.
    return _MARKDOWN_SPECIAL.sub(lambda match: f"&#x{ord(match[0]):x};", text)


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
    verdict = ""
    for shift in shifts:
        column = _text(shift.column)
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
                if not verdict and label == "Mean":
                    direction = "rose" if change > 0 else "fell"
                    if percent is None:
                        verdict = f"Average {column} {direction} from {start} to {end}."
                    else:
                        magnitude = _number(abs(percent), places=1)
                        verdict = f"Average {column} {direction} {magnitude}% ({start} to {end})."
            percent_text = f"{_number(percent, signed=True)}%" if percent is not None else "—"
            rows.append((column, label, start, end, _number(change, signed=True), percent_text))
    return rows, verdict


def render_markdown(result: DiffResult, max_rows: int = 10, title: str | None = None) -> str:
    """Render a verdict, summaries, and up to max_rows examples per category."""
    title_prefix = f"**{_text(title)}** — " if title else ""
    row_changes = (
        ("changed", result.changed_rows), ("added", result.added_rows),
        ("removed", result.removed_rows),
    )
    schema = result.schema
    schema_items = [f"- Added column {_text(column)}" for column in schema.added_columns]
    schema_items.extend(f"- Removed column {_text(column)}" for column in schema.removed_columns)
    schema_items.extend(
        f"- Changed type of {_text(column)} from {_text(before)} to {_text(after)}"
        for column, (before, after) in schema.type_changes.items()
    )
    numeric_rows, mean_verdict = _numeric_rows(result.numeric_shifts)

    verdict = []
    for label, count in row_changes:
        if count:
            subject = "" if verdict else (" row" if count == 1 else " rows")
            verdict.append(f"{count:,}{subject} {label}")
    if verdict:
        lead = ", ".join(verdict) + "."
    elif schema_items:
        lead = "Schema changed."
    elif numeric_rows:
        lead = mean_verdict or "Numeric statistics changed."
        mean_verdict = ""
    else:
        return title_prefix + "No differences."
    if mean_verdict:
        lead += " " + mean_verdict

    counts = (
        ("Before", result.before_rows), ("After", result.after_rows),
        ("Added", result.added_rows), ("Removed", result.removed_rows),
        ("Changed", result.changed_rows), ("Unchanged", result.unchanged_rows),
    )
    sections = [title_prefix + lead, _table(("Rows", "Count"), [
        (label, f"{count:,}") for label, count in counts
    ])]

    columns = [
        (_text(change.column), f"{change.changed_rows:,}", f"{change.null_to_value:,}",
         f"{change.value_to_null:,}")
        for change in result.column_changes if change.changed_rows
    ]
    if columns:
        sections.extend(("### Most changed columns", _table(
            ("Column", "Changed rows", "NULL to value", "Value to NULL"), columns
        )))
    if numeric_rows:
        sections.extend(("### Numeric shifts", _table(
            ("Column", "Statistic", "Before", "After", "Change", "Change (%)"), numeric_rows
        )))
    if schema_items:
        sections.extend(("### Schema changes", "\n".join(schema_items)))

    details = []
    for category in ("added", "removed", "changed"):
        samples = result.samples.get(category, [])[:max(0, max_rows)]
        columns_in_samples = dict.fromkeys(column for row in samples for column in row)
        if not columns_in_samples:
            continue
        headers = tuple(_text(column) for column in columns_in_samples)
        rows = [
            tuple(_sample_cell(row[column]) if column in row else "—" for column in columns_in_samples)
            for row in samples
        ]
        details.append(
            f"<details>\n<summary>{category.title()} rows</summary>\n\n"
            f"{_table(headers, rows)}\n\n</details>"
        )
    if details:
        sections.extend(("### Example rows", *details))
    return "\n\n".join(sections)
