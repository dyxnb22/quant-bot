"""日频/月频截面因子回测引擎：IC、分层组合、多空、换手与成本。

输入约定：factor 与 forward_returns 均为宽表（index=日期, columns=标的），
factor 在 t 期的值只允许使用 t 期及之前的信息，预测 t→t+1 的 forward_returns。
（无未来函数的责任在因子构造侧，本引擎按上述约定对齐。）
"""

import numpy as np
import pandas as pd


def rank_ic(factor: pd.DataFrame, forward_returns: pd.DataFrame) -> pd.Series:
    """逐期 Spearman rank IC（因子截面排名与未来收益截面排名的相关）。"""
    common = factor.index.intersection(forward_returns.index)
    f_rank = factor.loc[common].rank(axis=1)
    r_rank = forward_returns.loc[common].rank(axis=1)
    return f_rank.corrwith(r_rank, axis=1)


def _quantile_labels(factor: pd.DataFrame, quantiles: int) -> pd.DataFrame:
    return factor.apply(
        lambda row: pd.qcut(row, quantiles, labels=False, duplicates="drop"),
        axis=1)


def quantile_portfolios(factor: pd.DataFrame, forward_returns: pd.DataFrame,
                        quantiles: int = 5) -> pd.DataFrame:
    """各分层等权组合的逐期收益（Q1 = 因子最小层，Q{n} = 最大层）。"""
    common = factor.index.intersection(forward_returns.index)
    labels = _quantile_labels(factor.loc[common], quantiles)
    returns = forward_returns.loc[common]
    out = {}
    for q in range(quantiles):
        out[f"Q{q + 1}"] = returns.where(labels == q).mean(axis=1)
    return pd.DataFrame(out)


def turnover(factor: pd.DataFrame, quantiles: int = 5) -> pd.Series:
    """顶层（做多层）组合的逐期换手率：新进入标的占当期持仓的比例。"""
    labels = _quantile_labels(factor, quantiles)
    top = labels == quantiles - 1
    previous = top.shift(1, fill_value=False)
    new_entries = (top & ~previous).sum(axis=1)
    holdings = top.sum(axis=1)
    return (new_entries / holdings.replace(0, np.nan)).fillna(0.0)


def long_short(quantile_returns: pd.DataFrame, cost_bps: float = 10.0,
               turnover_series: pd.Series | None = None) -> pd.DataFrame:
    """顶层做多、底层做空的多空组合，扣除换手成本（双腿）。

    成本模型：每期成本 = 换手率 × 2 腿 × cost_bps；未提供换手率时按全换手保守估计。
    """
    columns = list(quantile_returns.columns)
    gross = quantile_returns[columns[-1]] - quantile_returns[columns[0]]
    if turnover_series is None:
        turnover_series = pd.Series(1.0, index=gross.index)
    cost = turnover_series.reindex(gross.index).fillna(1.0) * 2 * cost_bps / 1e4
    return pd.DataFrame({"gross": gross, "net": gross - cost})
