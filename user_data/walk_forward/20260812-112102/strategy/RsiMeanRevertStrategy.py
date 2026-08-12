"""均值回归基线策略：长期趋势向上（价格在 EMA200 上方）时，RSI 超卖买入、回归后卖出。

与趋势跟随策略互补：一个吃趋势、一个吃震荡回调，用于对比不同市况下的表现差异。
"""

import talib.abstract as ta
from pandas import DataFrame

from freqtrade.strategy import IntParameter, IStrategy


class RsiMeanRevertStrategy(IStrategy):
    INTERFACE_VERSION = 3

    REQUIRED_INDICATOR_COLUMNS = ("ema_trend", "rsi")

    timeframe = "1h"
    can_short = False
    process_only_new_candles = True
    startup_candle_count = 220

    minimal_roi = {"0": 0.06, "360": 0.03, "720": 0.015, "1440": 0}
    stoploss = -0.06
    trailing_stop = False

    buy_rsi_min = IntParameter(20, 40, default=30, space="buy", optimize=True)
    sell_rsi = IntParameter(50, 75, default=60, space="sell", optimize=True)

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
        dataframe["ema_trend"] = ta.EMA(dataframe, timeperiod=200)
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (dataframe["close"] > dataframe["ema_trend"])
            & (dataframe["rsi"] < self.buy_rsi_min.value)
            & (dataframe["volume"] > 0),
            "enter_long",
        ] = 1
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            dataframe["rsi"] > self.sell_rsi.value,
            "exit_long",
        ] = 1
        return dataframe
