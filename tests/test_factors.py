import numpy as np
import pandas as pd

from quantlab.factors import (forward_1m, illiquidity, low_volatility,
                              momentum_12_1, month_end, short_reversal_1m)


def make_monthly(n=20):
    dates = pd.date_range("2023-01-31", periods=n, freq="ME")
    # 三只票：强涨/横盘/下跌
    up = 100 * (1.05 ** np.arange(n))
    flat = np.full(n, 100.0)
    down = 100 * (0.97 ** np.arange(n))
    return pd.DataFrame({"UP": up, "FLAT": flat, "DOWN": down}, index=dates)


def test_momentum_ranks_match_trends():
    close = make_monthly()
    factor = momentum_12_1(close)
    row = factor.iloc[-1]
    assert row["UP"] > row["FLAT"] > row["DOWN"]


def test_momentum_skips_recent_month():
    """12-1 动量不含最近一个月：最后一个月的暴涨不应改变因子值。"""
    close = make_monthly()
    spiked = close.copy()
    spiked.iloc[-1, spiked.columns.get_loc("FLAT")] = 500.0
    base = momentum_12_1(close).iloc[-1]["FLAT"]
    with_spike = momentum_12_1(spiked).iloc[-1]["FLAT"]
    assert base == with_spike


def test_forward_return_alignment():
    close = make_monthly()
    forward = forward_1m(close)
    expected = close["UP"].iloc[6] / close["UP"].iloc[5] - 1
    assert abs(forward["UP"].iloc[5] - expected) < 1e-12
    assert forward.iloc[-1].isna().all(), "最后一期没有未来收益"


def test_month_end_resample():
    daily = pd.DataFrame(
        {"A": np.arange(1, 63, dtype=float)},
        index=pd.date_range("2024-01-01", periods=62, freq="B"))
    monthly = month_end(daily)
    assert monthly.index.is_month_end.all()


def test_short_reversal_negates_last_month():
    close = make_monthly()
    factor = short_reversal_1m(close)
    row = factor.iloc[-1]
    assert row["DOWN"] > row["FLAT"] > row["UP"], "上月跌得越狠反转因子越高"


def test_low_volatility_prefers_quiet_names():
    n = 200
    rng = np.random.default_rng(5)
    dates = pd.date_range("2024-01-01", periods=n, freq="B")
    quiet = 100 + np.cumsum(rng.normal(0, 0.1, n))
    noisy = 100 + np.cumsum(rng.normal(0, 3.0, n))
    close = pd.DataFrame({"QUIET": quiet, "NOISY": noisy}, index=dates)
    factor = low_volatility(close)
    row = factor.dropna().iloc[-1]
    assert row["QUIET"] > row["NOISY"], "低波动标的因子值应更高"


def test_illiquidity_prefers_thin_names():
    n = 200
    dates = pd.date_range("2024-01-01", periods=n, freq="B")
    close = pd.DataFrame({"BIG": 100.0, "SMALL": 100.0}, index=dates)
    volume = pd.DataFrame({"BIG": 1e9, "SMALL": 1e5}, index=dates)
    factor = illiquidity(close, volume)
    row = factor.dropna().iloc[-1]
    assert row["SMALL"] > row["BIG"], "成交额越小非流动性因子越高"


def test_valuation_yield_ranks_and_guards():
    from quantlab.factors import valuation_yield
    dates = pd.date_range("2024-01-01", periods=40, freq="B")
    pe = pd.DataFrame({"CHEAP": 8.0, "RICH": 40.0, "LOSS": -5.0, "ZERO": 0.0}, index=dates)
    factor = valuation_yield(pe)
    row = factor.iloc[-1]
    assert row["CHEAP"] > row["RICH"] > row["LOSS"], "低 PE 收益率更高，亏损为负"
    assert pd.isna(row["ZERO"]), "除零必须为 NaN"


def test_low_turnover_prefers_quiet():
    from quantlab.factors import low_turnover
    dates = pd.date_range("2024-01-01", periods=200, freq="B")
    turn = pd.DataFrame({"QUIET": 0.5, "HOT": 8.0}, index=dates)
    row = low_turnover(turn).dropna().iloc[-1]
    assert row["QUIET"] > row["HOT"]
