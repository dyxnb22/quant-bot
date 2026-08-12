"""可交易性组合模拟器：次日成交、涨跌停/停牌约束、A 股费用、整手与资金约束。

与 portfolio_sim（研究口径）互补：本模块回答"按真实交易规则，给定名义资金实际拿到多少"。
规则与成本模型已预登记（迭代 v3 计划 §3），不得因结果修改：
- 成交价 = 信号月末后第一个交易日收盘（无盘中数据的诚实近似）
- 收盘涨跌 ≥+9.8% 禁买 / ≤-9.8% 禁卖（以收盘近似"封板不可成交"）；停牌禁买卖
- 佣金 2.5bps（最低 5 元）/边，卖出印花税 5bps，整手 100 股
"""

import pandas as pd

from quantlab.portfolio_sim import target_positions

LIMIT_PCT = 0.098
COMMISSION_BPS = 2.5
MIN_COMMISSION = 5.0
STAMP_TAX_BPS = 5.0
LOT = 100


def _fill_dates(daily_index, signal_dates):
    """每个信号日（月末标签）→ 其后的第一个交易日。"""
    fills = {}
    for signal in signal_dates:
        after = daily_index[daily_index > signal]
        if len(after):
            fills[signal] = after[0]
    return fills


def simulate_tradable(factor: pd.DataFrame, close_daily: pd.DataFrame, *,
                      volume_daily: pd.DataFrame, capital: float = 300_000,
                      enter_pct: float = 0.2, exit_pct: float = 0.4,
                      industry_map: dict | None = None, industry_neutral: bool = True,
                      min_names: int = 50) -> dict:
    daily_index = close_daily.index
    change = close_daily.pct_change()
    fills = _fill_dates(daily_index, factor.index)

    shares: dict[str, float] = {}
    cash = float(capital)
    records = []
    blocked_buys = blocked_sells = too_expensive = 0
    total_fees = 0.0
    prev_value = float(capital)
    capacity_peak = 0.0

    signals = [s for s in factor.index if s in fills
               and factor.loc[s].notna().sum() >= min_names]
    for signal in signals:
        fill_date = fills[signal]
        price = close_daily.loc[fill_date]
        move = change.loc[fill_date]
        vol = volume_daily.loc[fill_date]

        def tradable_price(ticker):
            p = price.get(ticker)
            return None if p is None or pd.isna(p) else float(p)

        # 1) 目标名单（研究口径），随后应用可交易性约束
        row = factor.loc[signal]
        target = target_positions(row, set(shares), enter_pct, exit_pct,
                                  industry_map, industry_neutral)

        # 2) 卖出：非目标持仓；停牌/跌停 → 顺延
        for ticker in sorted(set(shares) - target):
            p = tradable_price(ticker)
            suspended = p is None or (not pd.isna(vol.get(ticker, float("nan")))
                                      and vol.get(ticker) == 0)
            limit_down = (not pd.isna(move.get(ticker, float("nan")))
                          and move.get(ticker) <= -LIMIT_PCT)
            if suspended or limit_down:
                blocked_sells += 1
                continue
            proceeds = shares[ticker] * p
            fee = max(proceeds * COMMISSION_BPS / 1e4, MIN_COMMISSION) \
                + proceeds * STAMP_TAX_BPS / 1e4
            cash += proceeds - fee
            total_fees += fee
            del shares[ticker]

        # 3) 买入：目标新进入；封板/停牌 → 禁买；整手买不起 → 跳过
        stuck = set(shares) - target  # 卖不掉被迫保留的仓位
        planned = sorted(target - set(shares))
        intended_total = len(target | stuck)
        holdings_value = sum(
            s * (tradable_price(t) or 0.0) for t, s in shares.items())
        budget_per_name = (cash + holdings_value) / max(intended_total, 1)
        for ticker in planned:
            p = tradable_price(ticker)
            suspended = p is None or vol.get(ticker, 0) == 0
            limit_up = (not pd.isna(move.get(ticker, float("nan")))
                        and move.get(ticker) >= LIMIT_PCT)
            if suspended or limit_up:
                blocked_buys += 1
                continue
            lots = int(min(budget_per_name, cash) / (p * LOT))
            if lots <= 0:
                too_expensive += 1
                continue
            quantity = lots * LOT
            notional = quantity * p
            fee = max(notional * COMMISSION_BPS / 1e4, MIN_COMMISSION)
            if notional + fee > cash:
                too_expensive += 1
                continue
            cash -= notional + fee
            total_fees += fee
            shares[ticker] = shares.get(ticker, 0) + quantity
            avg_dollar_volume = float(
                (close_daily[ticker] * volume_daily[ticker])
                .rolling(20, min_periods=5).mean().loc[:fill_date].iloc[-1])
            if avg_dollar_volume > 0:
                capacity_peak = max(capacity_peak, notional / avg_dollar_volume)

        # 4) 期末估值：下一个信号的成交日（或数据末端）
        next_signals = [s for s in signals if s > signal]
        value_date = fills[next_signals[0]] if next_signals else daily_index[-1]
        marks = close_daily.loc[:value_date].ffill().loc[value_date]
        portfolio_value = cash + sum(
            qty * float(marks.get(t)) for t, qty in shares.items()
            if not pd.isna(marks.get(t)))
        records.append({
            "date": signal, "fill_date": fill_date,
            "net": portfolio_value / prev_value - 1,
            "n_holdings": len(shares), "cash_ratio": cash / portfolio_value,
        })
        prev_value = portfolio_value

    monthly = pd.DataFrame(records).set_index("date")
    equity = (1 + monthly["net"]).cumprod()
    net = monthly["net"]
    return {
        "monthly": monthly,
        "months": len(monthly),
        "annual_return": float(equity.iloc[-1] ** (12 / len(monthly)) - 1),
        "net_sharpe": float(net.mean() / net.std()) if net.std() > 0 else 0.0,
        "max_drawdown": float((equity / equity.cummax() - 1).min()),
        "blocked_buys": blocked_buys, "blocked_sells": blocked_sells,
        "too_expensive": too_expensive, "total_fees": float(total_fees),
        "capacity_peak": float(capacity_peak),
        "avg_cash_ratio": float(monthly["cash_ratio"].mean()),
    }
