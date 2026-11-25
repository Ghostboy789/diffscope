"""The DiffResult data model shared by every part of diffscope."""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from typing import Any

_NONFINITE = {"NaN": math.nan, "Infinity": math.inf, "-Infinity": -math.inf}


def _json_value(value):
    if isinstance(value, float) and not math.isfinite(value):
        return "NaN" if math.isnan(value) else ("Infinity" if value > 0 else "-Infinity")
    if isinstance(value, dict):
        return {
            (_json_value(key) if isinstance(key, (str, int, float, type(None))) else str(key)):
            _json_value(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


class KeyNotUniqueError(ValueError):
    """A key column combination repeats in one of the tables."""


@dataclass
class SchemaDiff:
    added_columns: list[str] = field(default_factory=list)      # only in `after`
    removed_columns: list[str] = field(default_factory=list)    # only in `before`
    type_changes: dict[str, list[str]] = field(default_factory=dict)  # column -> [before_type, after_type]


@dataclass
class ColumnChange:
    column: str
    changed_rows: int           # matched rows whose value differs
    null_to_value: int          # was NULL, now has a value
    value_to_null: int          # had a value, now NULL


@dataclass
class NumericShift:
    column: str
    before_mean: float | None
    after_mean: float | None
    before_median: float | None
    after_median: float | None
    before_p95: float | None
    after_p95: float | None
    before_sum: float | None
    after_sum: float | None


@dataclass
class DiffResult:
    before_name: str
    after_name: str
    keys: list[str]
    before_rows: int
    after_rows: int
    added_rows: int             # keys only in `after`
    removed_rows: int           # keys only in `before`
    changed_rows: int           # keys in both with at least one compared column different
    unchanged_rows: int
    schema: SchemaDiff
    column_changes: list[ColumnChange]       # sorted by changed_rows, descending
    numeric_shifts: list[NumericShift]       # numeric columns compared, over all rows of each side
    samples: dict[str, list[dict[str, Any]]]  # "added", "removed", "changed" -> example rows
    elapsed_seconds: float

    def to_dict(self) -> dict[str, Any]:
        """Return the result fields with nonfinite values encoded as strings."""
        return _json_value(asdict(self))

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=1, default=str, allow_nan=False)

    @classmethod
    def from_json(cls, text: str) -> DiffResult:
        d = json.loads(text)
        d["schema"] = SchemaDiff(**d["schema"])
        d["column_changes"] = [ColumnChange(**c) for c in d["column_changes"]]
        d["numeric_shifts"] = [
            NumericShift(**{
                field: _NONFINITE.get(value, value) if field != "column" and isinstance(value, str)
                else value
                for field, value in shift.items()
            })
            for shift in d["numeric_shifts"]
        ]
        return cls(**d)
