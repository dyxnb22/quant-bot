#!/usr/bin/env bash
# 下载/增量更新回测所需历史 K 线。可重复执行（幂等追加）。
set -euo pipefail
cd "$(dirname "$0")/.."
TIMERANGE="${1:-20230101-}"
.venv/bin/freqtrade download-data \
    --config config/config.json \
    --timerange "$TIMERANGE" \
    --timeframes 1h
