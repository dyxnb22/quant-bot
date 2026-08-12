"""趋势跟随基线策略：EMA20/EMA50 金叉入场，RSI 过滤追高，死叉离场。

定位：学习基线。预期不稳定盈利，用于承载回测/优化/模拟盘完整流程。
"""

import talib.abstract as ta
from pandas import DataFrame
from technical import qtpylib

from freqtrade.strategy import IntParameter, IStrategy


class EmaRsiStrategy(IStrategy):
    INTERFACE_VERSION = 3

    REQUIRED_INDICATOR_COLUMNS = ("ema_fast", "ema_slow", "rsi")

    timeframe = "1h"
    can_short = False
    process_only_new_candles = True
    # 200：freqtrade recursive-analysis 实测 60 根时 RSI 有 0.66% 递归方差，199+ 归零
    startup_candle_count = 200

    # 随持仓时间递减的止盈目标（分钟: 收益率）
    minimal_roi = {"0": 0.10, "240": 0.05, "720": 0.02, "1440": 0}
    stoploss = -0.08
    trailing_stop = False

    # hyperopt 可优化参数：RSI 追高过滤阈值
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
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            qtpylib.crossed_above(dataframe["ema_fast"], dataframe["ema_slow"])
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
