"""因子评估流水线：按登记册预登记协议执行，输出带多重检验校正的判定。

流程（协议见 docs/results/factor-registry.md，先于本模块的任何运行提交）：
逐因子 IC/分层/多空/换手成本 → 半年分段一致性 → 家族内 BH 校正 + DSR(n_trials=家族登记数)
→ PASS / INCONCLUSIVE / REJECTED 判定。
"""

import argparse
import sys
from datetime import datetime

import pandas as pd
from scipy.stats import spearmanr

from quantlab.cross_section import long_short, quantile_portfolios, rank_ic, turnover
from quantlab.factors import (composite_mom_lto, forward_1m, illiquidity,
                              low_turnover, low_volatility, momentum_12_1,
                              month_end, short_reversal_1m, valuation_yield)
from quantlab.registry import family_trials
from quantlab.stats_tests import (benjamini_hochberg, deflated_sharpe,
                                  newey_west_pvalue, newey_west_tstat,
                                  permutation_pvalue)
from quantlab.strategy_loader import PROJECT_DIR

MIN_NAMES_PER_MONTH = 50
COST_BPS = 10.0

FACTOR_BUILDERS = {
    "momentum_12_1": lambda d: momentum_12_1(month_end(d["close"])),
    "short_reversal_1m": lambda d: short_reversal_1m(month_end(d["close"])),
    "low_volatility": lambda d: low_volatility(d["close"]),
    "illiquidity": lambda d: illiquidity(d["close"], d["volume"]),
    # 批次 2/3（需扩展字段，仅 A 股数据管道提供；登记册已预登记）
    "ep": lambda d: valuation_yield(d["pe"]),
    "bp": lambda d: valuation_yield(d["pb"]),
    "sp": lambda d: valuation_yield(d["ps"]),
    "low_turnover": lambda d: low_turnover(d["turn"]),
    "composite_mom_lto": lambda d: composite_mom_lto(d["close"], d["turn"]),
}
BATCH2_FACTORS = ("ep", "bp", "sp", "low_turnover", "composite_mom_lto")


def evaluate_factor(factor: pd.DataFrame, forward: pd.DataFrame,
                    cost_bps: float = COST_BPS) -> dict:
    valid = factor.notna().sum(axis=1) >= MIN_NAMES_PER_MONTH
    factor = factor[valid]
    common = factor.index.intersection(forward.dropna(how="all").index)
    factor, forward = factor.loc[common], forward.loc[common]

    ic = rank_ic(factor, forward).dropna()
    quantiles = quantile_portfolios(factor, forward, quantiles=5)
    net = long_short(quantiles, cost_bps=cost_bps,
                     turnover_series=turnover(factor, quantiles=5))["net"].dropna()

    halves = ic.groupby([ic.index.year, (ic.index.month - 1) // 6]).mean()
    consistency = float((halves > 0).mean()) if len(halves) else 0.0
    layer_means = quantiles.mean()
    monotonicity = float(spearmanr(range(len(layer_means)), layer_means.values).statistic)

    return {
        "months": int(len(ic)),
        "ic_mean": float(ic.mean()),
        "ic_t": float(ic.mean() / ic.std() * len(ic) ** 0.5) if ic.std() > 0 else 0.0,
        "ic_nw_t": newey_west_tstat(ic),
        "nw_p": newey_west_pvalue(ic),
        "perm_p": permutation_pvalue(ic, seed=42),
        "consistency": consistency,
        "net_mean": float(net.mean()),
        "net_sharpe": float(net.mean() / net.std()) if net.std() > 0 else 0.0,
        "n_obs_net": int(len(net)),
        "monotonicity": monotonicity,
        "layers": [float(layer_means[c]) for c in quantiles.columns],
    }


def verdict(metrics: dict, bh_significant: bool) -> str:
    hard_pass = (metrics["consistency"] >= 0.6
                 and metrics["net_mean"] > 0
                 and metrics["monotonicity"] >= 0.8)
    if bh_significant and hard_pass:
        return "PASS（初检）"
    if hard_pass:
        return "INCONCLUSIVE（方向成立但校正后不显著，待更长样本）"
    return "REJECTED（初检）"


def run_family(data: dict, market: str,
               membership_mask: pd.DataFrame | None = None,
               only_factors: list[str] | None = None) -> tuple[list[dict], list[str]]:
    forward = forward_1m(month_end(data["close"]))
    builders = {k: v for k, v in FACTOR_BUILDERS.items()
                if (only_factors is None or k in only_factors)}
    # 默认批次（未显式指定时）只跑数据齐备的价格系因子，批次 2 需显式指定
    if only_factors is None:
        builders = {k: v for k, v in builders.items() if k not in BATCH2_FACTORS}
    missing = [k for k in builders
               if k in BATCH2_FACTORS and not all(
                   f in data for f in ("pe", "pb", "ps", "turn"))]
    if missing:
        raise RuntimeError(f"数据缺少批次 2 所需字段（pe/pb/ps/turn），无法检验: {missing}")
    rows = []
    for name, builder in builders.items():
        factor = builder(data)
        if membership_mask is not None:
            factor = factor.where(membership_mask.reindex(factor.index).fillna(False))
        metrics = evaluate_factor(factor, forward)
        metrics["factor"] = name
        rows.append(metrics)
    # 协议 v3：显著性 = NW-p 过 BH（序列相关稳健）；置换 p 保留为信息列
    significant = benjamini_hochberg([r["nw_p"] for r in rows], alpha=0.05)
    n_trials = family_trials(market)  # 机读登记册，无手工覆盖入口（P1-03）
    verdicts = []
    for row, sig in zip(rows, significant):
        row["bh_significant"] = bool(sig)
        row["n_trials"] = n_trials
        row["dsr"] = deflated_sharpe(row["net_sharpe"], max(row["n_obs_net"], 2), n_trials)
        verdicts.append(verdict(row, sig))
    return rows, verdicts


def render(market_label: str, universe_note: str, rows: list[dict],
           verdicts: list[str]) -> str:
    lines = [
        f"# 因子初检报告：{market_label}",
        "",
        f"- 日期: {datetime.now():%F %T} | 协议与预登记: `docs/results/factor-registry.md`",
        f"- 股池: {universe_note}",
        f"- 家族试验数 n_trials = {rows[0]['n_trials']}（DSR 按此扣减；BH 在本批 {len(rows)} 个假设内）",
        "",
        "| 因子 | 月数 | IC 均值 | IC t | NW t | NW p | 置换 p(信息) | BH 显著(NW) | 分段一致率 | 多空净(月) | 净夏普 | DSR | 单调性 | 判定 |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for row, v in zip(rows, verdicts):
        lines.append(
            f"| {row['factor']} | {row['months']} | {row['ic_mean']:+.4f} | {row['ic_t']:+.2f} "
            f"| {row.get('ic_nw_t', 0):+.2f} | {row.get('nw_p', 1):.3f} "
            f"| {row['perm_p']:.3f} | {'✓' if row['bh_significant'] else '✗'} "
            f"| {row['consistency']:.0%} | {row['net_mean']:+.3%} | {row['net_sharpe']:+.2f} "
            f"| {row['dsr']:.2f} | {row['monotonicity']:+.2f} | {v} |")
    lines += [
        "",
        "分层月均收益（Q1→Q5）：",
        "",
    ]
    for row in rows:
        lines.append(f"- {row['factor']}: " + " / ".join(f"{x:+.3%}" for x in row["layers"]))
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="因子检验（按预登记协议）")
    parser.add_argument("--market", choices=["us", "cn", "cn500", "crypto_cs"], default="us")
    parser.add_argument("--factors", nargs="*", default=None,
                        help="只检验指定因子（复检场景，须先在登记册预登记）")
    parser.add_argument("--report-to", default=None)
    args = parser.parse_args()

    membership_mask = None
    if args.market == "us":
        from quantlab.us_data import load_us_daily, pit_membership_mask
        data = load_us_daily()
        monthly_index = month_end(data["close"]).index
        membership_mask = pit_membership_mask(monthly_index, data["close"].columns)
        label = "美股 S&P 500"
        note = ("S&P 500 点时成员掩码已应用（fja05680/sp500 起止表）；"
                "退市成员价格不可得的残余幸存者偏差仍存在")
        target = PROJECT_DIR / "docs" / "results" / "09-us-factor-tests.md"
    elif args.market == "crypto_cs":
        from quantlab.crypto_cs import TOP_N, crypto_membership_mask, load_crypto_cs
        raw = load_crypto_cs()
        data = {"close": raw["close"], "volume": raw["dollar_volume"]}
        monthly_index = month_end(data["close"]).index
        membership_mask = crypto_membership_mask(
            monthly_index, data["close"].columns, raw["dollar_volume"])
        label = "加密截面（Binance USDT）"
        note = (f"种子池=当前活跃前150（幸存偏差残余已声明）；"
                f"成员=池内每月末 60 日美元成交额前 {TOP_N}（点时重排）")
        target = PROJECT_DIR / "docs" / "results" / "18-crypto-cs-momentum.md"
    else:
        from quantlab.cn_data import UNIVERSES, cn_membership_mask, load_cn_daily
        universe = UNIVERSES["hs300" if args.market == "cn" else "zz500"]
        data = load_cn_daily(universe["dir"])
        monthly_index = month_end(data["close"]).index
        membership_mask = cn_membership_mask(monthly_index, data["close"].columns,
                                             universe["dir"])
        label = f"A 股 {universe['label']}"
        note = (f"{universe['label']} 点时成分掩码已应用（baostock 月末快照）"
                if membership_mask is not None
                else f"{universe['label']} 当前成分（幸存者偏差已声明，见登记册）")
        target = PROJECT_DIR / "docs" / "results" / (
            "10-cn-factor-tests.md" if args.market == "cn" else "16-cn500-factor-tests.md")

    if args.report_to:
        target = PROJECT_DIR / args.report_to
    rows, verdicts = run_family(data, args.market, membership_mask,
                                only_factors=args.factors)
    from quantlab.provenance import stamp
    report = render(label, note, rows, verdicts) + f"\n\n---\n溯源: {stamp()}"
    target.write_text(report + "\n")
    print(report)
    print(f"\n报告: {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
