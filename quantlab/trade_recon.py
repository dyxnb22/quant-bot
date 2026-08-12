"""成交对账：dry-run 实际成交 vs 回测假设（信号蜡烛收盘价）的偏差。

回测假设成交价 ≈ 信号蜡烛（下单蜡烛的前一根）收盘价；
本工具量化真实（模拟）成交与该假设的滑点，为"回测可信度"积累证据。
产物：user_data/logs/recon/YYYY-MM-DD.md（运行产物不入库，摘要可引用）。
"""

import base64
import json
import sys
import urllib.request
from datetime import datetime, timedelta

import pandas as pd

from quantlab.health import API_BASE, load_env
from quantlab.strategy_loader import PROJECT_DIR

RECON_DIR = PROJECT_DIR / "user_data" / "logs" / "recon"
CANDLE_DIR = PROJECT_DIR / "user_data" / "data" / "okx"

_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _api(path: str, env: dict):
    token = base64.b64encode(
        f"{env['FT_API_USERNAME']}:{env['FT_API_PASSWORD']}".encode()).decode()
    request = urllib.request.Request(
        f"{API_BASE}{path}", headers={"Authorization": f"Basic {token}"})
    with _OPENER.open(request, timeout=10) as response:
        return json.load(response)


def signal_close(pair: str, order_time: pd.Timestamp) -> float | None:
    """下单时刻所属蜡烛的前一根（信号蜡烛）收盘价。"""
    path = CANDLE_DIR / f"{pair.replace('/', '_')}-1h.feather"
    if not path.exists():
        return None
    candles = pd.read_feather(path).set_index("date")
    candles.index = candles.index.tz_localize(None)  # 统一为裸 UTC，与 API 时间口径一致
    signal_candle = order_time.floor("1h") - timedelta(hours=1)
    if signal_candle not in candles.index:
        return None
    return float(candles.loc[signal_candle, "close"])


def reconcile_trade(trade: dict) -> dict:
    pair = trade["pair"]
    row = {"pair": pair, "open_date": trade.get("open_date", ""),
           "exit_reason": trade.get("exit_reason") or ("持仓中" if trade.get("is_open") else "")}
    open_time = pd.Timestamp(trade["open_date"]).tz_localize(None)
    reference = signal_close(pair, open_time)
    if reference:
        row["entry_slippage_bps"] = (trade["open_rate"] / reference - 1) * 1e4
    else:
        row["note"] = "信号蜡烛不在本地数据（先 make data 更新）"
    if not trade.get("is_open") and trade.get("close_rate"):
        close_time = pd.Timestamp(trade["close_date"]).tz_localize(None)
        reference_exit = signal_close(pair, close_time)
        if reference_exit:
            row["exit_slippage_bps"] = (trade["close_rate"] / reference_exit - 1) * 1e4
    row["fee_open"] = trade.get("fee_open")
    row["fee_close"] = trade.get("fee_close")
    return row


def main() -> int:
    env = load_env()
    closed = _api("/trades?limit=500", env).get("trades", [])
    open_trades = _api("/status", env)
    trades = closed + open_trades
    if not trades:
        print("尚无成交可对账")
        return 0

    rows = [reconcile_trade(t) for t in trades]
    entry_slips = [r["entry_slippage_bps"] for r in rows if "entry_slippage_bps" in r]
    lines = [
        f"# 成交对账 {datetime.now():%F}",
        "",
        f"- 样本: 平仓 {len(closed)} 笔 + 持仓 {len(open_trades)} 笔（dry-run）",
        f"- 入场滑点（成交价 vs 信号蜡烛收盘）: 均值 "
        f"{sum(entry_slips)/len(entry_slips):+.1f} bps（{len(entry_slips)} 笔可对账）"
        if entry_slips else "- 无可对账的入场记录",
        "",
        "| 币对 | 开仓时间 | 入场滑点 bps | 出场滑点 bps | 开仓费率 | 平仓费率 | 出场原因 |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r['pair']} | {str(r['open_date'])[:16]} "
            f"| {r.get('entry_slippage_bps', float('nan')):+.1f} "
            f"| {r.get('exit_slippage_bps', float('nan')):+.1f} "
            f"| {r.get('fee_open')} | {r.get('fee_close')} | {r['exit_reason']} |")
    lines += ["", "> 样本量不足 30 笔前，本报告仅证明对账管道可用，不构成成交质量结论。"]

    RECON_DIR.mkdir(parents=True, exist_ok=True)
    target = RECON_DIR / f"{datetime.now():%F}.md"
    target.write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    print(f"\n对账: {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
