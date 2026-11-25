# Diff benchmark

DuckDB 2.0.1 on Darwin arm64 with a 4 GB DuckDB memory limit. Each duration is a single wall-clock observation and excludes table creation. A confidence interval requires repeated runs.

| Rows per side | Changed rows | Wall-clock seconds |
| ---: | ---: | ---: |
| 100,000 | 1,000 | 0.023 |
| 1,000,000 | 10,000 | 0.071 |
| 10,000,000 | 100,000 | 0.541 |
