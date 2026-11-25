import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import duckdb
import pytest

from diffscope.cli import _parser, _table_input, main
from diffscope.dbt import COMMENT_MARKER, load_models, post_pr_comment
from diffscope.report import combine_model_reports
from diffscope.result import DiffResult


@pytest.fixture
def contract_fakes(monkeypatch):
    calls = []
    fixture = Path(__file__).parent / "fixtures" / "example_result.json"
    result = DiffResult.from_json(fixture.read_text(encoding="utf-8"))

    def diff_tables(con, before, after, keys, columns=None, tolerance=0.0, sample_rows=5):
        rows = [con.execute(f"SELECT * FROM {relation}").fetchall() for relation in (before, after)]
        calls.append((rows, keys, columns, tolerance, sample_rows))
        return result

    def render_markdown(result, max_rows=10, title=None):
        return f"{title or 'Tables'}: {result.changed_rows} changed"

    engine = ModuleType("diffscope.engine")
    engine.diff_tables = diff_tables
    report = ModuleType("diffscope.report")
    report.render_markdown = render_markdown
    report.combine_model_reports = combine_model_reports
    monkeypatch.setitem(sys.modules, engine.__name__, engine)
    monkeypatch.setitem(sys.modules, report.__name__, report)
    return calls, result


def test_tables_arguments():
    args = _parser().parse_args(
        [
            "tables",
            "before",
            "after",
            "--key",
            "region",
            "--key",
            "id",
            "--db",
            "data.duckdb",
            "--columns",
            "name",
            "price",
            "--tolerance",
            "0.01",
            "--format",
            "json",
            "--output",
            "report.json",
        ]
    )
    assert (args.before, args.after, args.key) == ("before", "after", ["region", "id"])
    assert (args.columns, args.tolerance, args.format) == (["name", "price"], 0.01, "json")
    assert (args.db, args.output) == (Path("data.duckdb"), Path("report.json"))


@pytest.mark.parametrize("options", [[], ["--key", "id", "--tolerance", "nan"]])
def test_invalid_tables_arguments(options):
    with pytest.raises(SystemExit) as error:
        _parser().parse_args(["tables", "before", "after", *options])
    assert error.value.code == 2


def test_table_inputs(tmp_path):
    assert _table_input('prod."order items"') == 'prod."order items"'
    assert _table_input("  (SELECT 'example.csv')  ") == "(SELECT 'example.csv')"
    with pytest.raises(FileNotFoundError, match="missing.parquet"):
        _table_input(str(tmp_path / "missing.parquet"))


def test_tables_reads_csv_and_parquet(tmp_path, contract_fakes):
    calls, result = contract_fakes
    before = tmp_path / "it's here[1].CSV"
    before.write_text("id,name\n1,old\n", encoding="utf-8")
    (tmp_path / "it's here1.CSV").write_text("id,name\n2,other\n", encoding="utf-8")
    after = tmp_path / "after?.parquet"
    with duckdb.connect() as con:
        con.sql("SELECT 1 AS id, 'new' AS name").write_parquet(str(after))
    output = tmp_path / "report.json"

    assert (
        main(
            [
                "tables",
                str(before),
                str(after),
                "--key",
                "id",
                "--columns",
                "name",
                "--tolerance",
                "0.01",
                "--format",
                "json",
                "--output",
                str(output),
            ]
        )
        == 0
    )
    assert calls == [([[(1, "old")], [(1, "new")]], ["id"], ["name"], 0.01, 5)]
    assert json.loads(output.read_text(encoding="utf-8")) == json.loads(result.to_json())


@pytest.fixture
def dbt_project(tmp_path):
    manifest = {
        "metadata": {"adapter_type": "duckdb"},
        "nodes": {
            "model.demo.orders": {
                "resource_type": "model",
                "name": "orders",
                "alias": 'order "summary"',
                "database": "prod",
                "schema": "dev",
                "config": {"meta": {"diffscope_keys": ["id"]}},
            },
            "model.demo.customers": {
                "resource_type": "model",
                "name": "customers",
                "alias": "customers",
                "database": "prod",
                "schema": "dev",
                "meta": {"diffscope_keys": ["customer_id"]},
            },
            "test.demo.customer_key": {"resource_type": "test", "name": "customers"},
        },
    }
    target = tmp_path / "target"
    target.mkdir()
    (target / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return tmp_path


def test_dbt_resolves_models_and_overrides_manifest_keys(dbt_project):
    orders, customers = load_models(dbt_project, ["orders", "model.demo.customers"], None)
    assert orders.keys == ["id"]
    assert customers.keys == ["customer_id"]
    assert orders.relation("prod", "qa east") == '"prod"."qa east"."order ""summary"""'
    assert load_models(dbt_project, ["orders"], ["id", "region"])[0].keys == ["id", "region"]
    with pytest.raises(ValueError, match="was not found"):
        load_models(dbt_project, ["unknown"], None)


def test_dbt_outputs_one_markdown_report(dbt_project, contract_fakes, capsys):
    calls, result = contract_fakes
    with duckdb.connect(str(dbt_project / "prod.duckdb")) as con:
        con.execute('CREATE SCHEMA prod.prod; CREATE SCHEMA prod."qa east"')
        for schema, value in (("prod", 1), ("qa east", 2)):
            con.execute(f'CREATE TABLE prod."{schema}"."order ""summary""" AS SELECT {value} AS id')
            con.execute(f'CREATE TABLE prod."{schema}".customers AS SELECT 10 AS customer_id')

    assert (
        main(
            [
                "dbt",
                "--project-dir",
                str(dbt_project),
                "--models",
                "orders",
                "customers",
                "--base-schema",
                "prod",
                "--target-schema",
                "qa east",
            ]
        )
        == 0
    )
    assert calls == [
        ([[(1,)], [(2,)]], ["id"], None, 0.0, 5),
        ([[(10,)], [(10,)]], ["customer_id"], None, 0.0, 5),
    ]
    changed = result.changed_rows
    assert (
        capsys.readouterr().out
        == f"orders: {changed} changed\n\n---\n\ncustomers: {changed} changed\n"
    )


@pytest.mark.parametrize("previous_id", [None, 27])
def test_sticky_comment(tmp_path, monkeypatch, previous_id):
    report = tmp_path / "report.md"
    report.write_text("3 rows changed\n", encoding="utf-8")
    unrelated = [
        {"id": 10, "user": {"login": "person"}, "body": f"{COMMENT_MARKER}\nHello"},
        {"id": 11, "user": {"login": "github-actions[bot]"}, "body": f"About {COMMENT_MARKER}"},
    ]
    previous = []
    if previous_id is not None:
        previous.append(
            {
                "id": previous_id,
                "user": {"login": "github-actions[bot]"},
                "body": f"{COMMENT_MARKER}\nOld report",
            }
        )
    writes = []
    endpoint = "repos/owner/demo/issues/23/comments"

    def gh(args, *, check, text, stdout=None, input=None):
        assert check and text
        if stdout == subprocess.PIPE:
            assert args == ["gh", "api", endpoint, "--paginate", "--slurp"]
            return subprocess.CompletedProcess(args, 0, json.dumps([unrelated, previous]))
        assert args[:2] == ["gh", "api"]
        assert args[5:] == ["--input", "-", "--silent"]
        writes.append((args[2], args[4], json.loads(input)["body"]))
        return subprocess.CompletedProcess(args, 0)

    monkeypatch.setattr(subprocess, "run", gh)
    post_pr_comment(str(report), "owner/demo", "23")

    expected_body = f"{COMMENT_MARKER}\n3 rows changed\n"
    if previous_id is None:
        assert writes == [(endpoint, "POST", expected_body)]
    else:
        assert writes == [
            (f"repos/owner/demo/issues/comments/{previous_id}", "PATCH", expected_body)
        ]


def test_tables_row_gate_keeps_report_on_failure(tmp_path, capsys):
    before = "(SELECT * FROM (VALUES (1, 10), (2, 20), (4, 40)) t(id, value))"
    after = "(SELECT * FROM (VALUES (2, 21), (3, 30), (4, 40)) t(id, value))"
    output = tmp_path / "report.json"
    args = [
        "tables", before, after, "--key", "id", "--format", "json",
        "--sample-rows", "0", "--memory-limit", "128MB", "--output", str(output),
    ]

    assert main([*args, "--max-affected-rows", "2"]) == 3
    assert "tables affected 3 rows, above the limit of 2" in capsys.readouterr().err
    diff = json.loads(output.read_text())
    assert (diff["added_rows"], diff["removed_rows"], diff["changed_rows"]) == (1, 1, 1)
    assert diff["samples"] == {"added": [], "removed": [], "changed": []}
    assert main([*args, "--max-affected-rows", "3"]) == 0
    assert capsys.readouterr().err == ""


def test_dbt_compares_separate_read_only_snapshots(dbt_project, capsys):
    base = dbt_project / "it's baseline.duckdb"
    target = dbt_project / "_diffscope_base.duckdb"
    # Both use the same dbt schema and model aliases, backed by different local files.
    for path, price, name in ((base, 10.0, "old"), (target, 10.5, "new")):
        with duckdb.connect(str(path)) as con:
            con.execute("CREATE SCHEMA dataset")
            con.execute('CREATE TABLE dataset."order ""summary""" (id INT, price DOUBLE)')
            con.execute('INSERT INTO dataset."order ""summary""" VALUES (1, ?)', [price])
            con.execute("CREATE TABLE dataset.customers (customer_id INTEGER, name VARCHAR)")
            con.execute("INSERT INTO dataset.customers VALUES (2, ?)", [name])
    snapshots = [path.read_bytes() for path in (base, target)]

    assert main([
        "dbt", "--project-dir", str(dbt_project), "--models", "orders", "customers",
        "--base-schema", "dataset", "--target-schema", "dataset",
        "--base-db", str(base), "--db", str(target), "--tolerance", "0.5", "--format", "json",
        "--max-affected-rows", "0",
    ]) == 3

    capture = capsys.readouterr()
    orders, customers = json.loads(capture.out)["models"]
    assert (orders["model"], customers["model"]) == ("orders", "customers")
    assert (orders["diff"]["unchanged_rows"], customers["diff"]["changed_rows"]) == (1, 1)
    assert customers["diff"]["samples"]["changed"] == [{
        "customer_id": 2, "column": "name", "before": "old", "after": "new",
    }]
    assert "customers affected 1 row, above the limit of 0" in capture.err
    assert "orders" not in capture.err
    assert [path.read_bytes() for path in (base, target)] == snapshots


@pytest.mark.parametrize("side", ["base", "target"])
def test_dbt_names_missing_built_relation(dbt_project, capsys, side):
    with duckdb.connect(str(dbt_project / "prod.duckdb")) as con:
        schema = "baseline" if side == "target" else "candidate"
        con.execute(f"CREATE SCHEMA {schema}")
        con.execute(f'CREATE VIEW {schema}."order ""summary""" AS SELECT 1 AS id')
    with pytest.raises(SystemExit) as error:
        main([
            "dbt", "--project-dir", str(dbt_project), "--models", "orders",
            "--base-schema", "baseline", "--target-schema", "candidate",
        ])
    assert error.value.code == 1
    capture = capsys.readouterr()
    assert f"Cannot read {side} relation" in capture.err
    assert f"Build the model in the {side} schema" in capture.err
    assert capture.out == ""


@pytest.mark.parametrize("content", [None, "{wrong"])
def test_dbt_manifest_errors_point_to_manifest(tmp_path, capsys, content):
    if content is not None:
        (tmp_path / "target").mkdir()
        (tmp_path / "target" / "manifest.json").write_text(content)
    with pytest.raises(SystemExit) as error:
        main([
            "dbt", "--project-dir", str(tmp_path), "--models", "orders",
            "--base-schema", "baseline", "--target-schema", "candidate",
        ])
    assert error.value.code == 1
    message = capsys.readouterr().err
    assert "target/manifest.json" in message
    assert ("Run dbt build first" if content is None else "Could not read") in message
