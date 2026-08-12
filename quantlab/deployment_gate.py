"""部署门槛 G1-G5 机检：研究 PASS 只授予"paper 候选"，部署资格须另过本门。

阈值预登记于迭代 v3 计划 §2（先于任何运行提交），不得因结果修改。
真实输入来自：冻结口径的可交易性模拟（tradable_sim，含成本翻倍压力）+ 基准序列。
"""

import sys
from datetime import datetime

import pandas as pd

from quantlab.strategy_loader import PROJECT_DIR

REPORT = PROJECT_DIR / "docs" / "results" / "14-deployment-gate.md"
FREEZE_DATE = pd.Timestamp("2026-08-12")


def evaluate_gate(metrics: dict) -> list[dict]:
    """输入指标 → G1-G5 逐项判定（纯函数）。"""
    return [
        {"gate": "G1 DSR ≥ 0.95（n_trials 按家族登记数）",
         "value": f"{metrics['dsr']:.3f}", "ok": metrics["dsr"] >= 0.95},
        {"gate": "G2 相对基准年化超额 > 0（可交易口径）",
         "value": f"{metrics['ann_excess']:+.2%}", "ok": metrics["ann_excess"] > 0},
        {"gate": "G3 信息比率 ≥ 0.3",
         "value": f"{metrics['information_ratio']:.2f}",
         "ok": metrics["information_ratio"] >= 0.3},
        {"gate": "G4 成本翻倍（20bps/边）后净夏普 > 0",
         "value": f"{metrics['stress_net_sharpe']:+.3f}",
         "ok": metrics["stress_net_sharpe"] > 0},
        {"gate": "G5 冻结后前向观察 ≥ 12 个月度周期",
         "value": f"{metrics['forward_months']} 期", "ok": metrics["forward_months"] >= 12},
    ]


def information_ratio(portfolio_monthly: pd.Series, benchmark_monthly: pd.Series) -> dict:
    """月频超额 → 年化超额与 IR。"""
    aligned = pd.concat([portfolio_monthly, benchmark_monthly], axis=1).dropna()
    excess = aligned.iloc[:, 0] - aligned.iloc[:, 1]
    ann_excess = float((1 + excess.mean()) ** 12 - 1)
    ir = float(excess.mean() / excess.std() * 12 ** 0.5) if excess.std() > 0 else 0.0
    return {"ann_excess": ann_excess, "information_ratio": ir}


def render(rows: list[dict], context: str) -> str:
    passed = sum(r["ok"] for r in rows)
    lines = [
        "# Deployment Gate 判定（G1-G5）",
        "",
        f"- 日期: {datetime.now():%F %T} | 对象: CN 动量冻结口径（缓冲 20/40 + 行业中性）",
        f"- 上下文: {context}",
        "",
        "| 门槛 | 实际值 | 判定 |",
        "|---|---|---|",
    ]
    for r in rows:
        lines.append(f"| {r['gate']} | {r['value']} | {'✓' if r['ok'] else '✗'} |")
    verdict = ("**通过（{}/5）**".format(passed) if passed == 5
               else f"**未通过（{passed}/5）——维持 paper 候选，不进入真实资金讨论**")
    lines += ["", f"## 结论：{verdict}", "",
              "> 研究 PASS ≠ 部署 PASS。G5 只能靠时间（冻结后真实前向月份），无捷径。"]
    return "\n".join(lines)


def main() -> int:
    from quantlab.cn_data import cn_membership_mask, load_cn_daily, load_industry
    from quantlab.factors import forward_1m, momentum_12_1, month_end
    from quantlab.stats_tests import deflated_sharpe
    from quantlab.tradable_sim import simulate_tradable

    data = load_cn_daily()
    close_monthly = month_end(data["close"])
    factor = momentum_12_1(close_monthly)
    mask = cn_membership_mask(factor.index, data["close"].columns)
    if mask is not None:
        factor = factor.where(mask.reindex(factor.index).fillna(False))
    industry = load_industry()
    industry_map = dict(zip(industry["code"], industry["industry"]))

    base = simulate_tradable(factor, data["close"], volume_daily=data["volume"],
                             industry_map=industry_map)

    # G4 成本翻倍压力：以研究口径模拟（成本参数可调）近似
    from quantlab.portfolio_sim import simulate as research_sim
    forward = forward_1m(close_monthly)
    stress_res = research_sim(factor, forward, enter_pct=0.2, exit_pct=0.4,
                              cost_bps=20, industry_map=industry_map,
                              industry_neutral=True)

    # 基准优先级：沪深 300 指数（价格指数，不含股息）> 点时股池等权（内部基准）
    from quantlab.cn_data import load_index
    index_series = load_index()
    if index_series is not None:
        index_monthly = index_series.resample("ME").last()
        benchmark = index_monthly.pct_change().shift(-1)  # 与 forward 口径对齐（t 行 = t→t+1）
        benchmark_name = "沪深300价格指数（不含股息）"
    else:
        universe_monthly = forward.where(
            mask.reindex(forward.index).fillna(False) if mask is not None else True)
        benchmark = universe_monthly.mean(axis=1)
        benchmark_name = "点时股池等权（内部基准）"
    portfolio_monthly = base["monthly"]["net"]
    benchmark_aligned = benchmark.reindex(portfolio_monthly.index)
    rel = information_ratio(portfolio_monthly, benchmark_aligned)

    forward_months = len([d for d in portfolio_monthly.index if d > FREEZE_DATE])
    metrics = {
        "dsr": deflated_sharpe(base["net_sharpe"], max(base["months"], 2), 9),
        "ann_excess": rel["ann_excess"],
        "information_ratio": rel["information_ratio"],
        "stress_net_sharpe": stress_res["net_sharpe"],
        "forward_months": forward_months,
    }
    context = (f"可交易口径 {base['months']} 个月（年化 {base['annual_return']:+.2%}，"
               f"费用合计 {base['total_fees']:.0f} 元，容量峰值 {base['capacity_peak']:.1%}，"
               f"禁买 {base['blocked_buys']} / 禁卖 {base['blocked_sells']} 次）；"
               f"基准 = {benchmark_name}")
    from quantlab.provenance import stamp
    rows = evaluate_gate(metrics)
    REPORT.write_text(render(rows, context) + f"\n\n---\n溯源: {stamp()}\n")
    print(render(rows, context))
    print(f"\n报告: {REPORT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
