import pandas as pd

from quantlab.cn_momentum_list import (industry_weights, realized_performance,
                                       select_top_quintile)


def test_select_top_quintile_descending():
    row = pd.Series({f"T{i}": float(i) for i in range(20)})
    top = select_top_quintile(row)
    assert len(top) == 4
    assert list(top.index) == ["T19", "T18", "T17", "T16"]
    assert top.is_monotonic_decreasing


def test_industry_weights_ordering_and_sum():
    imap = {"A": "银行", "B": "银行", "C": "白酒", "D": "医药"}
    weights = industry_weights(["A", "B", "C", "D"], imap)
    assert abs(weights.sum() - 1.0) < 1e-9
    assert weights.index[0] == "银行" and abs(weights.iloc[0] - 0.5) < 1e-9
    # 未知行业归入"未分类"
    weights2 = industry_weights(["A", "X"], imap)
    assert "未分类" in weights2.index


def test_realized_performance_math():
    dates = pd.date_range("2026-05-31", periods=3, freq="ME")
    close = pd.DataFrame(
        {"A": [100.0, 110.0, 121.0], "B": [100.0, 100.0, 90.0], "C": [100.0, 105.0, 105.0]},
        index=dates)
    perf = realized_performance(["A", "B"], ["A", "B", "C"], close, "2026-06", "2026-07")
    # A: 110→121 = +10%，B: 100→90 = -10% → 清单等权 0%
    assert abs(perf["list_return"]) < 1e-9
    assert abs(perf["benchmark_return"]) < 1e-9
    assert abs(perf["excess"]) < 1e-9
    assert perf["months_gap"] == 1


def test_realized_performance_explicit_months_and_gap():
    dates = pd.date_range("2026-04-30", periods=4, freq="ME")
    close = pd.DataFrame({"A": [100.0, 100.0, 100.0, 130.0]}, index=dates)
    # 跨 2 个月的缺口必须被显式标注，而不是悄悄用最后两行
    perf = realized_performance(["A"], ["A"], close, "2026-05", "2026-07")
    assert perf["months_gap"] == 2
    assert abs(perf["list_return"] - 0.30) < 1e-9
    # 月份不存在 → None（漏月可察觉）
    assert realized_performance(["A"], ["A"], close, "2025-01", "2026-07") is None
