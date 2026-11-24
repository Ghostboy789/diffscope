"""Time the 1% value-change comparison at three table sizes."""

import platform
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter

import duckdb

from bench.make_scenarios import build_scenario

SIZES = (100_000, 1_000_000, 10_000_000)
RESULTS = Path(__file__).with_name("results.md")


def write_results(body: str) -> None:
    RESULTS.write_text(f"# Diff benchmark\n\n{body}\n", encoding="utf-8")
    print(body)


def main() -> None:
    try:
        from diffscope.engine import diff_tables
    except ModuleNotFoundError as error:
        if error.name != "diffscope.engine":
            raise
        write_results("Skipped because `diffscope.engine` is unavailable.")
        return

    results = [
        (
            f"DuckDB {duckdb.__version__} on {platform.system()} {platform.machine()} with a 4 GB "
            "DuckDB memory limit. Each duration is a single wall-clock observation and excludes "
            "table creation. A confidence interval requires repeated runs."
        ),
        "",
        "| Rows per side | Changed rows | Wall-clock seconds |",
        "| ---: | ---: | ---: |",
    ]
    for rows in SIZES:
        with TemporaryDirectory(prefix="diffscope-bench-") as directory:
            database = Path(directory) / "benchmark.duckdb"
            with duckdb.connect(str(database), config={"memory_limit": "4GB"}) as con:
                before, after = build_scenario(con, "value_changes", rows)
                started = perf_counter()
                try:
                    result = diff_tables(con, before, after, keys=["id"])
                except NotImplementedError:
                    if rows != SIZES[0]:
                        raise
                    write_results("Skipped because `diff_tables` is awaiting implementation.")
                    return
                elapsed = perf_counter() - started

        assert (result.before_rows, result.after_rows) == (rows, rows)
        assert (result.added_rows, result.removed_rows) == (0, 0)
        assert (result.changed_rows, result.unchanged_rows) == (rows // 100, rows - rows // 100)
        results.append(f"| {rows:,} | {result.changed_rows:,} | {elapsed:.3f} |")

    write_results("\n".join(results))


if __name__ == "__main__":
    main()
