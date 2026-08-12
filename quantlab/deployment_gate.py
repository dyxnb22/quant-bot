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
        {"gate": "G4 成本翻倍（20bps/边，研究口径近似）后净夏普 > 0",
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


def _benchmark_on_fill_intervals(index_series: pd.Series,
                                 monthly: pd.DataFrame,
                                 daily_end) -> pd.Series:
    """基准收益按组合相同的成交日区间计算（P1-05：同风险区间才可比）。"""
    idx = index_series.sort_index().ffill()
    fill_dates = list(monthly["fill_date"])
    boundaries = fill_dates + [daily_end]
    values = idx.reindex(pd.DatetimeIndex(boundaries), method="ffill")
    returns = [float(values.iloc[i + 1] / values.iloc[i] - 1)
               for i in range(len(fill_dates))]
    return pd.Series(returns, index=monthly.index)


def main() -> int:
    from scipy.stats import kurtosis, skew

    from quantlab.cn_data import cn_membership_mask, load_cn_daily, load_index, load_industry
    from quantlab.factors import momentum_12_1, month_end
    from quantlab.forward_ledger import forward_months as ledger_forward_months
    from quantlab.locking import file_lock
    from quantlab.registry import family_trials
    from quantlab.stats_tests import deflated_sharpe
    from quantlab.tradable_sim import simulate_tradable

    with file_lock("cn_data"):
        data = load_cn_daily()
        close_monthly = month_end(data["close"])
        factor = momentum_12_1(close_monthly)
        mask = cn_membership_mask(factor.index, data["close"].columns)
        if mask is not None:
            factor = factor.where(mask.reindex(factor.index).fillna(False))
        industry = load_industry()
        industry_map = dict(zip(industry["code"], industry["industry"]))

        # G1-G4 同引擎（协议 v3）：基线成本 与 成本翻倍（佣金/印花均 ×2）
        base = simulate_tradable(factor, data["close"], volume_daily=data["volume"],
                                 industry_map=industry_map)
        stress = simulate_tradable(factor, data["close"], volume_daily=data["volume"],
                                   industry_map=industry_map,
                                   commission_bps=5.0, stamp_bps=10.0)

        index_series = load_index()
        portfolio_monthly = base["monthly"]["net"]
        if index_series is not None:
            benchmark_aligned = _benchmark_on_fill_intervals(
                index_series, base["monthly"], data["close"].index.max())
            benchmark_name = "沪深300价格指数（不含股息；按相同成交日区间）"
        else:
            benchmark_aligned = pd.Series(float("nan"), index=portfolio_monthly.index)
            benchmark_name = "缺失（指数数据未落地，G2/G3 无法判定）"
        rel = information_ratio(portfolio_monthly, benchmark_aligned)

    net = portfolio_monthly.dropna()
    metrics = {
        "dsr": deflated_sharpe(
            base["net_sharpe"], max(base["months"], 2), family_trials("cn"),
            skew=float(skew(net)) if len(net) > 2 else 0.0,
            kurt=float(kurtosis(net, fisher=False)) if len(net) > 3 else 3.0),
        "ann_excess": rel["ann_excess"],
        "information_ratio": rel["information_ratio"],
        "stress_net_sharpe": stress["net_sharpe"],
        "forward_months": ledger_forward_months(f"{FREEZE_DATE:%Y-%m-%d}T00:00:00+00:00"),
    }
    context = (f"可交易口径 {base['months']} 个月（年化 {base['annual_return']:+.2%}，"
               f"费用 {base['total_fees']:.0f} 元，容量峰值 {base['capacity_peak']:.1%}，"
               f"禁买 {base['blocked_buys']}/禁卖 {base['blocked_sells']}/清算 {base['writeoffs']}）；"
               f"压力口径 = 同引擎佣金印花×2；基准 = {benchmark_name}；"
               f"DSR 用真实偏度/峰度与登记册 n_trials={family_trials('cn')}；"
               f"G5 证据源 = 前向账本（append-only）")
    from quantlab.provenance import stamp
    rows = evaluate_gate(metrics)
    REPORT.write_text(render(rows, context) + f"\n\n---\n溯源: {stamp()}\n")
    print(render(rows, context))
    print(f"\n报告: {REPORT}")
    return 0 if all(r["ok"] for r in rows) else 1  # 未通过 → 非零退出（P1-04）


if __name__ == "__main__":
    sys.exit(main())
