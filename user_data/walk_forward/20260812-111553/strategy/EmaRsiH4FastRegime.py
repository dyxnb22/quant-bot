"""假设 4（来自 04 号报告方向 1）：更快的体制闸门。

EMA200（≈8.3 天）闸门因滞后错过 V 型反弹早段（04 号已证伪）；
本变体换用 EMA100（≈4.2 天），检验"闸门方向正确、只是速度不够"是否成立。
检验：walk-forward OOS 拼接收益 vs 基线与 04 号 EMA200 版本。
"""

import talib.abstract as ta
from pandas import DataFrame

from EmaRsiStrategy import EmaRsiStrategy


class EmaRsiH4FastRegime(EmaRsiStrategy):
    REQUIRED_INDICATOR_COLUMNS = ("ema_fast", "ema_slow", "rsi", "ema_regime")
    startup_candle_count = 120

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe = super().populate_indicators(dataframe, metadata)
        dataframe["ema_regime"] = ta.EMA(dataframe, timeperiod=100)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe = super().populate_entry_trend(dataframe, metadata)
        dataframe.loc[dataframe["close"] <= dataframe["ema_regime"], "enter_long"] = 0
        return dataframe
