import pandas as pd

from quantlab.attribution import industry_active_weights, style_snapshot


def test_style_snapshot_tilts():
    universe = [f"T{i}" for i in range(10)]
    factor = pd.Series({t: float(10 - i) for i, t in enumerate(universe)})  # T0 动量最高
    liquidity = pd.Series({t: float(i) for i, t in enumerate(universe)})   # T9 流动性最高
    snapshot = style_snapshot(["T0", "T1"], factor, liquidity)
    assert snapshot["momentum_pct"] < 0.25, "清单应集中在动量最高分位"
    assert snapshot["liquidity_pct"] > 0.5, "本例清单偏低流动性"


def test_industry_active_weights():
    imap = {"A": "银行", "B": "银行", "C": "白酒", "D": "医药", "E": "医药", "F": "白酒"}
    active = industry_active_weights(["A", "B", "C"], list(imap), imap)
    # 清单: 银行 2/3, 白酒 1/3, 医药 0；股池: 银行 1/3, 白酒 1/3, 医药 1/3
    assert abs(active["银行"] - (2 / 3 - 2 / 6)) < 1e-9
    assert abs(active["医药"] - (0 - 2 / 6)) < 1e-9
    assert abs(active["白酒"]) < 1e-9
