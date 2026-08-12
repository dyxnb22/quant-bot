"""LLM 值班日报：模拟盘状态 + 24h 行情摘要 → 风险观察报告（只读，不进交易回路）。

每日由 launchd 定时生成，落盘 user_data/logs/daily_brief/YYYY-MM-DD.md。
"""

import base64
import json
import sys
import urllib.request
from datetime import datetime

import pandas as pd

from quantlab.data_quality import DATA_DIR
from quantlab.health import API_BASE, check_log_fresh, check_process, load_env
from quantlab.llm import DEFAULT_MODEL, chat
from quantlab.strategy_loader import PROJECT_DIR

BRIEF_DIR = PROJECT_DIR / "user_data" / "logs" / "daily_brief"

# 本机 API 绕过系统代理（与 health 同理）
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))

SYSTEM_PROMPT = (
    "你是量化模拟盘的值班风控助手。基于用户提供的运行状态、持仓、近期交易与 24 小时行情，"
    "用中文输出 markdown 日报，固定三段：\n"
    "## 状态摘要（2-3 句：进程/持仓/盈亏概况）\n"
    "## 风险观察（引用数字：回撤、连亏、持仓集中度、异常波动；没有就明说'无异常'）\n"
    "## 今日关注点（最多 3 条，只谈观察与核对事项）\n"
    "禁止：交易建议、行情预测、收益预期。这是 dry-run 模拟盘，资金为虚拟。"
)


def _api_get(path: str, env: dict) -> dict:
    token = base64.b64encode(
        f"{env['FT_API_USERNAME']}:{env['FT_API_PASSWORD']}".encode()).decode()
    request = urllib.request.Request(
        f"{API_BASE}{path}", headers={"Authorization": f"Basic {token}"})
    with _OPENER.open(request, timeout=10) as response:
        return json.load(response)


def market_summary() -> list[str]:
    lines = []
    for file in sorted(DATA_DIR.glob("*-1h.feather")):
        df = pd.read_feather(file)
        if len(df) < 25:
            continue
        last, prev = df["close"].iloc[-1], df["close"].iloc[-25]
        change = last / prev - 1
        pair = file.stem.replace("-1h", "").replace("_", "/")
        lines.append(f"- {pair}: 最新 {last:.4g}，24h {change:+.2%}"
                     f"（数据截至 {df['date'].iloc[-1]:%m-%d %H:%M} UTC）")
    return lines


def build_user_prompt() -> str:
    env = load_env()
    process_ok = check_process()
    log_ok = check_log_fresh()
    lines = [f"巡检: 进程{'正常' if process_ok else '异常'} / 日志心跳{'正常' if log_ok else '异常'}"]
    try:
        profit = _api_get("/profit", env)
        lines.append(
            f"累计: 平仓 {profit.get('closed_trade_count', 0)} 笔 / "
            f"总交易 {profit.get('trade_count', 0)} | "
            f"已实现盈亏 {profit.get('profit_closed_coin', 0):.2f} USDT | "
            f"胜率 {profit.get('winrate', 0) * 100:.1f}% | "
            f"最大回撤 {profit.get('max_drawdown', 0) * 100:.2f}%")
        open_trades = _api_get("/status", env)
        if open_trades:
            lines.append("当前持仓:")
            for t in open_trades:
                lines.append(f"- {t['pair']}: 开仓 {t['open_rate']} @ {t['open_date']} | "
                             f"浮动 {t.get('profit_pct', 0):+.2f}%")
        else:
            lines.append("当前持仓: 空仓")
        recent = _api_get("/trades?limit=20", env).get("trades", [])
        if recent:
            lines.append("最近平仓（至多 20 笔）:")
            for t in recent:
                lines.append(f"- {t['pair']} {t.get('close_date', '')} | "
                             f"{t.get('profit_ratio', 0):+.2%} | {t.get('exit_reason', '')}")
        else:
            lines.append("最近平仓: 无")
    except Exception as error:
        lines.append(f"API 读取失败: {error}（bot 可能未运行）")
    lines.append("")
    lines.append("24 小时行情:")
    lines.extend(market_summary())
    return "\n".join(lines)


def main() -> int:
    today = datetime.now().strftime("%Y-%m-%d")
    prompt = build_user_prompt()
    print(f"生成 {today} 值班日报（{DEFAULT_MODEL}）...")
    analysis = chat(SYSTEM_PROMPT, prompt, max_tokens=1200)
    BRIEF_DIR.mkdir(parents=True, exist_ok=True)
    target = BRIEF_DIR / f"{today}.md"
    target.write_text("\n".join([
        f"# 值班日报 {today}",
        "",
        f"- 生成: {datetime.now():%F %T} | 模型: {DEFAULT_MODEL} | dry-run 模拟盘",
        "",
        "## 原始数据",
        "```",
        prompt,
        "```",
        "",
        analysis,
        "",
    ]))
    print(f"日报: {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
