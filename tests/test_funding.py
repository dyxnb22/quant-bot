import pandas as pd

from quantlab.funding import attach_funding


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
