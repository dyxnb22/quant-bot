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
    perf = realized_performance(["A", "B"], ["A", "B", "C"], close)
    # A: 110→121 = +10%，B: 100→90 = -10% → 清单等权 0%
    assert abs(perf["list_return"]) < 1e-9
    # 基准: (+10% -10% +0%) / 3 = 0%
    assert abs(perf["benchmark_return"]) < 1e-9
    assert abs(perf["excess"]) < 1e-9
