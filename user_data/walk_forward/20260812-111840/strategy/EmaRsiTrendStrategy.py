"""趋势跟随 + 体制闸门：EmaRsi 原信号，且仅在长期趋势向上（close > EMA200）时入场。

研究依据：03 号 walk-forward 报告显示 EmaRsiStrategy 的 OOS 亏损窗口与熊市完全重合
（策略只有 beta）。本策略用体制闸门在熊市把敞口关掉。EMA200 周期固定，
不进入 hyperopt 空间——体制定义属于风险政策范畴，不属于可优化参数。
"""

import talib.abstract as ta
from pandas import DataFrame
from technical import qtpylib

from freqtrade.strategy import IntParameter, IStrategy


class EmaRsiTrendStrategy(IStrategy):
    INTERFACE_VERSION = 3

    REQUIRED_INDICATOR_COLUMNS = ("ema_fast", "ema_slow", "rsi", "ema_trend")

    timeframe = "1h"
    can_short = False
    process_only_new_candles = True
    startup_candle_count = 220

    minimal_roi = {"0": 0.10, "240": 0.05, "720": 0.02, "1440": 0}
    stoploss = -0.08
    trailing_stop = False

    buy_rsi_max = IntParameter(55, 80, default=70, space="buy", optimize=True)

    @property
    def protections(self):
        return [
            {"method": "CooldownPeriod", "stop_duration_candles": 3},
            {
                "method": "MaxDrawdown",
                "lookback_period_candles": 168,
                "trade_limit": 10,
                "stop_duration_candles": 24,
                "max_allowed_drawdown": 0.15,
            },
            {
                "method": "StoplossGuard",
                "lookback_period_candles": 72,
                "trade_limit": 3,
                "stop_duration_candles": 12,
                "only_per_pair": False,
            },
        ]

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["ema_fast"] = ta.EMA(dataframe, timeperiod=20)
        dataframe["ema_slow"] = ta.EMA(dataframe, timeperiod=50)
        dataframe["ema_trend"] = ta.EMA(dataframe, timeperiod=200)
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            qtpylib.crossed_above(dataframe["ema_fast"], dataframe["ema_slow"])
            & (dataframe["close"] > dataframe["ema_trend"])
            & (dataframe["rsi"] < self.buy_rsi_max.value)
            & (dataframe["volume"] > 0),
            "enter_long",
        ] = 1
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            qtpylib.crossed_below(dataframe["ema_fast"], dataframe["ema_slow"]),
            "exit_long",
        ] = 1
        return dataframe
