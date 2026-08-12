import pandas as pd

from quantlab.deployment_gate import evaluate_gate, information_ratio


GOOD = {"dsr": 0.97, "ann_excess": 0.05, "information_ratio": 0.6,
        "stress_net_sharpe": 0.1, "forward_months": 14}


def test_gate_all_pass():
    assert all(r["ok"] for r in evaluate_gate(GOOD))


def test_gate_each_condition_binds():
    for key, bad in [("dsr", 0.90), ("ann_excess", -0.01),
                     ("information_ratio", 0.1), ("stress_net_sharpe", -0.05),
                     ("forward_months", 3)]:
        rows = evaluate_gate({**GOOD, key: bad})
        assert sum(not r["ok"] for r in rows) == 1, f"{key} 应恰好触发一条不通过"


def test_information_ratio_math():
    idx = pd.date_range("2025-01-31", periods=12, freq="ME")
    portfolio = pd.Series(0.02, index=idx)
    benchmark = pd.Series(0.01, index=idx)
    rel = information_ratio(portfolio, benchmark)
    assert abs(rel["ann_excess"] - ((1.01) ** 12 - 1)) < 1e-9
    assert rel["information_ratio"] == 0.0 or rel["information_ratio"] > 10  # 零波动超额
