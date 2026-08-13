from quantlab.factor_eval import verdict


def base_metrics(**overrides):
    metrics = {"consistency": 0.7, "net_mean": 0.005, "monotonicity": 0.9}
    metrics.update(overrides)
    return metrics


def test_verdict_three_way():
    assert verdict(base_metrics(), bh_significant=True) == "PASS（初检）"
    assert "INCONCLUSIVE" in verdict(base_metrics(), bh_significant=False)
    assert "REJECTED" in verdict(base_metrics(monotonicity=0.5), bh_significant=True)
    assert "REJECTED" in verdict(base_metrics(net_mean=-0.001), bh_significant=True)


def test_verdict_float_noise_at_boundary():
    """回归（2026-08-13 cn roe_pit）：spearmanr 对精确 0.8 返回 0.7999…9，
    边界判定必须消浮点噪声，否则恰好踩线的因子被误拒。"""
    metrics = base_metrics(monotonicity=0.7999999999999999, consistency=0.6)
    assert "INCONCLUSIVE" in verdict(metrics, bh_significant=False)
    # 真实低于阈值（超出噪声量级）仍拒绝
    assert "REJECTED" in verdict(base_metrics(monotonicity=0.79), bh_significant=False)
