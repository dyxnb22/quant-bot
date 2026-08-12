import numpy as np
import pandas as pd

from quantlab.portfolio_sim import simulate, target_positions


def test_target_positions_buffer_semantics():
    row = pd.Series({f"T{i}": float(100 - i) for i in range(10)})  # T0 最高
    # 进入线 20%（前 2 名），退出线 40%（前 4 名）
    prev = {"T3", "T5"}
    new = target_positions(row, prev, enter_pct=0.2, exit_pct=0.4)
    assert "T0" in new and "T1" in new, "前 20% 必须进入"
    assert "T3" in new, "老持仓在前 40% 内应保留"
    assert "T5" not in new, "老持仓跌出前 40% 应退出"
    assert "T2" not in new, "非持仓且不在前 20% 不得进入"


def test_buffer_reduces_turnover():
    rng = np.random.default_rng(0)
    dates = pd.date_range("2024-01-31", periods=24, freq="ME")
    names = [f"T{i}" for i in range(100)]
    base = pd.Series(rng.normal(0, 1, 100), index=names)
    factor = pd.DataFrame(
        {n: base[n] + rng.normal(0, 0.8, 24) for n in names}, index=dates)
    forward = pd.DataFrame(rng.normal(0, 0.05, (24, 100)), index=dates, columns=names)
    naive = simulate(factor, forward, enter_pct=0.2, exit_pct=0.2, min_names=50)
    buffered = simulate(factor, forward, enter_pct=0.2, exit_pct=0.4, min_names=50)
    assert buffered["avg_turnover"] < naive["avg_turnover"]


def test_cost_math_two_periods():
    dates = pd.date_range("2024-01-31", periods=2, freq="ME")
    names = list("ABCDE")
    factor = pd.DataFrame([[5, 4, 3, 2, 1], [1, 2, 3, 4, 5]],
                          index=dates, columns=names, dtype=float)
    forward = pd.DataFrame(0.10, index=dates, columns=names)
    result = simulate(factor, forward, enter_pct=0.2, exit_pct=0.2,
                      cost_bps=100, min_names=1)
    monthly = result["monthly"]
    # 第 1 期：买入 A（1 买 0 卖，n=1）成本 = 1/1 * 1% = 1%
    assert abs(monthly["net"].iloc[0] - (0.10 - 0.01)) < 1e-9
    # 第 2 期：A→E 全换（1 买 1 卖，n=1）成本 = 2/1 * 1% = 2%
    assert abs(monthly["net"].iloc[1] - (0.10 - 0.02)) < 1e-9


def test_industry_neutral_balances_selection():
    names = [f"A{i}" for i in range(10)] + [f"B{i}" for i in range(10)]
    industry_map = {n: n[0] for n in names}
    # A 行业因子值整体碾压 B 行业
    row = pd.Series({**{f"A{i}": 100.0 - i for i in range(10)},
                     **{f"B{i}": 10.0 - i for i in range(10)}})
    global_sel = target_positions(row, set(), enter_pct=0.2, exit_pct=0.2)
    assert all(t.startswith("A") for t in global_sel), "全局排序应全选 A 行业"
    neutral_sel = target_positions(row, set(), enter_pct=0.2, exit_pct=0.2,
                                   industry_map=industry_map, industry_neutral=True)
    assert sum(t.startswith("A") for t in neutral_sel) == 2
    assert sum(t.startswith("B") for t in neutral_sel) == 2, "行业中性应各行业各取前 20%"
