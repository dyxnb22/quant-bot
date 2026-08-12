"""统计严谨性工具箱：所有因子/策略结论必须经过这里才有资格谈显著。

背景：本仓库已检验 8 个币市管线 + 后续将批量检验因子。试验次数一多，
"总会撞出一个好看的"是数学必然——这三件工具就是防假阳性的：

- deflated_sharpe：把"试了多少次"计入夏普的显著性（Bailey & López de Prado, 2014）
- permutation_pvalue：不依赖分布假设的置换检验
- benjamini_hochberg：多假设同时检验时的 FDR 校正
"""

import math

import numpy as np
from scipy.stats import norm

EULER_MASCHERONI = 0.5772156649015329


def deflated_sharpe(sharpe: float, n_obs: int, n_trials: int,
                    skew: float = 0.0, kurt: float = 3.0,
                    var_trials: float | None = None) -> float:
    """DSR：观测夏普在扣除"多次试验的期望最大噪声夏普"后仍为正的概率。

    sharpe 为每期（非年化）夏普，n_obs 为期数，n_trials 为总试验次数。
    返回值 ∈ (0,1)，越接近 1 越可信；一般要求 > 0.95。
    """
    if n_trials <= 1:
        expected_max_noise = 0.0
    else:
        if var_trials is None:
            var_trials = 1.0 / (n_obs - 1)
        z1 = norm.ppf(1 - 1.0 / n_trials)
        z2 = norm.ppf(1 - 1.0 / (n_trials * math.e))
        expected_max_noise = math.sqrt(var_trials) * (
            (1 - EULER_MASCHERONI) * z1 + EULER_MASCHERONI * z2)
    denominator = math.sqrt(
        max(1e-12, 1 - skew * sharpe + (kurt - 1) / 4 * sharpe ** 2))
    statistic = (sharpe - expected_max_noise) * math.sqrt(n_obs - 1) / denominator
    return float(norm.cdf(statistic))


def permutation_pvalue(series, n_permutations: int = 1000, seed: int = 0) -> float:
    """符号翻转置换检验：H0 为对称零均值分布，返回单侧 p 值（均值 > 0）。"""
    values = np.asarray(series, dtype=float)
    values = values[~np.isnan(values)]
    if values.size == 0:
        return 1.0
    observed = values.mean()
    rng = np.random.default_rng(seed)
    signs = rng.choice([-1.0, 1.0], size=(n_permutations, values.size))
    permuted_means = (signs * values).mean(axis=1)
    return float((1 + (permuted_means >= observed).sum()) / (1 + n_permutations))


def newey_west_tstat(series, lags: int | None = None) -> float:
    """均值 = 0 的 Newey-West HAC t 统计（Bartlett 核）。

    月频 IC/收益序列存在序列相关，朴素 t 会高估显著性；
    默认滞后阶 ⌊4(n/100)^{2/9}⌋。
    """
    values = np.asarray(series, dtype=float)
    values = values[~np.isnan(values)]
    n = values.size
    if n < 3:
        return 0.0
    if lags is None:
        lags = int(4 * (n / 100) ** (2 / 9))
    demeaned = values - values.mean()
    long_run_var = float(demeaned @ demeaned) / n
    for lag in range(1, min(lags, n - 1) + 1):
        gamma = float(demeaned[lag:] @ demeaned[:-lag]) / n
        long_run_var += 2 * (1 - lag / (lags + 1)) * gamma
    if long_run_var <= 0:
        return 0.0
    return float(values.mean() / math.sqrt(long_run_var / n))


def newey_west_pvalue(series, lags: int | None = None) -> float:
    """NW t 的单侧 p 值（均值 > 0，正态近似）。

    协议 v3（2026-08-12 预登记）：月频 IC 序列相关下，新批次显著性以此为准；
    符号翻转置换检验保留为信息列（其可交换性假设在序列相关下不成立）。
    """
    return float(1 - norm.cdf(newey_west_tstat(series, lags)))


def benjamini_hochberg(pvalues, alpha: float = 0.05) -> list[bool]:
    """BH 过程控制 FDR：返回每个假设校正后是否显著（与输入同序）。"""
    p = np.asarray(pvalues, dtype=float)
    n = p.size
    if n == 0:
        return []
    order = np.argsort(p)
    thresholds = alpha * (np.arange(1, n + 1)) / n
    passed = p[order] <= thresholds
    significant = np.zeros(n, dtype=bool)
    if passed.any():
        cutoff = np.max(np.nonzero(passed)[0]) + 1
        significant[order[:cutoff]] = True
    return significant.tolist()
