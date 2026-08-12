"""LLM 交易复盘：聚合回测交易记录 → LLM 归纳模式与可检验假设 → 报告落盘。

方法论边界（为什么是"复盘"而不是"LLM 回测"）：
主流 LLM 的训练语料覆盖历史行情时段，让 LLM 对历史 K 线做交易决策相当于开卷考试，
成绩不可外推（数据污染）。本模块只让 LLM 做归因分析与假设生成——
产出的每条假设都必须经 walk-forward（make wf）检验后才有资格谈部署。
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

from quantlab.backtest_io import load_export_zip
from quantlab.llm import DEFAULT_MODEL, chat
from quantlab.strategy_loader import PROJECT_DIR

RESULTS_DIR = PROJECT_DIR / "user_data" / "backtest_results"
REPORT_TARGET = PROJECT_DIR / "docs" / "results" / "05-llm-trade-review.md"

DISCLAIMER = (
    "> **免责与边界**：本报告由 LLM 基于历史回测交易记录生成，属于归因分析与假设生成，"
    "不构成对未来收益的预测。文中任何假设在部署前必须通过 walk-forward 验证（`make wf`）"
    "并满足风险政策审计（`make audit`）。\n"
)

SYSTEM_PROMPT = (
    "你是一名资深量化策略分析师与风控顾问。用户会给你一个加密货币策略的回测交易聚合统计。"
    "请用中文输出 markdown 分析报告，包含：\n"
    "1. 亏损集中来源的定量归因（哪类出场、哪些币对、什么持仓时长在亏钱）；\n"
    "2. 可识别的行为模式（如止损过频、持有亏损过久等），引用给出的数字；\n"
    "3. 恰好 3 条可检验的改进假设：每条必须能翻译成明确的规则改动（指标/阈值/出场逻辑），"
    "并说明预期改善的指标与检验方式（walk-forward 样本外拼接收益）；\n"
    "4. 不要给出任何'预期收益率'或对未来行情的预测；不要建议加杠杆。"
)


def aggregate_trades(trades: list[dict]) -> dict:
    stats = {
        "n": len(trades), "wins": 0, "winrate": 0.0, "total_profit_abs": 0.0,
        "by_exit_reason": {}, "by_pair": {},
        "avg_duration_win_min": 0.0, "avg_duration_loss_min": 0.0,
        "best": [], "worst": [],
    }
    if not trades:
        return stats
    win_durations, loss_durations = [], []
    for trade in trades:
        profit_ratio = trade.get("profit_ratio", 0.0)
        profit_abs = trade.get("profit_abs", 0.0)
        stats["total_profit_abs"] += profit_abs
        if profit_ratio > 0:
            stats["wins"] += 1
            win_durations.append(trade.get("trade_duration", 0))
        else:
            loss_durations.append(trade.get("trade_duration", 0))
        for key, bucket_name in (("exit_reason", "by_exit_reason"), ("pair", "by_pair")):
            bucket = stats[bucket_name].setdefault(
                trade.get(key, "unknown"), {"n": 0, "total_abs": 0.0})
            bucket["n"] += 1
            bucket["total_abs"] += profit_abs
    stats["winrate"] = stats["wins"] / stats["n"]
    if win_durations:
        stats["avg_duration_win_min"] = sum(win_durations) / len(win_durations)
    if loss_durations:
        stats["avg_duration_loss_min"] = sum(loss_durations) / len(loss_durations)
    by_profit = sorted(trades, key=lambda t: t.get("profit_ratio", 0.0))
    keep = ("pair", "open_date", "profit_ratio", "profit_abs", "exit_reason", "trade_duration")
    stats["worst"] = [{k: t.get(k) for k in keep} for t in by_profit[:10]]
    stats["best"] = [{k: t.get(k) for k in keep} for t in reversed(by_profit[-10:])]
    return stats


def build_prompt(strategy: str, source: str, stats: dict) -> str:
    lines = [
        f"策略: {strategy} | 数据来源: 回测导出 {source}（dry-run 假设，OKX 现货费率）",
        f"总笔数: {stats['n']} | 胜率: {stats['winrate']:.1%} | 总盈亏: {stats['total_profit_abs']:.1f} USDT",
        f"赢家平均持仓: {stats['avg_duration_win_min']:.0f} 分钟 | 输家平均持仓: {stats['avg_duration_loss_min']:.0f} 分钟",
        "", "按出场原因（笔数 / 累计盈亏 USDT）:",
    ]
    for reason, bucket in sorted(stats["by_exit_reason"].items(),
                                 key=lambda kv: kv[1]["total_abs"]):
        lines.append(f"- {reason}: {bucket['n']} 笔 / {bucket['total_abs']:.1f}")
    lines.append("")
    lines.append("按币对（笔数 / 累计盈亏 USDT）:")
    for pair, bucket in sorted(stats["by_pair"].items(), key=lambda kv: kv[1]["total_abs"]):
        lines.append(f"- {pair}: {bucket['n']} 笔 / {bucket['total_abs']:.1f}")
    for title, key in (("最差 10 笔", "worst"), ("最好 10 笔", "best")):
        lines.append("")
        lines.append(f"{title}:")
        for t in stats[key]:
            lines.append(
                f"- {t['pair']} {t['open_date']} | {t['profit_ratio']:+.2%} "
                f"({t['profit_abs']:+.1f} USDT) | {t['exit_reason']} | {t['trade_duration']} 分钟")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="LLM 交易复盘（基于回测导出）")
    parser.add_argument("--strategy", default="EmaRsiStrategy")
    parser.add_argument("--zip", default=None, help="回测导出 zip 路径（默认取最新）")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    args = parser.parse_args()

    if args.zip:
        zip_path = Path(args.zip)
    else:
        zips = sorted(RESULTS_DIR.glob("*.zip"), key=lambda p: p.stat().st_mtime)
        if not zips:
            print(f"未找到回测导出：{RESULTS_DIR}（先运行 make backtest）")
            return 1
        zip_path = zips[-1]

    data = load_export_zip(zip_path)
    if args.strategy not in data.get("strategy", {}):
        print(f"{zip_path.name} 中没有策略 {args.strategy} 的结果，"
              f"可选: {list(data.get('strategy', {}))}")
        return 1
    trades = data["strategy"][args.strategy].get("trades", [])
    stats = aggregate_trades(trades)
    print(f"输入: {zip_path.name} | {args.strategy} | {stats['n']} 笔交易，调用 {args.model} ...")

    analysis = chat(SYSTEM_PROMPT, build_prompt(args.strategy, zip_path.name, stats))

    timestamp = datetime.now().strftime("%F %T")
    report = "\n".join([
        "# LLM 交易复盘报告",
        "",
        f"- 生成时间: {timestamp} | 模型: {args.model}",
        f"- 输入: `{zip_path.name}` 中 {args.strategy} 的 {stats['n']} 笔回测交易（聚合后投喂）",
        "",
        DISCLAIMER,
        "---",
        "",
        analysis,
        "",
    ])
    REPORT_TARGET.parent.mkdir(parents=True, exist_ok=True)
    REPORT_TARGET.write_text(report)
    print(f"报告: {REPORT_TARGET}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
