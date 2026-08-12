import numpy as np
import pandas as pd

from quantlab.factors import forward_1m, momentum_12_1, month_end


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
