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


def _identifier(name: str, *, in_table: bool = False) -> str:
    name = " ".join(name.splitlines())
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
        column = _identifier(shift.column, in_table=True)
        mean_shift = sum_shift = None
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
                if label == "Mean":
                    mean_shift = (percent, change, start, end, "the average of")
                if label == "Sum" and percent is not None:
                    sum_shift = (percent, change, start, end, "the sum of")
            percent_text = f"{_number(percent, signed=True)}%" if percent is not None else "—"
            rows.append((column, label, start, end, _number(change, signed=True), percent_text))

        candidate = sum_shift or mean_shift
        if candidate is not None:
            percent, change, start, end, statistic = candidate
            score = abs(percent) if percent is not None else Decimal(-1)
            if strongest is None or score > strongest[0]:
                direction = "rose" if change > 0 else "fell"
                prefix = f"{statistic} {_identifier(shift.column)} {direction}"
                if percent is None:
                    phrase = f"{prefix} from {start} to {end}"
                else:
                    magnitude = _number(abs(percent), places=1)
                    phrase = f"{prefix} {magnitude}% ({start} to {end})"
                strongest = (score, phrase)
    return rows, strongest[1] if strongest else ""


def render_markdown(result: DiffResult, max_rows: int = 10, title: str | None = None) -> str:
    """Render a verdict, summaries, and up to max_rows examples per category."""
    title_prefix = f"**{_identifier(title)}** — " if title else ""
    row_changes = (
        ("added", result.added_rows), ("removed", result.removed_rows),
        ("changed", result.changed_rows),
    )
    schema = result.schema
    schema_items = [f"- Added column {_identifier(column)}" for column in schema.added_columns]
    schema_items.extend(
        f"- Removed column {_identifier(column)}" for column in schema.removed_columns
    )
    schema_items.extend(
        f"- Changed type of {_identifier(column)} from {_text(before)} to {_text(after)}"
        for column, (before, after) in schema.type_changes.items()
    )
    numeric_rows, numeric_verdict = _numeric_rows(result.numeric_shifts)

    verdict = []
    for label, count in row_changes:
        if count:
            subject = "row" if count == 1 else "rows"
            verb = ("was " if count == 1 else "were ") if label != "changed" else ""
            verdict.append(f"{count:,} {subject} {verb}{label}")
    if numeric_rows:
        verdict.append(numeric_verdict or "numeric statistics changed")
    if schema_items:
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

    columns = [
        (_identifier(change.column, in_table=True), f"{change.changed_rows:,}",
         f"{change.null_to_value:,}",
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
    nested_keys = {"column", "before", "after"}.intersection(result.keys)
    for category in ("added", "removed", "changed"):
        samples = result.samples.get(category, [])[:max(0, max_rows)]
        columns_in_samples = dict.fromkeys(column for row in samples for column in row)
        if not columns_in_samples:
            continue
        headers = tuple(_identifier(column, in_table=True) for column in columns_in_samples)
        rows = []
        for row in samples:
            cells = {column: _sample_cell(value) for column, value in row.items()}
            if category == "changed" and "column" in row:
                cells["column"] = _identifier(row["column"], in_table=True)
            if category == "changed" and nested_keys and isinstance(row.get("keys"), dict):
                cells["keys"] = ", ".join(
                    f"{_identifier(key, in_table=True)} = {_sample_cell(value)}"
                    for key, value in row["keys"].items()
                )
            rows.append(tuple(cells.get(column, "—") for column in columns_in_samples))
        details.append(
            f"<details>\n<summary>{category.title()} rows</summary>\n\n"
            f"{_table(headers, rows)}\n\n</details>"
        )
    if details:
        sections.extend(("### Example rows", *details))
    return "\n\n".join(sections)
