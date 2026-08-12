#!/usr/bin/env bash
# 查询运行状态：launchd 服务 + 进程 + REST API 健康 + 持仓/收益摘要
set -euo pipefail
cd "$(dirname "$0")/.."
set -a; source .env; set +a
BASE="http://127.0.0.1:8080/api/v1"
AUTH="$FT_API_USERNAME:$FT_API_PASSWORD"
LABEL="com.quantbot.dryrun"
# 本机 API 请求绕过系统代理，避免本地代理干扰
CURL="curl -s --noproxy 127.0.0.1"

if launchctl print "gui/$(id -u)/${LABEL}" >/dev/null 2>&1; then
    echo "launchd 服务: 已加载 (${LABEL})"
else
    echo "launchd 服务: 未加载"
fi

PID=$(pgrep -f "freqtrade trade" | head -1 || true)
if [[ -n "$PID" ]]; then
    echo "进程: 运行中 (pid=$PID)"
else
    echo "进程: 未运行"; exit 1
fi

echo "--- ping ---"
$CURL "$BASE/ping"; echo
echo "--- 概览 ---"
$CURL -u "$AUTH" "$BASE/show_config" | .venv/bin/python -c "import json,sys; c=json.load(sys.stdin); print('state:', c['state'], '| strategy:', c['strategy'], '| dry_run:', c['dry_run'])"
echo "--- 收益 ---"
$CURL -u "$AUTH" "$BASE/profit" | .venv/bin/python -c "import json,sys; p=json.load(sys.stdin); print('平仓:', p.get('closed_trade_count', 0), '笔 | 总交易:', p.get('trade_count', 0), '| 已实现:', round(p['profit_closed_coin'], 2), 'USDT | 胜率:', round(p.get('winrate', 0) * 100, 1), '%')"
echo "--- 持仓 ---"
$CURL -u "$AUTH" "$BASE/status" | .venv/bin/python -c "
import json, sys
trades = json.load(sys.stdin)
if not trades:
    print('（当前空仓）')
for t in trades:
    print(f\"{t['pair']}: 开仓价 {t['open_rate']} | 当前收益 {t['profit_pct']}%\")
"
