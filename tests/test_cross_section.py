import numpy as np
import pandas as pd
import pytest

from quantlab.cross_section import long_short, quantile_portfolios, rank_ic, turnover


@pytest.fixture
def perfect_data():
    """因子值恰好等于未来收益：IC 应为 1，分层应严格单调。"""
    dates = pd.date_range("2024-01-31", periods=12, freq="ME")
    tickers = [f"T{i}" for i in range(20)]
    rng = np.random.default_rng(0)
    returns = pd.DataFrame(rng.normal(0, 0.05, (12, 20)), index=dates, columns=tickers)
    factor = returns.copy()
    return factor, returns


def test_rank_ic_perfect(perfect_data):
    factor, returns = perfect_data
    ic = rank_ic(factor, returns)
    assert len(ic) == 12
    assert np.allclose(ic.values, 1.0)


def test_rank_ic_random_near_zero():
    dates = pd.date_range("2024-01-31", periods=100, freq="ME")
    tickers = [f"T{i}" for i in range(50)]
    rng = np.random.default_rng(1)
    factor = pd.DataFrame(rng.normal(size=(100, 50)), index=dates, columns=tickers)
    returns = pd.DataFrame(rng.normal(size=(100, 50)), index=dates, columns=tickers)
    assert abs(rank_ic(factor, returns).mean()) < 0.05


def test_quantile_monotonic(perfect_data):
    factor, returns = perfect_data
    q = quantile_portfolios(factor, returns, quantiles=5)
    means = q.mean()
    assert list(means.index) == ["Q1", "Q2", "Q3", "Q4", "Q5"]
    assert means.is_monotonic_increasing, "完美因子的分层收益应严格单调"


def test_long_short_and_costs(perfect_data):
    factor, returns = perfect_data
    q = quantile_portfolios(factor, returns, quantiles=5)
    to = turnover(factor, quantiles=5)
    ls = long_short(q, cost_bps=10, turnover_series=to)
    assert (ls["net"] <= ls["gross"] + 1e-12).all(), "扣成本后不得高于毛收益"
    assert ls["gross"].mean() > 0, "完美因子多空毛收益应为正"


def test_turnover_bounds():
    dates = pd.date_range("2024-01-31", periods=3, freq="ME")
    tickers = list("ABCDE")
    stable = pd.DataFrame([[1, 2, 3, 4, 5]] * 3, index=dates, columns=tickers, dtype=float)
    to = turnover(stable, quantiles=5)
    assert to.iloc[0] == 1.0, "首期全部为新持仓"
    assert (to.iloc[1:] == 0.0).all(), "因子排序不变则零换手"

    flipped = stable.copy()
    flipped.iloc[1] = [5, 4, 3, 2, 1]
    to2 = turnover(flipped, quantiles=5)
    assert to2.iloc[1] == 1.0, "排序完全反转则全换手"
