from quantlab.factor_eval import power_months, verdict


def base_metrics(**overrides):
    metrics = {"consistency": 0.7, "net_mean": 0.005, "monotonicity": 0.9,
               "months": 100, "ic_nw_t": 1.2,
               "layers": [-0.01, 0.0, 0.005, 0.008, 0.012]}
    metrics.update(overrides)
    return metrics


def test_verdict_three_way():
    assert verdict(base_metrics(), bh_significant=True) == "PASS（初检）"
    assert "INCONCLUSIVE" in verdict(base_metrics(), bh_significant=False)
    assert "REJECTED" in verdict(base_metrics(monotonicity=0.5), bh_significant=True)
    assert "REJECTED" in verdict(base_metrics(net_mean=-0.001), bh_significant=True)


def test_verdict_v4_implementability_annotation():
    """协议 v4-1：多头腿（Q5）为负的 PASS 自动标注不可实施（20 号案例回归）。"""
    negative_long = base_metrics(layers=[-0.09, -0.08, -0.07, -0.05, -0.013])
    result = verdict(negative_long, bh_significant=True)
    assert "PASS" in result and "不可实施" in result and "不产生候选" in result


def test_verdict_v4_power_estimate():
    """协议 v4-3：INCONCLUSIVE 附功效估计（22 号案例：t=1.64@119月 → 约 120 月）。"""
    boundary = base_metrics(months=119, ic_nw_t=1.64)
    result = verdict(boundary, bh_significant=False)
    assert "约需 120 月" in result
    assert power_months(119, 1.64) == 120
    assert power_months(100, 0.0) is None, "无正效应时不给估计"
    assert power_months(100, 3.29) == 25, "t 翻倍 → 月数缩四倍"


def test_verdict_float_noise_at_boundary():
    """回归（2026-08-13 cn roe_pit）：spearmanr 对精确 0.8 返回 0.7999…9，
    边界判定必须消浮点噪声，否则恰好踩线的因子被误拒。"""
    metrics = base_metrics(monotonicity=0.7999999999999999, consistency=0.6)
    assert "INCONCLUSIVE" in verdict(metrics, bh_significant=False)
    # 真实低于阈值（超出噪声量级）仍拒绝
    assert "REJECTED" in verdict(base_metrics(monotonicity=0.79), bh_significant=False)
