"""CN 动量月度调仓研究清单：PASS 因子（11 号复检）的落地形态。

这不是交易系统：A 股个人自动化受限，本工具输出研究清单与跟踪记录，
执行与否是人的决策。清单与跟踪历史提交入库（记录本身即研究产品）。
"""

import argparse
import json
import sys
from datetime import datetime

import pandas as pd

from quantlab.attribution import industry_active_weights, style_snapshot
from quantlab.cn_data import cn_membership_mask, load_cn_daily, load_industry
from quantlab.factors import momentum_12_1, month_end
from quantlab.portfolio_sim import target_positions
from quantlab.strategy_loader import PROJECT_DIR

MIN_UNIVERSE = 250  # 股池小于此值视为数据不完整（如下载中断），拒绝生成清单

RESEARCH_DIR = PROJECT_DIR / "docs" / "research" / "cn-momentum"
STATE_FILE = RESEARCH_DIR / "state.json"
TRACKING_FILE = RESEARCH_DIR / "tracking.md"
CONCENTRATION_WARN = 0.30
STALENESS_DAYS = 7

DISCLAIMER = ("> 本清单为个人研究产物（依据 `docs/results/11` 号复检通过的动量因子），"
              "不构成投资建议；数据与模型均可能出错，据此操作风险自担。")


def select_top_quintile(factor_row: pd.Series) -> pd.Series:
    """按因子值取最高五分位，降序返回。"""
    valid = factor_row.dropna()
    labels = pd.qcut(valid, 5, labels=False, duplicates="drop")
    return valid[labels == labels.max()].sort_values(ascending=False)


def industry_weights(tickers, industry_map: dict) -> pd.Series:
    industries = pd.Series({t: industry_map.get(t) or "未分类" for t in tickers})
    return industries.value_counts(normalize=True)


def avg_pairwise_correlation(close_daily: pd.DataFrame, tickers, window: int = 60) -> float:
    returns = close_daily[list(tickers)].tail(window + 1).pct_change().dropna(how="all")
    corr = returns.corr()
    n = len(corr)
    if n < 2:
        return float("nan")
    return float((corr.sum().sum() - n) / (n * (n - 1)))


def realized_performance(prev_tickers, universe, close_monthly: pd.DataFrame,
                         from_month: str, to_month: str) -> dict | None:
    """按明确月份标签结算（P1-11：不再取"面板最后两行"，漏月可被察觉）。"""
    labels = {f"{d:%Y-%m}": d for d in close_monthly.index}
    if from_month not in labels or to_month not in labels:
        return None
    start, end = labels[from_month], labels[to_month]
    returns = close_monthly.loc[end] / close_monthly.loc[start] - 1
    list_return = float(returns.reindex(prev_tickers).mean())
    benchmark_return = float(returns.reindex(universe).mean())
    gap = (end.year * 12 + end.month) - (start.year * 12 + start.month)
    return {"list_return": list_return, "benchmark_return": benchmark_return,
            "excess": list_return - benchmark_return, "months_gap": gap}


def main() -> int:
    from quantlab.locking import file_lock

    parser = argparse.ArgumentParser(description="生成 CN 动量月度研究清单")
    parser.parse_args()

    with file_lock("cn_data"):
        return _run()


def _run() -> int:
    data = load_cn_daily()
    close_daily = data["close"]
    age_days = (datetime.now() - close_daily.index[-1]).days
    if age_days > STALENESS_DAYS:
        print(f"警告: 行情数据距今 {age_days} 天（> {STALENESS_DAYS}），"
              f"建议先 make cn-data-refresh", flush=True)

    close_monthly = month_end(close_daily)
    factor = momentum_12_1(close_monthly)
    latest = factor.index[-1]
    month_key = f"{latest:%Y-%m}"

    mask = cn_membership_mask(factor.index, close_daily.columns)
    row = factor.loc[latest]
    if mask is not None:
        row = row[mask.loc[latest].reindex(row.index).fillna(False)]
    if row.notna().sum() < MIN_UNIVERSE:
        print(f"错误: 当前有效股池仅 {row.notna().sum()} 只（< {MIN_UNIVERSE}），"
              f"疑似数据不完整（下载中断？），拒绝生成清单。先完成 make cn-data-refresh")
        return 1

    industry = load_industry()
    industry_map = dict(zip(industry["code"], industry["industry"]))
    name_map = dict(zip(industry["code"], industry["code_name"]))

    # 口径：缓冲带（进20/出40）+ 行业中性（12 号报告按预登记标准判定切换；参数已冻结）
    state = json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {}
    previous_months = [m for m in sorted(state) if m < month_key]
    previous_holdings = set(state[previous_months[-1]]) if previous_months else set()
    selected = target_positions(row, previous_holdings, enter_pct=0.2, exit_pct=0.4,
                                industry_map=industry_map, industry_neutral=True)
    top = row.reindex(list(selected)).dropna().sort_values(ascending=False)
    weights = industry_weights(top.index, industry_map)
    correlation = avg_pairwise_correlation(close_daily, top.index)

    RESEARCH_DIR.mkdir(parents=True, exist_ok=True)

    # 跟踪上期清单表现（按明确月份标签结算；跨月缺口显式标注）
    tracking_row = None
    if previous_months:
        prev_month = previous_months[-1]
        universe = list(row.index)
        perf = realized_performance(state[prev_month], universe, close_monthly,
                                    prev_month, month_key)
        if perf:
            gap_note = "" if perf["months_gap"] == 1 else f"（跨 {perf['months_gap']} 月）"
            tracking_row = (f"| {prev_month}{gap_note} | {len(state[prev_month])} "
                            f"| {perf['list_return']:+.2%} | {perf['benchmark_return']:+.2%} "
                            f"| {perf['excess']:+.2%} |")

    lines = [
        f"# CN 动量研究清单 {month_key}",
        "",
        f"- 生成: {datetime.now():%F %T} | 因子: momentum_12_1（{latest:%Y-%m} 月末截面）",
        "- 口径: 缓冲带（进20/出40）+ 行业中性（依据 12 号组合工程对比）",
        (f"- 股池: 沪深 300 点时成分 {row.notna().sum()} 只 | 清单: {len(top)} 只"
         f"（保留老持仓 {len(selected & previous_holdings)} 只）"),
        (f"- 组合风险: 最大行业权重 {weights.iloc[0]:.0%}（{weights.index[0]}）"
         f"{' ⚠ 超 30% 集中度警戒' if weights.iloc[0] > CONCENTRATION_WARN else ''} | "
         f"60 日平均两两相关 {correlation:.2f}"),
        "",
        DISCLAIMER,
        "",
        "| # | 代码 | 名称 | 12-1 动量 | 行业 |",
        "|---|---|---|---|---|",
    ]
    for rank, (ticker, value) in enumerate(top.items(), 1):
        lines.append(f"| {rank} | {ticker} | {name_map.get(ticker, '')} "
                     f"| {value:+.1%} | {industry_map.get(ticker) or '未分类'} |")
    lines += ["", "行业分布：", ""]
    for name, weight in weights.items():
        lines.append(f"- {name}: {weight:.0%}")

    # 风格归因段：清单赚的是什么钱（迭代 3）
    liquidity_row = ((close_daily * data["volume"]).rolling(60, min_periods=40)
                     .mean().iloc[-1].reindex(row.index))
    snapshot = style_snapshot(list(top.index), row, liquidity_row)
    active = industry_active_weights(list(top.index), list(row.dropna().index), industry_map)
    lines += [
        "", "## 风格归因（相对股池）", "",
        f"- 动量分位: {snapshot['momentum_pct']:.0%}（0% = 股池最高动量端；清单按设计应显著偏高动量）",
        f"- 流动性分位: {snapshot['liquidity_pct']:.0%}（<50% 偏大盘活跃票，>50% 偏小票——警惕隐性小票暴露）",
        "- 行业主动权重（超配前 3 / 低配前 3）：",
    ]
    for name, value in list(active.head(3).items()) + list(active.tail(3).items()):
        lines.append(f"  - {name}: {value:+.1%}")
    (RESEARCH_DIR / f"{month_key}.md").write_text("\n".join(lines) + "\n")

    if not TRACKING_FILE.exists():
        TRACKING_FILE.write_text(
            "# 清单表现跟踪（次月自动回填）\n\n"
            "| 清单月份 | 名单数 | 实现月收益 | 基准收益 | 超额 |\n|---|---|---|---|---|\n")
    if tracking_row and tracking_row not in TRACKING_FILE.read_text():
        TRACKING_FILE.write_text(TRACKING_FILE.read_text() + tracking_row + "\n")

    state[month_key] = list(top.index)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=1))

    # 前向账本（append-only，Gate G5 的唯一证据源）
    from quantlab.forward_ledger import append_entry
    if append_entry(month_key, list(top.index), note="缓冲20/40+行业中性（冻结口径）"):
        print("前向账本: 已追加本月条目")

    print(f"清单: {RESEARCH_DIR / f'{month_key}.md'}（{len(top)} 只）")
    print(f"最大行业: {weights.index[0]} {weights.iloc[0]:.0%} | 平均相关 {correlation:.2f}")
    if tracking_row:
        print(f"已回填上期表现: {tracking_row}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
