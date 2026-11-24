#!/usr/bin/env bash
set -euo pipefail

cd -- "$(dirname -- "$0")"
export DBT_SEND_ANONYMOUS_USAGE_STATS=false
dbt build --profiles-dir . --target baseline
dbt build --profiles-dir . --target candidate
