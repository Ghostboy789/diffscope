import json
import sys
from pathlib import Path
from types import ModuleType

import duckdb
import pytest

from diffscope.cli import _parser, _table_input, main
from diffscope.dbt import load_models
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
    before = tmp_path / "it's here.CSV"
    before.write_text("id,name\n1,old\n", encoding="utf-8")
    after = tmp_path / "after.parquet"
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
