from datetime import datetime, timezone

import pandas as pd

from quantlab.data_quality import check_ohlcv


def make_df(n=100, freq="1h"):
    dates = pd.date_range("2026-08-01", periods=n, freq=freq, tz="UTC")
    return pd.DataFrame({
        "date": dates,
        "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5,
        "volume": 10.0,
    })


NOW = datetime(2026, 8, 5, 12, tzinfo=timezone.utc)


def test_clean_data_passes():
    report = check_ohlcv(make_df(), "1h", now=NOW)
    assert report.ok and not report.warnings


def test_gap_detected_as_warning():
    df = make_df().drop(index=[50, 51]).reset_index(drop=True)
    report = check_ohlcv(df, "1h", now=NOW)
    assert report.gaps == 1 and report.warnings and report.ok


def test_duplicate_and_ohlc_error_fail():
    df = make_df()
    df.loc[10, "date"] = df.loc[9, "date"]   # 重复时间戳
    df.loc[20, "high"] = 90.0                # high < low
    report = check_ohlcv(df, "1h", now=NOW)
    assert not report.ok
    assert report.duplicates == 1 and report.ohlc_errors == 1


def test_stale_data_fails():
    report = check_ohlcv(make_df(), "1h", now=datetime(2026, 9, 1, tzinfo=timezone.utc))
    assert not report.ok
