# Jaffle Shop demo

This small dbt project follows the [Jaffle Shop Classic](https://github.com/dbt-labs/jaffle-shop-classic)
pattern of building orders and customers from raw shop data. It uses synthetic seeds.

From the repository root, install the adapter if needed, then build both versions.

```sh
"$HOME/Library/Python/3.9/bin/uv" pip install --python ../diffscope/.venv/bin/python \
  dbt-duckdb 'dbt-core>=1.11,<1.12'
PATH="$PWD/../diffscope/.venv/bin:$PATH" bash examples/jaffle_demo/build.sh
```

The script builds `baseline` and `candidate` in `examples/jaffle_demo/jaffle_demo.duckdb`.
The two targets use the same seeds. The candidate model normalizes `complete` to
`completed` and also multiplies partner order amounts by 100. Both builds leave the
manifest for the most recent target at `examples/jaffle_demo/target/manifest.json`.

Once the engine, report and dbt integration are available, compare both models from
the repository root. The manifest supplies `order_id` and `customer_id` as the keys.

```sh
../diffscope/.venv/bin/python -c 'from diffscope.cli import main; raise SystemExit(main())' \
  dbt --project-dir examples/jaffle_demo --models orders customers \
  --base-schema baseline --target-schema candidate
```

Both builds should pass the dbt key tests. Expect two changed orders and one changed
customer, with no added or removed rows.

- Order `101` changes from `complete` to `completed` as intended.
- Order `103` jumps from 760 to 76,000 cents. Customer `2`'s total jumps from 1,250
  to 76,490 cents.
