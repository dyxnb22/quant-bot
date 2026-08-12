"""迭代 1 对比实验：朴素 Q5 / 缓冲带 / 缓冲+行业中性 三口径的 10 年组合模拟。

预登记切换标准（迭代计划 v2，先于运行提交）：
月度清单切换到新口径，当且仅当相对朴素 Q5——净夏普提升 且 最大回撤不恶化 且 月均换手下降。
"""

import sys
from datetime import datetime

from quantlab.cn_data import cn_membership_mask, load_cn_daily, load_industry
from quantlab.factors import forward_1m, momentum_12_1, month_end
from quantlab.portfolio_sim import simulate
from quantlab.strategy_loader import PROJECT_DIR

REPORT = PROJECT_DIR / "docs" / "results" / "12-portfolio-engineering.md"

CONFIGS = {
    "朴素 Q5（现行）": dict(enter_pct=0.2, exit_pct=0.2, industry_neutral=False),
    "缓冲带（进20/出40）": dict(enter_pct=0.2, exit_pct=0.4, industry_neutral=False),
    "缓冲+行业中性": dict(enter_pct=0.2, exit_pct=0.4, industry_neutral=True),
}


def main() -> int:
    data = load_cn_daily()
    close_monthly = month_end(data["close"])
    factor = momentum_12_1(close_monthly)
    forward = forward_1m(close_monthly)
    mask = cn_membership_mask(factor.index, data["close"].columns)
    if mask is not None:
        factor = factor.where(mask.reindex(factor.index).fillna(False))
    industry = load_industry()
    industry_map = dict(zip(industry["code"], industry["industry"]))

    results = {}
    for name, config in CONFIGS.items():
        results[name] = simulate(factor, forward, cost_bps=10,
                                 industry_map=industry_map, min_names=50, **config)

    base = results["朴素 Q5（现行）"]

    def switch_ok(res):
        return (res["net_sharpe"] > base["net_sharpe"]
                and res["max_drawdown"] >= base["max_drawdown"]
                and res["avg_turnover"] < base["avg_turnover"])

    lines = [
        "# 组合工程对比：朴素 Q5 vs 缓冲带 vs 缓冲+行业中性",
        "",
        f"- 日期: {datetime.now():%F %T} | 因子: momentum_12_1 | 样本: 10 年点时成分 | 成本: 10bps/边",
        "- 预登记切换标准: 净夏普 ↑ 且 最大回撤不恶化 且 月均换手 ↓（三条同时满足）",
        "",
        "| 口径 | 月数 | 年化收益 | 净夏普(月) | 最大回撤 | 月均换手 | 平均持仓数 | 达标 |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for name, res in results.items():
        flag = "—基准—" if name.startswith("朴素") else ("✓ 达标" if switch_ok(res) else "✗")
        lines.append(
            f"| {name} | {res['months']} | {res['annual_return']:+.2%} "
            f"| {res['net_sharpe']:+.3f} | {res['max_drawdown']:.2%} "
            f"| {res['avg_turnover']:.1%} | {res['avg_names']:.0f} | {flag} |")

    qualified = [n for n, r in results.items()
                 if not n.startswith("朴素") and switch_ok(r)]
    if qualified:
        best = max(qualified, key=lambda n: results[n]["net_sharpe"])
        decision = f"**切换到「{best}」**（达标口径中净夏普最高），月度清单工具随之升级。"
    else:
        decision = "**维持朴素 Q5**：无口径同时满足三条标准，改动不予采纳。"
    lines += ["", "## 决策（按预登记标准自动判定）", "", decision]

    REPORT.write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    print(f"\n报告: {REPORT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
