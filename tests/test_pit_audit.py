import pandas as pd

from quantlab.pit_audit import audit_cn, audit_us


def test_audit_cn_counts():
    records = pd.DataFrame([
        # 正常：期末后 30 天公告
        {"ticker": "A", "stat_date": pd.Timestamp("2025-03-31"),
         "pub_date": pd.Timestamp("2025-04-30"), "roe": 0.1},
        # 硬违规：公告早于期末
        {"ticker": "B", "stat_date": pd.Timestamp("2025-03-31"),
         "pub_date": pd.Timestamp("2025-03-01"), "roe": 0.1},
        # 迟披露：>120 天
        {"ticker": "C", "stat_date": pd.Timestamp("2024-12-31"),
         "pub_date": pd.Timestamp("2025-06-30"), "roe": 0.1},
        # 更正公告：同 (ticker, stat_date) 两条
        {"ticker": "A", "stat_date": pd.Timestamp("2025-03-31"),
         "pub_date": pd.Timestamp("2025-05-10"), "roe": 0.2},
        # 哨兵行（NaT）不参与
        {"ticker": "D", "stat_date": pd.NaT, "pub_date": pd.NaT, "roe": float("nan")},
    ])
    audit = audit_cn(records)
    assert audit["records"] == 4
    assert audit["violations"] == 1
    assert audit["late"] == 1
    assert audit["corrections"] == 2, "更正公告按对计数（keep=False）"


def test_audit_us_counts():
    records = pd.DataFrame([
        {"ticker": "X", "kind": "ni", "start": "2024-01-01",
         "end": "2024-03-31", "filed": "2024-05-01", "val": 1.0},
        {"ticker": "X", "kind": "eq", "start": None,
         "end": "2024-03-31", "filed": "2024-03-01", "val": 2.0},  # 硬违规
        {"ticker": "X", "kind": "none", "start": None,
         "end": None, "filed": None, "val": float("nan")},          # 哨兵不参与
    ])
    audit = audit_us(records)
    assert audit["records"] == 2
    assert audit["violations"] == 1


def test_audit_us_first_filing_lag():
    """往年同期数在后续年报中重复申报（同 end 更晚 filed）——滞后按首次申报，不算迟披露。"""
    records = pd.DataFrame([
        {"ticker": "X", "kind": "ni", "start": "2024-01-01",
         "end": "2024-03-31", "filed": "2024-05-01", "val": 1.0},   # 首次：31 天
        {"ticker": "X", "kind": "ni", "start": "2024-01-01",
         "end": "2024-03-31", "filed": "2025-02-15", "val": 1.0},   # 对比值重复申报
    ])
    audit = audit_us(records)
    assert audit["late"] == 0, "重复申报不计迟披露"
    assert audit["lag_median"] == 31.0
