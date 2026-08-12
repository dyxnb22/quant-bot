"""稳健性披露：块自助 p 对照列 + 三候选参数平原（仅披露，不择优）。

预登记见 factor-registry「稳健性披露登记（2026-08-12）」：
- 块自助置换（块长 6 个月）保留 IC 序列的块内自相关，是 NW-p 的稳健性对照；
- 参数平原 = 冻结规则在 enter×exit 邻域的可交易口径净夏普矩阵，
  只披露形态（平原/刀锋），任何点位不得因此被选用，冻结参数（20/40）不变。
"""

import sys
from datetime import datetime

from quantlab.cross_section import rank_ic
from quantlab.deployment_gate import RULES
from quantlab.factor_eval import FACTOR_BUILDERS, MIN_NAMES_PER_MONTH
from quantlab.factors import forward_1m, month_end
from quantlab.stats_tests import (block_permutation_pvalue, newey_west_pvalue,
                                  permutation_pvalue)
from quantlab.strategy_loader import PROJECT_DIR

REPORT = PROJECT_DIR / "docs" / "results" / "19-robustness-disclosure.md"

# 5 个 PASS 因子（登记册现状；判定不在此模块发生）
PASS_FACTORS = [
    ("hs300", "cn", "momentum_12_1"),
    ("hs300", "cn", "low_turnover"),
    ("hs300", "cn", "composite_mom_lto"),
    ("zz500", "cn500", "low_turnover"),
    ("zz500", "cn500", "composite_mom_lto"),
]
ENTER_GRID = (0.15, 0.20, 0.25)
EXIT_GRID = (0.35, 0.40, 0.45)
FROZEN = (0.20, 0.40)


def ic_series(data: dict, mask, factor_name: str):
    factor = FACTOR_BUILDERS[factor_name](data)
    if mask is not None:
        factor = factor.where(mask.reindex(factor.index).fillna(False))
    factor = factor[factor.notna().sum(axis=1) >= MIN_NAMES_PER_MONTH]
    forward = forward_1m(month_end(data["close"]))
    common = factor.index.intersection(forward.dropna(how="all").index)
    return rank_ic(factor.loc[common], forward.loc[common]).dropna()


def block_bootstrap_rows(datasets: dict) -> list[dict]:
    rows = []
    for universe, family, name in PASS_FACTORS:
        data, mask = datasets[universe]
        ic = ic_series(data, mask, name)
        rows.append({
            "universe": universe, "family": family, "factor": name,
            "months": len(ic),
            "nw_p": newey_west_pvalue(ic),
            "perm_p": permutation_pvalue(ic, seed=42),
            "block_p": block_permutation_pvalue(ic, block=6, seed=42),
        })
    return rows


def plateau_grid(rule_key: str, datasets: dict, industry_map: dict) -> dict:
    """规则的 enter×exit 净夏普矩阵（可交易口径，基线成本）。"""
    from quantlab.cn_data import cn_membership_mask
    from quantlab.factors import composite_mom_lto, momentum_12_1
    from quantlab.tradable_sim import simulate_tradable

    rule = RULES[rule_key]
    data, _ = datasets[rule["universe"]]
    close_monthly = month_end(data["close"])
    if rule["factor"] == "momentum":
        factor = momentum_12_1(close_monthly)
    else:
        factor = composite_mom_lto(data["close"], data["turn"])
    from quantlab.cn_data import UNIVERSES
    mask = cn_membership_mask(factor.index, data["close"].columns,
                              UNIVERSES[rule["universe"]]["dir"])
    if mask is not None:
        factor = factor.where(mask.reindex(factor.index).fillna(False))

    grid = {}
    for enter in ENTER_GRID:
        for exit_ in EXIT_GRID:
            result = simulate_tradable(
                factor, data["close"], volume_daily=data["volume"],
                industry_map=industry_map, enter_pct=enter, exit_pct=exit_)
            grid[(enter, exit_)] = {
                "net_sharpe": result["net_sharpe"],
                "annual_return": result["annual_return"],
            }
            print(f"  {rule_key} enter={enter:.0%} exit={exit_:.0%} "
                  f"净夏普 {result['net_sharpe']:+.3f}", flush=True)
    return grid


def render(bootstrap_rows: list[dict], plateaus: dict) -> str:
    lines = [
        "# 稳健性披露：块自助对照 + 参数平原（不择优）",
        "",
        f"- 日期: {datetime.now():%F %T} | 预登记: `factor-registry.md` 稳健性披露登记节",
        "- 性质：**纯披露**。判定协议不变（NW-p 过 BH）；冻结参数（20/40）不变。",
        "",
        "## A. 五个 PASS 因子的块自助置换 p（块长 6 个月）",
        "",
        "| 宇宙 | 因子 | 月数 | NW p（判定用） | 朴素置换 p | 块自助 p | 块自助 <0.05 |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in bootstrap_rows:
        lines.append(
            f"| {r['universe']} | {r['factor']} | {r['months']} "
            f"| {r['nw_p']:.4f} | {r['perm_p']:.4f} | {r['block_p']:.4f} "
            f"| {'✓' if r['block_p'] < 0.05 else '✗'} |")
    lines += [
        "",
        "解读：块自助保留 6 个月块内自相关，p 值一般不小于朴素置换；",
        "若某因子块自助 p 明显劣化（>0.05），说明其显著性依赖逐点独立假设，置信应下调。",
        "",
        "## B. 三候选参数平原（可交易口径净夏普，缓冲 enter×exit 邻域）",
        "",
    ]
    for rule_key, grid in plateaus.items():
        label = RULES[rule_key]["label"]
        lines += [f"### {rule_key}（{label}）", "",
                  "| enter\\exit | " + " | ".join(f"{e:.0%}" for e in EXIT_GRID) + " |",
                  "|---" * (len(EXIT_GRID) + 1) + "|"]
        for enter in ENTER_GRID:
            cells = []
            for exit_ in EXIT_GRID:
                value = grid[(enter, exit_)]["net_sharpe"]
                mark = " ←冻结" if (enter, exit_) == FROZEN else ""
                cells.append(f"{value:+.3f}{mark}")
            lines.append(f"| {enter:.0%} | " + " | ".join(cells) + " |")
        sharpes = [v["net_sharpe"] for v in grid.values()]
        frozen_value = grid[FROZEN]["net_sharpe"]
        all_positive = all(s > 0 for s in sharpes)
        lines += [
            "",
            (f"- 9 点净夏普范围 [{min(sharpes):+.3f}, {max(sharpes):+.3f}]，"
             f"冻结点 {frozen_value:+.3f}；邻域{'全正' if all_positive else '存在非正点'}。"),
            "",
        ]
    lines += [
        "> 预登记约束重申：本表仅用于披露形态。任何'邻域内更优点位'都不得被选用；",
        "> 冻结参数的变更只能走登记册预登记 + 新前向账本重新计时。",
    ]
    return "\n".join(lines)


def main() -> int:
    from quantlab.cn_data import (UNIVERSES, cn_membership_mask, load_cn_daily,
                                  load_industry)
    from quantlab.locking import file_lock

    datasets = {}
    for key in ("hs300", "zz500"):
        universe = UNIVERSES[key]
        with file_lock(universe["lock"]):
            data = load_cn_daily(universe["dir"])
        monthly_index = month_end(data["close"]).index
        mask = cn_membership_mask(monthly_index, data["close"].columns,
                                  universe["dir"])
        datasets[key] = (data, mask)
    industry = load_industry()
    industry_map = dict(zip(industry["code"], industry["industry"]))

    print("A. 块自助对照…", flush=True)
    bootstrap_rows = block_bootstrap_rows(datasets)
    print("B. 参数平原（27 次可交易模拟）…", flush=True)
    plateaus = {key: plateau_grid(key, datasets, industry_map) for key in RULES}

    from quantlab.provenance import stamp
    report = render(bootstrap_rows, plateaus) + f"\n\n---\n溯源: {stamp()}\n"
    REPORT.write_text(report)
    print(report)
    print(f"报告: {REPORT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
