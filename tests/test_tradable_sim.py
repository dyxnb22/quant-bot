import numpy as np
import pandas as pd

from quantlab.tradable_sim import simulate_tradable


def build_world():
    """4 只票 × 4 个月日频：GOOD 正常、LIMIT 首个成交日封板、SUSP 第二期停牌、PRICY 天价。"""
    days = pd.date_range("2024-01-02", "2024-04-30", freq="B")
    base = pd.DataFrame(100.0, index=days, columns=["GOOD", "LIMIT", "SUSP", "PRICY"])
    base["PRICY"] = 5000.0  # 一手 50 万 > 预算
    # LIMIT 在 2 月首个交易日（2/1）收盘 +10% 封板
    feb_first = days[days >= "2024-02-01"][0]
    prev_day = days[days < feb_first][-1]
    base.loc[feb_first:, "LIMIT"] = base.loc[prev_day, "LIMIT"] * 1.10
    volume = pd.DataFrame(1e6, index=days, columns=base.columns)
    # SUSP 自 3 月起停牌（无量，价格冻结）
    mar_first = days[days >= "2024-03-01"][0]
    volume.loc[mar_first:, "SUSP"] = 0.0
    close = base.copy()
    close.loc[mar_first:, "SUSP"] = np.nan
    return close, volume


def month_ends(close):
    return close.resample("ME").last().index


def test_tradable_constraints_and_fees():
    close, volume = build_world()
    ends = month_ends(close)
    # 因子值互异（避免并列分位）。1 月末: 前三 = GOOD/LIMIT/SUSP；
    # 2 月末起: SUSP 垫底跌出（应卖出）、PRICY 进入前三（应尝试买入）
    factor = pd.DataFrame(
        [[4.0, 3.0, 2.0, 1.0],
         [4.0, 3.0, -9.0, 1.0],
         [4.0, 3.0, -9.0, 1.0]],
        index=ends[:3], columns=close.columns)

    result = simulate_tradable(
        factor, close, volume_daily=volume, capital=300_000,
        enter_pct=0.8, exit_pct=0.8, min_names=1, industry_neutral=False)

    monthly = result["monthly"]
    # 首期（2/1 成交日）：LIMIT 封板禁买、PRICY 整手买不起 → 只持有 GOOD 与 SUSP
    assert result["blocked_buys"] >= 1, "封板股必须被禁买"
    assert result["too_expensive"] >= 1, "超预算股必须被跳过"
    first_names = monthly["n_holdings"].iloc[0]
    assert first_names == 2
    # 第二期（3/1 成交日）：SUSP 停牌 → 卖不出去，被迫顺延持有
    assert result["blocked_sells"] >= 1, "停牌股必须卖出顺延"
    # 费用：有买有卖，印花税只对卖出征收（费用明细为正且卖出期费用含税）
    assert result["total_fees"] > 0
    # 组合价值轨迹存在且无 NaN
    assert monthly["net"].notna().all()


def test_ghost_asset_writeoff():
    """持仓连续 60 交易日无有效价 → 清算减记为 0（不再按 ffill 幽灵估值）。"""
    days = pd.date_range("2024-01-02", "2024-09-30", freq="B")
    close = pd.DataFrame({"GOOD": 100.0, "GHOST": 100.0}, index=days)
    volume = pd.DataFrame(1e6, index=days, columns=close.columns)
    dead_from = days[days >= "2024-02-15"]
    close.loc[dead_from, "GHOST"] = np.nan
    volume.loc[dead_from, "GHOST"] = 0.0

    ends = close.resample("ME").last().index
    factor = pd.DataFrame(float("nan"), index=ends[:8], columns=close.columns)
    factor["GOOD"] = 2.0
    factor.iloc[0, factor.columns.get_loc("GHOST")] = 1.0  # 仅首月入选

    result = simulate_tradable(factor, close, volume_daily=volume, capital=200_000,
                               enter_pct=1.0, exit_pct=1.0, min_names=1,
                               industry_neutral=False)
    assert result["writeoffs"] == 1, "长期无价持仓必须被清算"
    assert result["monthly"]["net"].min() < -0.25, "清算损失必须体现在净值中"
    assert result["monthly"]["n_holdings"].iloc[-1] == 1


def test_next_day_fill_prices_used():
    """月末信号必须用次一交易日价格成交：错过月末与成交日之间的跳空。"""
    days = pd.date_range("2024-01-02", "2024-03-29", freq="B")
    close = pd.DataFrame(100.0, index=days, columns=["A"])
    # 2 月首个交易日跳空 +5%，随后回落到 100
    feb_first = days[days >= "2024-02-01"][0]
    close.loc[feb_first, "A"] = 105.0
    volume = pd.DataFrame(1e6, index=days, columns=["A"])
    ends = close.resample("ME").last().index
    factor = pd.DataFrame([[1.0], [1.0]], index=ends[:2], columns=["A"])
    result = simulate_tradable(factor, close, volume_daily=volume, capital=100_000,
                               enter_pct=1.0, exit_pct=1.0, min_names=1,
                               industry_neutral=False)
    # 以 105 买入、随后价格 100 → 首期应体现约 -4.8% 的下跌（而非 0%）
    assert result["monthly"]["net"].iloc[0] < -0.03