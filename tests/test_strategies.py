import pytest

from conftest import load_strategy_class

STRATEGIES = ["EmaRsiStrategy"]


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
    assert df["enter_long"].sum() > 0, "合成数据上应至少产生一次入场信号"


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
