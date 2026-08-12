import pandas as pd

from quantlab.cn_fundamentals import build_roe_panel


def make_records():
    return pd.DataFrame([
        {"ticker": "sh.600000", "stat_date": pd.Timestamp("2024-12-31"),
         "pub_date": pd.Timestamp("2025-03-20"), "roe": 0.12},
        {"ticker": "sh.600000", "stat_date": pd.Timestamp("2025-03-31"),
         "pub_date": pd.Timestamp("2025-04-25"), "roe": 0.03},
        # 同日更正公告：报告期更新的一条生效
        {"ticker": "sh.600000", "stat_date": pd.Timestamp("2025-06-30"),
         "pub_date": pd.Timestamp("2025-08-20"), "roe": 0.07},
        {"ticker": "sh.600000", "stat_date": pd.Timestamp("2025-03-31"),
         "pub_date": pd.Timestamp("2025-08-20"), "roe": 0.99},
        # 零数据哨兵行：不产生列
        {"ticker": "sz.000001", "stat_date": pd.NaT,
         "pub_date": pd.NaT, "roe": float("nan")},
    ])


def test_panel_pit_visibility_and_correction():
    daily = pd.date_range("2025-03-01", "2025-09-30", freq="B")
    panel = build_roe_panel(daily, make_records())
    assert list(panel.columns) == ["sh.600000"], "哨兵行不产生列"
    assert pd.isna(panel.loc["2025-03-19", "sh.600000"]), "公告日前不可见"
    assert panel.loc["2025-03-20", "sh.600000"] == 0.12
    assert panel.loc["2025-04-25", "sh.600000"] == 0.03
    assert panel.loc["2025-08-20", "sh.600000"] == 0.07, "同日多条取报告期最新"


def test_panel_staleness_expiry():
    daily = pd.date_range("2025-03-01", "2026-03-31", freq="B")
    panel = build_roe_panel(daily, make_records())
    assert panel.loc["2025-10-15", "sh.600000"] == 0.07, "两季内有效"
    assert pd.isna(panel.loc["2026-03-25", "sh.600000"]), "超限过期为 NaN"
