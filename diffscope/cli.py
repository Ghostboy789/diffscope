"""Command-line entry point for table and dbt comparisons."""

from __future__ import annotations

import argparse
import json
import math
import sys
from glob import escape
from pathlib import Path

import duckdb

from .dbt import load_models
from .result import DiffResult


def _tolerance(value: str) -> float:
    tolerance = float(value)
    if not math.isfinite(tolerance) or tolerance < 0:
        raise argparse.ArgumentTypeError("tolerance must be finite and nonnegative")
    return tolerance


def _nonnegative_int(value: str) -> int:
    count = int(value)
    if count < 0:
        raise argparse.ArgumentTypeError("expected a nonnegative integer")
    return count


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="diffscope")
    commands = parser.add_subparsers(dest="command", required=True)

    tables = commands.add_parser("tables", help="Compare two tables, SQL queries, or files")
    tables.add_argument("before")
    tables.add_argument("after")
    tables.add_argument("--key", action="append", required=True)
    tables.add_argument("--db", type=Path, help="DuckDB file (default: in-memory)")
    tables.add_argument("--columns", nargs="+", action="extend")

    dbt = commands.add_parser("dbt", help="Compare two snapshots of built DuckDB dbt models")
    dbt.add_argument("--project-dir", type=Path, default=Path("."))
    dbt.add_argument("--models", nargs="+", required=True)
    dbt.add_argument("--base-schema", required=True)
    dbt.add_argument("--target-schema", required=True)
    dbt.add_argument("--key", action="append", help="Override each model's diffscope_keys")
    dbt.add_argument("--db", type=Path, help="DuckDB file (default: <catalog>.duckdb in project)")
    dbt.add_argument("--base-db", type=Path, help="Read the base schema from a separate DuckDB file")

    for command in (tables, dbt):
        command.add_argument("--tolerance", type=_tolerance, default=0.0)
        command.add_argument("--sample-rows", type=_nonnegative_int, default=5)
        command.add_argument("--format", choices=("markdown", "json"), default="markdown")
        command.add_argument("--output", type=Path)
        command.add_argument("--memory-limit", default="4GB", help="DuckDB memory limit (default: 4GB)")
        command.add_argument(
            "--max-affected-rows", type=_nonnegative_int, metavar="N",
            help="Exit 3 if added + removed + changed rows exceed N in any comparison",
        )
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
    literal = escape(str(path.resolve())).replace("'", "''")
    return f"(SELECT * FROM {reader}('{literal}'))"


def _connect(db: Path | None, memory_limit: str) -> duckdb.DuckDBPyConnection:
    if db is not None:
        db = db.expanduser()
        if not db.is_file():
            raise FileNotFoundError(f"DuckDB file does not exist: {db}")
    return duckdb.connect(
        str(db) if db is not None else ":memory:",
        read_only=db is not None,
        config={"memory_limit": memory_limit},
    )


def _compare_tables(args: argparse.Namespace) -> DiffResult:
    from .engine import diff_tables

    before = _table_input(args.before)
    after = _table_input(args.after)
    with _connect(args.db, args.memory_limit) as con:
        return diff_tables(
            con, before, after, args.key, columns=args.columns, tolerance=args.tolerance,
            sample_rows=args.sample_rows,
        )


def _compare_dbt(args: argparse.Namespace) -> list[tuple[str, DiffResult]]:
    from .engine import diff_tables

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

    results = []
    with _connect(db, args.memory_limit) as con:
        catalog = con.execute("SELECT current_database()").fetchone()[0]
        base_catalog = catalog
        if args.base_db is not None:
            base_db = args.base_db.expanduser().resolve()
            if base_db != db.expanduser().resolve():
                if not base_db.is_file():
                    raise FileNotFoundError(f"Base DuckDB file does not exist: {base_db}")
                base_catalog = "_diffscope_base"
                if base_catalog == catalog.lower():
                    base_catalog += "_"
                literal = str(base_db).replace("'", "''")
                con.execute(f"ATTACH '{literal}' AS {base_catalog} (READ_ONLY)")

        for model in models:
            before = model.relation(base_catalog, args.base_schema)
            after = model.relation(catalog, args.target_schema)
            try:
                result = diff_tables(
                    con, before, after, model.keys,
                    tolerance=args.tolerance, sample_rows=args.sample_rows,
                )
            except duckdb.CatalogException:
                for side, relation in (("base", before), ("target", after)):
                    try:
                        con.execute(f"DESCRIBE SELECT * FROM {relation}")
                    except duckdb.CatalogException as exc:
                        raise ValueError(
                            f"Cannot read {side} relation {relation} for model {model.name!r}. "
                            f"Build the model in the {side} schema before comparing.\n{exc}"
                        ) from exc
                raise
            results.append((model.name, result))
    return results


def main(argv: list[str] | None = None) -> int:
    from .report import combine_model_reports, render_markdown

    parser = _parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "tables":
            result = _compare_tables(args)
            results = [("tables", result)]
            output = result.to_json() if args.format == "json" else render_markdown(result)
        else:
            results = _compare_dbt(args)
            if args.format == "json":
                output = json.dumps(
                    {"models": [{"model": name, "diff": diff.to_dict()} for name, diff in results]},
                    indent=1, default=str, allow_nan=False,
                )
            else:
                output = combine_model_reports([
                    render_markdown(diff, title=name).rstrip() for name, diff in results
                ])
        output = output.rstrip("\n")
        if args.output:
            args.output.write_text(output + "\n", encoding="utf-8")
        else:
            print(output)
    except (OSError, ValueError, duckdb.Error) as exc:
        parser.exit(1, f"{parser.prog}: {exc}\n")

    status = 0
    if args.max_affected_rows is not None:
        for name, diff in results:
            affected = diff.added_rows + diff.removed_rows + diff.changed_rows
            if affected > args.max_affected_rows:
                rows = "row" if affected == 1 else "rows"
                print(
                    f"{parser.prog}: {name} affected {affected:,} {rows}, "
                    f"above the limit of {args.max_affected_rows:,}",
                    file=sys.stderr,
                )
                status = 3
    return status
