"""CN 动量月度调仓研究清单：PASS 因子（11 号复检）的落地形态。

这不是交易系统：A 股个人自动化受限，本工具输出研究清单与跟踪记录，
执行与否是人的决策。清单与跟踪历史提交入库（记录本身即研究产品）。
"""

import argparse
import json
import sys
from datetime import datetime, timedelta

import pandas as pd

from quantlab.cn_data import cn_membership_mask, load_cn_daily, load_industry
from quantlab.factors import momentum_12_1, month_end
from quantlab.strategy_loader import PROJECT_DIR

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


def realized_performance(prev_tickers, universe, close_monthly: pd.DataFrame) -> dict:
    """上期清单从上月末到最新月末的等权收益 vs 成分等权基准。"""
    window = close_monthly.iloc[-2:]
    returns = window.iloc[-1] / window.iloc[0] - 1
    list_return = float(returns.reindex(prev_tickers).mean())
    benchmark_return = float(returns.reindex(universe).mean())
    return {"list_return": list_return, "benchmark_return": benchmark_return,
            "excess": list_return - benchmark_return}


def main() -> int:
    parser = argparse.ArgumentParser(description="生成 CN 动量月度研究清单")
    parser.parse_args()

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
    top = select_top_quintile(row)

    industry = load_industry()
    industry_map = dict(zip(industry["code"], industry["industry"]))
    name_map = dict(zip(industry["code"], industry["code_name"]))
    weights = industry_weights(top.index, industry_map)
    correlation = avg_pairwise_correlation(close_daily, top.index)

    RESEARCH_DIR.mkdir(parents=True, exist_ok=True)
    state = json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {}

    # 跟踪上期清单表现（若上期存在且不是本月）
    tracking_row = None
    previous_months = [m for m in sorted(state) if m < month_key]
    if previous_months:
        prev_month = previous_months[-1]
        universe = list(row.index)
        perf = realized_performance(state[prev_month], universe, close_monthly)
        tracking_row = (f"| {prev_month} | {len(state[prev_month])} "
                        f"| {perf['list_return']:+.2%} | {perf['benchmark_return']:+.2%} "
                        f"| {perf['excess']:+.2%} |")

    lines = [
        f"# CN 动量研究清单 {month_key}",
        "",
        f"- 生成: {datetime.now():%F %T} | 因子: momentum_12_1（{latest:%Y-%m} 月末截面）",
        f"- 股池: 沪深 300 点时成分 {row.notna().sum()} 只 | 清单: Q5 共 {len(top)} 只",
        f"- 组合风险: 最大行业权重 {weights.iloc[0]:.0%}（{weights.index[0]}）"
        f"{' ⚠ 超 30% 集中度警戒' if weights.iloc[0] > CONCENTRATION_WARN else ''} | "
        f"60 日平均两两相关 {correlation:.2f}",
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
    (RESEARCH_DIR / f"{month_key}.md").write_text("\n".join(lines) + "\n")

    if not TRACKING_FILE.exists():
        TRACKING_FILE.write_text(
            "# 清单表现跟踪（次月自动回填）\n\n"
            "| 清单月份 | 名单数 | 实现月收益 | 基准收益 | 超额 |\n|---|---|---|---|---|\n")
    if tracking_row and tracking_row not in TRACKING_FILE.read_text():
        TRACKING_FILE.write_text(TRACKING_FILE.read_text() + tracking_row + "\n")

    state[month_key] = list(top.index)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=1))

    print(f"清单: {RESEARCH_DIR / f'{month_key}.md'}（{len(top)} 只）")
    print(f"最大行业: {weights.index[0]} {weights.iloc[0]:.0%} | 平均相关 {correlation:.2f}")
    if tracking_row:
        print(f"已回填上期表现: {tracking_row}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
