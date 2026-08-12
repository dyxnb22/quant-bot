import numpy as np
import pandas as pd

from quantlab.factors import (forward_1m, illiquidity, low_volatility,
                              momentum_12_1, momentum_ex_winners, month_end,
                              short_reversal_1m)


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


def test_momentum_ex_winners_cuts_top_segment():
    """截面前 20% 动量（极端赢家）被置 NaN，其余保留原值。"""
    dates = pd.date_range("2023-01-31", periods=15, freq="ME")
    frame = pd.DataFrame(
        {f"C{i}": 100 * ((1 + 0.01 * i) ** np.arange(15)) for i in range(10)},
        index=dates)
    base = momentum_12_1(frame)
    trimmed = momentum_ex_winners(frame, cut=0.2)
    last_base, last_trim = base.iloc[-1], trimmed.iloc[-1]
    top2 = last_base.nlargest(2).index
    assert last_trim[top2].isna().all(), "前 20%（2/10 只）被剔除"
    kept = last_base.index.difference(top2)
    assert (last_trim[kept] == last_base[kept]).all(), "其余保留原值"


def test_forward_return_alignment():
    close = make_monthly()
    forward = forward_1m(close)
    expected = close["UP"].iloc[6] / close["UP"].iloc[5] - 1
    assert abs(forward["UP"].iloc[5] - expected) < 1e-12
    assert forward.iloc[-1].isna().all(), "最后一期没有未来收益"


def test_month_end_resample_drops_partial_month():
    daily = pd.DataFrame(
        {"A": np.arange(1, 63, dtype=float)},
        index=pd.date_range("2024-01-01", periods=62, freq="B"))  # 止于 2024-03-27
    monthly = month_end(daily)
    assert monthly.index.is_month_end.all()
    assert monthly.index[-1].month == 2, "3 月未完成，必须剔除"
    kept = month_end(daily, drop_partial=False)
    assert kept.index[-1].month == 3


def test_month_end_keeps_complete_month():
    daily = pd.DataFrame(
        {"A": 1.0},
        index=pd.date_range("2024-01-01", "2024-02-29", freq="B"))  # 2/29 周四为当月最后交易日
    monthly = month_end(daily)
    assert monthly.index[-1].month == 2, "已收满的月份必须保留"


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


def test_composite_mom_lto_averages_ranks():
    from quantlab.factors import composite_mom_lto
    n = 400
    dates = pd.date_range("2023-01-02", periods=n, freq="B")
    rng = np.random.default_rng(9)
    # WIN：涨且低换手（双强）；MID：涨但高换手；LOSE：跌且高换手
    close = pd.DataFrame({
        "WIN": 100 * (1.002 ** np.arange(n)),
        "MID": 100 * (1.002 ** np.arange(n)),
        "LOSE": 100 * (0.999 ** np.arange(n)),
    }, index=dates) + rng.normal(0, 0.01, (n, 3))
    turn = pd.DataFrame({"WIN": 0.5, "MID": 9.0, "LOSE": 9.0}, index=dates)
    composite = composite_mom_lto(close, turn).dropna(how="all")
    row = composite.iloc[-1]
    assert row["WIN"] > row["MID"] > row["LOSE"], "双强 > 单强 > 双弱"
    assert row.max() <= 1.0 and row.min() >= 0.0


def test_composite_requires_both_signals():
    from quantlab.factors import composite_mom_lto
    n = 400
    dates = pd.date_range("2023-01-02", periods=n, freq="B")
    close = pd.DataFrame({"A": 100.0, "B": 100.0}, index=dates)
    turn = pd.DataFrame({"A": 1.0, "B": float("nan")}, index=dates)
    composite = composite_mom_lto(close, turn)
    assert composite["B"].dropna().empty, "换手缺失的标的不得有复合值"
