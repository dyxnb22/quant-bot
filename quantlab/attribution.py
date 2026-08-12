"""风格暴露快照：回答"清单赚的是什么钱"。

简版归因（迭代 3）：组合相对股池的动量/流动性分位倾斜 + 行业主动权重。
完整的收益分解（Barra 式因子收益回归）待因子库扩容后升级。
"""

import pandas as pd


def style_snapshot(list_tickers, factor_row: pd.Series,
                   liquidity_row: pd.Series) -> dict:
    """清单在股池中的风格分位（0 = 该风格最强的一端）。"""
    momentum_pct = factor_row.rank(ascending=False, pct=True)
    liquidity_pct = liquidity_row.rank(ascending=False, pct=True)
    return {
        "momentum_pct": float(momentum_pct.reindex(list_tickers).mean()),
        "liquidity_pct": float(liquidity_pct.reindex(list_tickers).mean()),
    }


def industry_active_weights(list_tickers, universe_tickers,
                            industry_map: dict) -> pd.Series:
    """行业主动权重 = 清单行业权重 - 股池行业权重（正 = 超配）。"""
    def weights(tickers):
        series = pd.Series({t: industry_map.get(t) or "未分类" for t in tickers})
        return series.value_counts(normalize=True)

    list_weights = weights(list_tickers)
    universe_weights = weights(universe_tickers)
    return (list_weights.reindex(universe_weights.index.union(list_weights.index))
            .fillna(0.0)
            - universe_weights.reindex(universe_weights.index.union(list_weights.index))
            .fillna(0.0)).sort_values(ascending=False)
