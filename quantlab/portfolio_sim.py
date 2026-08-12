"""可执行组合模拟器：换手缓冲带 + 行业中性 + 成本的月度调仓组合。

与 factor_eval 的研究口径（IC/分层）互补：本模块回答"按规则实际持有会怎样"。
缓冲带语义（预登记，见迭代计划 v2）：分位进入线以内才买入，
老持仓跌出退出线才卖出——用不对称门槛压换手。
"""

import pandas as pd


def percentile_ranks(row: pd.Series, industry_map: dict | None = None,
                     industry_neutral: bool = False) -> pd.Series:
    """0~1 分位，越小 = 因子越高；行业中性时在行业内计算分位。"""
    valid = row.dropna()
    if industry_neutral and industry_map:
        groups = valid.index.map(lambda t: industry_map.get(t) or "未分类")
        return valid.groupby(groups).rank(ascending=False, pct=True)
    return valid.rank(ascending=False, pct=True)


def target_positions(row: pd.Series, previous: set, enter_pct: float = 0.2,
                     exit_pct: float = 0.4, industry_map: dict | None = None,
                     industry_neutral: bool = False) -> set:
    ranks = percentile_ranks(row, industry_map, industry_neutral)
    keep = {t for t in previous if t in ranks.index and ranks[t] <= exit_pct}
    entries = {t for t in ranks.index if ranks[t] <= enter_pct}
    return keep | entries


def simulate(factor: pd.DataFrame, forward_returns: pd.DataFrame, *,
             enter_pct: float, exit_pct: float, cost_bps: float = 10.0,
             industry_map: dict | None = None, industry_neutral: bool = False,
             min_names: int = 50) -> dict:
    positions: set = set()
    records = []
    for dt in factor.index:
        row = factor.loc[dt]
        if row.notna().sum() < min_names:
            continue
        forward = forward_returns.loc[dt] if dt in forward_returns.index else None
        if forward is None or forward.notna().sum() == 0:
            continue
        new_positions = target_positions(row, positions, enter_pct, exit_pct,
                                         industry_map, industry_neutral)
        if not new_positions:
            continue
        gross = float(forward.reindex(list(new_positions)).mean())
        buys = len(new_positions - positions)
        sells = len(positions - new_positions)
        cost = (buys + sells) / len(new_positions) * cost_bps / 1e4
        records.append({
            "date": dt, "gross": gross, "net": gross - cost,
            "turnover": (buys + sells) / (2 * len(new_positions)),
            "n_holdings": len(new_positions),
        })
        positions = new_positions

    monthly = pd.DataFrame(records).set_index("date")
    equity = (1 + monthly["net"]).cumprod()
    drawdown = float((equity / equity.cummax() - 1).min())
    net = monthly["net"]
    return {
        "monthly": monthly,
        "months": len(monthly),
        "annual_return": float(equity.iloc[-1] ** (12 / len(monthly)) - 1),
        "net_sharpe": float(net.mean() / net.std()) if net.std() > 0 else 0.0,
        "max_drawdown": drawdown,
        "avg_turnover": float(monthly["turnover"].mean()),
        "avg_names": float(monthly["n_holdings"].mean()),
    }
