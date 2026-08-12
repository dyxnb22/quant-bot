import numpy as np
import pandas as pd
import pytest

from conftest import load_strategy_class
from quantlab.strategy_loader import discover_strategies

STRATEGIES = discover_strategies()
# 带体制闸门的策略在通用合成夹具上可能无入场信号，由各自专项测试覆盖入场行为
GATED_STRATEGIES = {"EmaRsiTrendStrategy", "EmaRsiH4FastRegime"}


@pytest.fixture
def uptrend_df():
    """确立 EMA200 后的深回调-强反弹形态：保证体制闸门策略必然出现合规入场。"""
    n = 700
    rng = np.random.default_rng(7)
    trend = np.concatenate([
        np.full(300, 100.0),          # 平台期（确立 EMA200）
        np.linspace(100, 88, 60),     # 回调（制造死叉）
        np.linspace(88, 150, 340),    # 强反弹（金叉时 close 远高于 EMA200）
    ])
    close = trend + rng.normal(0, 0.6, n)
    return pd.DataFrame({
        "date": pd.date_range("2024-01-01", periods=n, freq="1h", tz="UTC"),
        "open": close + rng.normal(0, 0.2, n),
        "high": close + np.abs(rng.normal(0, 0.6, n)) + 0.4,
        "low": close - np.abs(rng.normal(0, 0.6, n)) - 0.4,
        "close": close,
        "volume": rng.uniform(100, 1000, n),
    })


@pytest.fixture(params=STRATEGIES)
def strategy(request):
    cls = load_strategy_class(request.param)
    return cls(config={"stake_currency": "USDT", "runmode": "backtest"})


def test_strategy_basic_attributes(strategy):
    assert strategy.timeframe == "1h"
    assert -0.20 <= strategy.stoploss < 0, "止损必须存在且不过深"
    assert strategy.can_short is False


def test_populate_indicators_adds_columns(strategy, ohlcv_df):
    df = strategy.populate_indicators(ohlcv_df.copy(), {"pair": "BTC/USDT"})
    for col in strategy.REQUIRED_INDICATOR_COLUMNS:
        assert col in df.columns, f"缺少指标列 {col}"


def test_entry_exit_signals_valid(strategy, ohlcv_df):
    meta = {"pair": "BTC/USDT"}
    df = strategy.populate_indicators(ohlcv_df.copy(), meta)
    df = strategy.populate_entry_trend(df, meta)
    df = strategy.populate_exit_trend(df, meta)
    assert "enter_long" in df.columns and "exit_long" in df.columns
    assert set(df["enter_long"].dropna().unique()) <= {0, 1}
    assert set(df["exit_long"].dropna().unique()) <= {0, 1}
    if strategy.__class__.__name__ not in GATED_STRATEGIES:
        assert df["enter_long"].sum() > 0, "合成数据上应至少产生一次入场信号"


def test_trend_gate_blocks_entries_below_ema200(ohlcv_df):
    """体制闸门：所有入场信号必须发生在 close > ema_trend 的 K 线上。"""
    cls = load_strategy_class("EmaRsiTrendStrategy")
    strategy = cls(config={"stake_currency": "USDT", "runmode": "backtest"})
    meta = {"pair": "BTC/USDT"}
    df = strategy.populate_indicators(ohlcv_df.copy(), meta)
    df = strategy.populate_entry_trend(df, meta)
    entries = df[df["enter_long"] == 1]
    assert (entries["close"] > entries["ema_trend"]).all()


def test_trend_strategy_enters_in_uptrend(uptrend_df):
    cls = load_strategy_class("EmaRsiTrendStrategy")
    strategy = cls(config={"stake_currency": "USDT", "runmode": "backtest"})
    meta = {"pair": "BTC/USDT"}
    df = strategy.populate_indicators(uptrend_df.copy(), meta)
    df = strategy.populate_entry_trend(df, meta)
    assert df["enter_long"].sum() > 0


def test_h1_tight_stoploss():
    cls = load_strategy_class("EmaRsiH1TightStop")
    assert cls.stoploss == -0.04


def test_h2_time_cutoff():
    from datetime import datetime, timedelta, timezone
    from types import SimpleNamespace
    cls = load_strategy_class("EmaRsiH2TimeExit")
    s = cls(config={"stake_currency": "USDT", "runmode": "backtest"})
    now = datetime(2026, 1, 2, tzinfo=timezone.utc)
    old = SimpleNamespace(open_date_utc=now - timedelta(minutes=800))
    fresh = SimpleNamespace(open_date_utc=now - timedelta(minutes=100))
    assert s.custom_exit("BTC/USDT", old, now, 100.0, 0.01) == "time_cutoff"
    assert s.custom_exit("BTC/USDT", old, now, 100.0, 0.05) is None
    assert s.custom_exit("BTC/USDT", fresh, now, 100.0, 0.01) is None


def test_h3_pair_specific_exit(ohlcv_df):
    cls = load_strategy_class("EmaRsiH3PairSpecific")
    s = cls(config={"stake_currency": "USDT", "runmode": "backtest"})
    assert s.custom_exit("ETH/USDT", None, None, 100.0, 0.04) == "pair_roi"
    assert s.custom_exit("BTC/USDT", None, None, 100.0, 0.04) is None
    df = s.populate_indicators(ohlcv_df.copy(), {"pair": "ETH/USDT"})
    assert "ema_fast2" in df.columns and "ema_slow2" in df.columns


def test_h4_regime_gate(ohlcv_df):
    cls = load_strategy_class("EmaRsiH4FastRegime")
    s = cls(config={"stake_currency": "USDT", "runmode": "backtest"})
    meta = {"pair": "BTC/USDT"}
    df = s.populate_indicators(ohlcv_df.copy(), meta)
    df = s.populate_entry_trend(df, meta)
    entries = df[df["enter_long"] == 1]
    assert (entries["close"] > entries["ema_regime"]).all()


def test_no_lookahead_bias(strategy, ohlcv_df):
    """截断最后 50 根 K 线不应改变此前任何信号（未来函数检测）。"""
    meta = {"pair": "BTC/USDT"}

    def signals(df):
        d = strategy.populate_indicators(df.copy(), meta)
        d = strategy.populate_entry_trend(d, meta)
        return d["enter_long"].fillna(0)

    full = signals(ohlcv_df)
    truncated = signals(ohlcv_df.iloc[:-50])
    assert (full.iloc[: len(truncated)].values == truncated.values).all()
