"""Command-line entry point for table and dbt comparisons."""

from __future__ import annotations

import argparse
import math
from pathlib import Path

import duckdb

from .dbt import load_models


def _tolerance(value: str) -> float:
    tolerance = float(value)
    if not math.isfinite(tolerance) or tolerance < 0:
        raise argparse.ArgumentTypeError("tolerance must be finite and nonnegative")
    return tolerance


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="diffscope")
    commands = parser.add_subparsers(dest="command", required=True)

    tables = commands.add_parser("tables", help="Compare two tables, SQL queries, or files")
    tables.add_argument("before")
    tables.add_argument("after")
    tables.add_argument("--key", action="append", required=True)
    tables.add_argument("--db", type=Path, help="DuckDB file (default: in-memory)")
    tables.add_argument("--columns", nargs="+", action="extend")
    tables.add_argument("--tolerance", type=_tolerance, default=0.0)
    tables.add_argument("--format", choices=("markdown", "json"), default="markdown")
    tables.add_argument("--output", type=Path)

    dbt = commands.add_parser("dbt", help="Compare built dbt models across two DuckDB schemas")
    dbt.add_argument("--project-dir", type=Path, default=Path("."))
    dbt.add_argument("--models", nargs="+", required=True)
    dbt.add_argument("--base-schema", required=True)
    dbt.add_argument("--target-schema", required=True)
    dbt.add_argument("--key", action="append", help="Override each model's diffscope_keys")
    dbt.add_argument("--db", type=Path, help="DuckDB file (default: <catalog>.duckdb in project)")
    dbt.add_argument("--output", type=Path)
    return parser


def _table_input(source: str) -> str:
    value = source.strip()
    if value.startswith("(") and value.endswith(")"):
        return value
    path = Path(source).expanduser()
    reader = {".csv": "read_csv_auto", ".parquet": "read_parquet"}.get(path.suffix.lower())
    if reader is None:
        return source
    if not path.is_file():
        raise FileNotFoundError(f"Input file does not exist: {path}")
    literal = str(path.resolve()).replace("'", "''")
    return f"(SELECT * FROM {reader}('{literal}'))"


def _connect(db: Path | None) -> duckdb.DuckDBPyConnection:
    return duckdb.connect(
        str(db.expanduser()) if db is not None else ":memory:",
        read_only=db is not None,
        config={"memory_limit": "4GB"},
    )


def _compare_tables(args: argparse.Namespace) -> str:
    from .engine import diff_tables

    before = _table_input(args.before)
    after = _table_input(args.after)
    with _connect(args.db) as con:
        result = diff_tables(
            con, before, after, args.key, columns=args.columns, tolerance=args.tolerance
        )
    if args.format == "json":
        return result.to_json()

    from .report import render_markdown

    return render_markdown(result)


def _compare_dbt(args: argparse.Namespace) -> str:
    from .engine import diff_tables
    from .report import render_markdown

    models = load_models(args.project_dir, args.models, args.key)
    db = args.db
    if db is None:
        catalogs = {model.database for model in models}
        catalog = models[0].database
        if len(catalogs) != 1 or not catalog or Path(catalog).name != catalog:
            raise ValueError("Pass --db to select the DuckDB file")
        db = args.project_dir.expanduser() / f"{catalog}.duckdb"
        if not db.is_file():
            raise FileNotFoundError(f"DuckDB file does not exist: {db}. Pass its path with --db.")

    reports = []
    with _connect(db) as con:
        catalog = con.execute("SELECT current_database()").fetchone()[0]
        for model in models:
            result = diff_tables(
                con,
                model.relation(catalog, args.base_schema),
                model.relation(catalog, args.target_schema),
                model.keys,
            )
            reports.append(render_markdown(result, title=model.name).rstrip())
    return "\n\n---\n\n".join(reports)


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        result = _compare_tables(args) if args.command == "tables" else _compare_dbt(args)
        if args.output:
            args.output.write_text(result.rstrip("\n") + "\n", encoding="utf-8")
        else:
            print(result.rstrip("\n"))
    except ModuleNotFoundError as exc:
        if exc.name not in {"diffscope.engine", "diffscope.report"}:
            raise
        parser.exit(1, f"{parser.prog}: required module {exc.name} is unavailable\n")
    except (OSError, ValueError, duckdb.Error) as exc:
        parser.exit(1, f"{parser.prog}: {exc}\n")
    return 0
