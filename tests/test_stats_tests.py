import numpy as np

from quantlab.stats_tests import (benjamini_hochberg, deflated_sharpe,
                                  newey_west_tstat, permutation_pvalue)


def naive_t(x):
    return x.mean() / x.std(ddof=1) * len(x) ** 0.5


def test_newey_west_close_to_naive_when_iid():
    rng = np.random.default_rng(0)
    x = rng.normal(0.5, 1.0, 500)
    nw = newey_west_tstat(x)
    assert abs(nw - naive_t(x)) / naive_t(x) < 0.15


def test_newey_west_shrinks_t_under_autocorrelation():
    rng = np.random.default_rng(1)
    n = 500
    e = rng.normal(0, 1, n)
    x = np.zeros(n)
    for i in range(1, n):
        x[i] = 0.7 * x[i - 1] + e[i]  # 强正自相关
    x = x + 0.3
    assert newey_west_tstat(x) < naive_t(x) * 0.75, "正自相关下 NW t 应显著低于朴素 t"


def test_deflated_sharpe_monotone_in_trials():
    """同样的观测夏普，试验次数越多，DSR（真实性概率）越低。"""
    d1 = deflated_sharpe(sharpe=0.1, n_obs=252, n_trials=1)
    d10 = deflated_sharpe(sharpe=0.1, n_obs=252, n_trials=10)
    d100 = deflated_sharpe(sharpe=0.1, n_obs=252, n_trials=100)
    assert d1 > d10 > d100


def test_deflated_sharpe_extremes():
    assert deflated_sharpe(sharpe=0.5, n_obs=1000, n_trials=1) > 0.99
    assert deflated_sharpe(sharpe=0.0, n_obs=252, n_trials=50) < 0.1


def test_permutation_pvalue():
    rng = np.random.default_rng(0)
    strong = rng.normal(0.5, 0.1, 100)   # 明显为正
    noise = rng.normal(0.0, 1.0, 100)    # 零均值噪声
    assert permutation_pvalue(strong, seed=1) < 0.01
    assert 0.1 < permutation_pvalue(noise, seed=1) < 0.9


def test_newey_west_pvalue_direction():
    from quantlab.stats_tests import newey_west_pvalue
    rng = np.random.default_rng(2)
    strong = rng.normal(0.5, 0.5, 200)
    noise = rng.normal(0.0, 1.0, 200)
    assert newey_west_pvalue(strong) < 0.01
    assert 0.05 < newey_west_pvalue(noise) < 0.95


def test_registry_family_trials():
    import pytest as _pytest

    from quantlab.registry import family_trials
    # 不硬编码具体数值（登记数合法增长）；验证机制：正整数、已知下限、未知家族报错
    assert family_trials("cn") >= 9
    assert family_trials("us") >= 4
    assert family_trials("crypto") >= 8
    with _pytest.raises(KeyError):
        family_trials("hk")


def test_forward_ledger(tmp_path, monkeypatch):
    import quantlab.forward_ledger as ledger
    monkeypatch.setattr(ledger, "LEDGER_FILE", tmp_path / "ledger.jsonl")
    assert ledger.append_entry("2026-09", ["sh.600000", "sz.000001"]) is True
    assert ledger.append_entry("2026-09", ["sh.600000"]) is False, "同月同规则幂等"
    assert ledger.append_entry("2026-09", ["sh.600000"], rule="composite") is True, "不同规则独立计数"
    assert ledger.forward_months("2026-08-12T00:00:00+00:00") == 1
    assert ledger.forward_months("2026-08-12T00:00:00+00:00", rule="composite") == 1
    assert ledger.forward_months("2099-01-01T00:00:00+00:00") == 0


def test_benjamini_hochberg():
    # 教科书例子：p = [0.01, 0.04, 0.03, 0.005] @ alpha=0.05 → 全部通过
    assert benjamini_hochberg([0.01, 0.04, 0.03, 0.005]) == [True, True, True, True]
    # 全部不显著
    assert benjamini_hochberg([0.5, 0.8, 0.9]) == [False, False, False]
    # 混合：只有极小的 p 通过
    result = benjamini_hochberg([0.001, 0.7, 0.8, 0.9])
    assert result == [True, False, False, False]
    assert benjamini_hochberg([]) == []
