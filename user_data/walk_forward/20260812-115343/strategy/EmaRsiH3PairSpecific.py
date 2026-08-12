"""假设 3（来自 05 号 LLM 复盘）：币对差异化出场，优先修复 ETH/SOL。

ETH/SOL 出场用更快的 EMA12/35 交叉（响应快约 30%），并在浮盈 ≥3.5% 时提前止盈；
BTC/XRP 保持基线参数作为对照。
检验：walk-forward OOS 拼接收益 vs 基线（关注改善是否币种特异）。
"""

import talib.abstract as ta
from pandas import DataFrame
from technical import qtpylib

from EmaRsiStrategy import EmaRsiStrategy


class EmaRsiH3PairSpecific(EmaRsiStrategy):
    FAST_EXIT_PAIRS = {"ETH/USDT", "SOL/USDT"}
    REQUIRED_INDICATOR_COLUMNS = ("ema_fast", "ema_slow", "rsi", "ema_fast2", "ema_slow2")

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe = super().populate_indicators(dataframe, metadata)
        dataframe["ema_fast2"] = ta.EMA(dataframe, timeperiod=12)
        dataframe["ema_slow2"] = ta.EMA(dataframe, timeperiod=35)
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        fast, slow = (("ema_fast2", "ema_slow2")
                      if metadata["pair"] in self.FAST_EXIT_PAIRS
                      else ("ema_fast", "ema_slow"))
        dataframe.loc[
            qtpylib.crossed_below(dataframe[fast], dataframe[slow]),
            "exit_long",
        ] = 1
        return dataframe

    def custom_exit(self, pair, trade, current_time, current_rate, current_profit, **kwargs):
        if pair in self.FAST_EXIT_PAIRS and current_profit >= 0.035:
            return "pair_roi"
        return None
