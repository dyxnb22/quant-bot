import pandas as pd

from quantlab.us_fundamentals import (build_roe_panel, extract_records,
                                      roe_events)


def _ni(end, val, start, filed):
    return {"ticker": "T", "kind": "ni", "start": start, "end": end,
            "filed": filed, "val": val}


def _eq(end, val, filed):
    return {"ticker": "T", "kind": "eq", "start": None, "end": end,
            "filed": filed, "val": val}


def make_records():
    """三个直接季度 + 一个年度（推导 Q4）+ 权益，申报日依次推进。"""
    rows = [
        _ni("2024-03-31", 10.0, "2024-01-01", "2024-05-01"),
        _eq("2024-03-31", 400.0, "2024-05-01"),
        _ni("2024-06-30", 12.0, "2024-04-01", "2024-08-01"),
        _eq("2024-06-30", 410.0, "2024-08-01"),
        _ni("2024-09-30", 11.0, "2024-07-01", "2024-11-01"),
        _eq("2024-09-30", 420.0, "2024-11-01"),
        # 10-K：年度值 50 → Q4 = 50 - (10+12+11) = 17
        _ni("2024-12-31", 50.0, "2024-01-01", "2025-02-15"),
        _eq("2024-12-31", 500.0, "2025-02-15"),
    ]
    return pd.DataFrame(rows)


def test_roe_events_ttm_and_q4_derivation():
    events = roe_events(make_records())
    assert len(events) == 1, "凑满 4 个相邻季度的时点只有年报申报日"
    filed, roe = events[0]
    assert filed == pd.Timestamp("2025-02-15")
    assert abs(roe - 50.0 / 500.0) < 1e-9, "TTM=10+12+11+17=50，权益取最新 500"


def test_roe_events_requires_adjacent_quarters():
    records = make_records()
    # 抽掉 Q2：年度无法推导 Q4（窗口内只剩 2 个季度），永远凑不满 4 季
    records = records[records["end"] != "2024-06-30"]
    assert roe_events(records) == []


def test_build_roe_panel_pit_visibility():
    daily = pd.date_range("2025-02-10", "2025-02-20", freq="B")
    panel = build_roe_panel(daily, make_records())
    assert pd.isna(panel.loc["2025-02-14", "T"]), "申报日之前不可见（PIT）"
    assert abs(panel.loc["2025-02-17", "T"] - 0.1) < 1e-9, "申报后首个交易日起生效"


def test_build_roe_panel_staleness_expiry():
    daily = pd.date_range("2025-02-01", "2025-12-31", freq="B")
    panel = build_roe_panel(daily, make_records())
    assert abs(panel.loc["2025-06-02", "T"] - 0.1) < 1e-9, "两季内仍有效"
    assert pd.isna(panel.loc["2025-12-30", "T"]), "超过前向填充上限后过期为 NaN"


def test_extract_records_filters():
    facts = {"facts": {"us-gaap": {"NetIncomeLoss": {"units": {"USD": [
        {"form": "10-Q", "start": "2024-01-01", "end": "2024-03-31",
         "filed": "2024-05-01", "val": 1.0},
        {"form": "8-K", "start": "2024-01-01", "end": "2024-03-31",
         "filed": "2024-05-01", "val": 2.0},          # 非 10-Q/10-K → 丢弃
        {"form": "10-Q", "start": None, "end": "2024-06-30",
         "filed": None, "val": 3.0},                   # 缺 filed → 丢弃
    ]}}}}}
    records = extract_records(facts, "X")
    assert len(records) == 1 and records[0]["val"] == 1.0
