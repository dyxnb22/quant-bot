import numpy as np

from quantlab.stats_tests import benjamini_hochberg, deflated_sharpe, permutation_pvalue


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


def test_benjamini_hochberg():
    # 教科书例子：p = [0.01, 0.04, 0.03, 0.005] @ alpha=0.05 → 全部通过
    assert benjamini_hochberg([0.01, 0.04, 0.03, 0.005]) == [True, True, True, True]
    # 全部不显著
    assert benjamini_hochberg([0.5, 0.8, 0.9]) == [False, False, False]
    # 混合：只有极小的 p 通过
    result = benjamini_hochberg([0.001, 0.7, 0.8, 0.9])
    assert result == [True, False, False, False]
    assert benjamini_hochberg([]) == []
