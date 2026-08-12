import numpy as np
import pandas as pd

from quantlab.funding import attach_funding, funding_zscore


def test_funding_zscore_no_lookahead_and_extremes():
    """z-score 只用截至当期的历史；截断尾部不改变此前的 z 值。"""
    n = 200
    rng = np.random.default_rng(1)
    rates = rng.normal(0.0001, 0.00005, n)
    rates[150:160] = -0.0004  # 相对极端的负值段
    funding = pd.DataFrame({
        "date": pd.date_range("2024-01-01", periods=n, freq="8h", tz="UTC"),
        "funding_rate": rates,
    })
    out = funding_zscore(funding, window=90, min_periods=30)
    assert out["funding_z"].iloc[:29].isna().all(), "min_periods 之前应为 NaN"
    assert out["funding_z"].iloc[150:160].min() < -2, "极端负值段应产生显著负 z"

    truncated = funding_zscore(funding.iloc[:160], window=90, min_periods=30)
    pd.testing.assert_series_equal(
        out["funding_z"].iloc[:160], truncated["funding_z"], check_names=False)


def test_attach_funding_no_lookahead():
    candles = pd.DataFrame({
        "date": pd.date_range("2024-01-01", periods=24, freq="1h", tz="UTC"),
    })
    funding = pd.DataFrame({
        "date": pd.to_datetime(
            ["2024-01-01 00:00", "2024-01-01 08:00", "2024-01-01 16:00"], utc=True),
        "funding_rate": [0.0001, -0.0002, 0.0003],
    })
    out = attach_funding(candles, funding)

    def rate_at(hour):
        ts = pd.Timestamp(f"2024-01-01 {hour:02d}:00", tz="UTC")
        return out.loc[out["date"] == ts, "funding_rate"].iloc[0]

    assert rate_at(0) == 0.0001
    assert rate_at(7) == 0.0001, "08:00 结算前只能看到 00:00 的费率"
    assert rate_at(9) == -0.0002
    assert rate_at(15) == -0.0002, "16:00 结算前不得看到 16:00 的费率"
    assert rate_at(16) == 0.0003
    assert rate_at(23) == 0.0003


def test_attach_funding_before_first_settlement_is_nan():
    candles = pd.DataFrame({
        "date": pd.date_range("2023-12-31 20:00", periods=6, freq="1h", tz="UTC"),
    })
    funding = pd.DataFrame({
        "date": pd.to_datetime(["2024-01-01 00:00"], utc=True),
        "funding_rate": [0.0001],
    })
    out = attach_funding(candles, funding)
    assert out["funding_rate"].isna().sum() == 4  # 20/21/22/23 点无已结算费率
