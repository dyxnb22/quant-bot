#!/usr/bin/env bash
# launchd 调用的前台运行入口：注入凭据后 exec freqtrade。
# 不要直接运行本脚本，请用 bot_start.sh / bot_stop.sh 管理。
set -euo pipefail
cd "$(dirname "$0")/.."

# KeepAlive 崩溃重启也必须过风险审计（不能绕过 bot_start 的闸门）
if ! .venv/bin/python -m quantlab.risk_policy >/dev/null 2>&1; then
    echo "$(date '+%F %T') 风险审计未通过，拒绝拉起 bot" >> user_data/logs/freqtrade.log
    sleep 30  # 防 KeepAlive 紧循环
    exit 1
fi

set -a; source .env; set +a
export FREQTRADE__API_SERVER__ENABLED=true
export FREQTRADE__API_SERVER__LISTEN_IP_ADDRESS=127.0.0.1
export FREQTRADE__API_SERVER__LISTEN_PORT=8080
export FREQTRADE__API_SERVER__USERNAME="$FT_API_USERNAME"
export FREQTRADE__API_SERVER__PASSWORD="$FT_API_PASSWORD"
export FREQTRADE__API_SERVER__JWT_SECRET_KEY="$FT_API_JWT_SECRET"
export FREQTRADE__API_SERVER__WS_TOKEN="$FT_API_WS_TOKEN"

mkdir -p user_data/logs
exec .venv/bin/freqtrade trade \
    --config config/config.json \
    --strategy EmaRsiStrategy \
    --logfile user_data/logs/freqtrade.log
