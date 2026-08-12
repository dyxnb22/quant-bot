"""价格系因子库 + 端到端冒烟入口。

因子约定：输入日频 close 宽表，输出月度（月末）因子宽表；
t 期因子只用 t 期及之前的数据（无未来函数责任在此层）。
"""

import argparse
import sys
from datetime import datetime

import pandas as pd

from quantlab.cross_section import long_short, quantile_portfolios, rank_ic, turnover
from quantlab.stats_tests import deflated_sharpe, permutation_pvalue
from quantlab.strategy_loader import PROJECT_DIR
from quantlab.us_data import load_us_daily

SMOKE_REPORT = PROJECT_DIR / "docs" / "results" / "08-us-pipeline-smoke.md"
MIN_NAMES_PER_MONTH = 100


def month_end(close_daily: pd.DataFrame) -> pd.DataFrame:
    return close_daily.resample("ME").last()


def momentum_12_1(close_monthly: pd.DataFrame) -> pd.DataFrame:
    """12-1 动量：过去 12 个月收益，剔除最近 1 个月（短期反转噪声）。"""
    return close_monthly.shift(1) / close_monthly.shift(12) - 1


def short_reversal_1m(close_monthly: pd.DataFrame) -> pd.DataFrame:
    """1 月短反转：负的最近一个月收益（上月输家预期反弹）。"""
    return -(close_monthly / close_monthly.shift(1) - 1)


def low_volatility(close_daily: pd.DataFrame, window: int = 60) -> pd.DataFrame:
    """低波动：负的过去 60 交易日日收益标准差（低波动异象为正向溢价）。"""
    volatility = close_daily.pct_change().rolling(window, min_periods=40).std()
    return -volatility.resample("ME").last()


def illiquidity(close_daily: pd.DataFrame, volume_daily: pd.DataFrame,
                window: int = 60) -> pd.DataFrame:
    """非流动性：负的过去 60 交易日日均成交额对数（流动性溢价方向）。"""
    import numpy as np
    dollar_volume = (close_daily * volume_daily).rolling(window, min_periods=40).mean()
    return -np.log(dollar_volume).resample("ME").last()


def valuation_yield(ratio_daily: pd.DataFrame) -> pd.DataFrame:
    """估值收益率：1/估值比率的月末值（EP=1/PE、BP=1/PB、SP=1/PS）。

    比率 ≤ 0（亏损/负资产）时收益率为负，保留其排序信息；除零得到的 inf 置为 NaN。
    """
    import numpy as np
    yields = 1.0 / ratio_daily
    return yields.replace([np.inf, -np.inf], float("nan")).resample("ME").last()


def low_turnover(turn_daily: pd.DataFrame, window: int = 60) -> pd.DataFrame:
    """低换手：负的 60 日平均换手率月末值（低换手溢价方向）。"""
    return -turn_daily.rolling(window, min_periods=40).mean().resample("ME").last()


def forward_1m(close_monthly: pd.DataFrame) -> pd.DataFrame:
    """t 期行 = t → t+1 的未来一个月收益。"""
    return close_monthly.shift(-1) / close_monthly - 1


def main() -> int:
    parser = argparse.ArgumentParser(description="美股截面管道冒烟（12-1 动量）")
    parser.add_argument("--cost-bps", type=float, default=10.0)
    args = parser.parse_args()

    close_monthly = month_end(load_us_daily()["close"])
    factor = momentum_12_1(close_monthly)
    forward = forward_1m(close_monthly)

    valid = factor.notna().sum(axis=1) >= MIN_NAMES_PER_MONTH
    factor, forward = factor[valid], forward[valid]
    factor = factor.iloc[:-1]  # 最后一期无未来收益
    forward = forward.loc[factor.index]

    ic = rank_ic(factor, forward)
    quantiles = quantile_portfolios(factor, forward, quantiles=5)
    ls = long_short(quantiles, cost_bps=args.cost_bps,
                    turnover_series=turnover(factor, quantiles=5))
    net = ls["net"].dropna()

    ic_mean, ic_std = ic.mean(), ic.std()
    ic_t = ic_mean / ic_std * (len(ic) ** 0.5)
    ic_p = permutation_pvalue(ic, seed=42)
    net_sharpe = net.mean() / net.std() if net.std() > 0 else 0.0
    dsr = deflated_sharpe(net_sharpe, n_obs=len(net), n_trials=1)

    lines = [
        "# 美股截面管道冒烟报告：12-1 动量",
        "",
        f"- 日期: {datetime.now():%F %T} | 股池: S&P 500 当前成分（{factor.shape[1]} 标的）",
        f"- 样本: {factor.index[0]:%Y-%m} ~ {factor.index[-1]:%Y-%m}（{len(factor)} 个月度截面）",
        f"- 成本假设: {args.cost_bps:.0f} bps/边 × 双腿 × 顶层换手率",
        "",
        "> **定位声明**：本报告是管道验证（引擎/数据/统计三件套能端到端跑通），"
        "**不构成因子有效性结论**——样本仅约 3 年、股池含幸存者偏差（当前成分回看，"
        "已退市标的缺席，收益系统性偏乐观）、且未做多窗口 OOS。正式检验见阶段 B（预登记标准）。",
        "",
        "## 结果",
        "",
        f"| 指标 | 值 |",
        f"|---|---|",
        f"| rank IC 均值 | {ic_mean:+.4f} |",
        f"| IC t 值 | {ic_t:+.2f} |",
        f"| IC 置换检验 p（单侧） | {ic_p:.3f} |",
        f"| 多空净收益（月均） | {net.mean():+.3%} |",
        f"| 多空净夏普（月频） | {net_sharpe:+.3f} |",
        f"| DSR（trials=1，即 PSR） | {dsr:.3f} |",
        f"| 分层月均收益 Q1→Q5 | {' / '.join(f'{quantiles[c].mean():+.3%}' for c in quantiles.columns)} |",
        "",
        "## 管道验证清单",
        "",
        "- [x] 数据: S&P 500 日频 4 年，覆盖率 99%（7 标的下载缺失，NaN 处理）",
        "- [x] 引擎: rank IC / 分层 / 换手 / 成本全链路",
        "- [x] 统计: 置换检验 + DSR 接入（正式检验将按因子登记册计入 n_trials）",
        "",
        "后续（阶段 B）：短反转/低波/流动性因子 → 预登记标准 → 滚动 OOS → BH 校正。",
    ]
    SMOKE_REPORT.write_text("\n".join(lines))
    print("\n".join(lines[6:]))
    print(f"\n报告: {SMOKE_REPORT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
