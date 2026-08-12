"""资金费率反转策略：第一个 K 线之外的信息源（07 号研究批次）。

论点（预登记）：永续资金费率极端负值 = 杠杆空头拥挤 = 现货逆向做多机会；
费率回正 = 情绪修复 = 离场。阈值可优化，论点不可优化。

数据口径：信号来自 Binance 永续（全球最大永续市场）+ OKX 尾部补齐，
执行于 OKX 现货。费率文件缺失时安全降级为永不入场。
"""

import sys
from pathlib import Path

import pandas as pd
from pandas import DataFrame

from freqtrade.strategy import IntParameter, IStrategy

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from quantlab.funding import FUNDING_DIR, attach_funding, funding_file  # noqa: E402


class FundingRevertStrategy(IStrategy):
    INTERFACE_VERSION = 3

    REQUIRED_INDICATOR_COLUMNS = ("funding_rate",)

    timeframe = "1h"
    can_short = False
    process_only_new_candles = True
    startup_candle_count = 30

    minimal_roi = {"0": 0.06, "360": 0.03, "720": 0.015, "1440": 0}
    stoploss = -0.08
    trailing_stop = False

    # 入场阈值：费率 ≤ buy_funding_bps/10000（每 8 小时），负得越深越极端
    buy_funding_bps = IntParameter(-30, -2, default=-10, space="buy", optimize=True)

    funding_dir = FUNDING_DIR  # 测试可注入

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

    def _load_funding(self, pair: str) -> pd.DataFrame | None:
        path = Path(self.funding_dir) / funding_file(pair).name
        if not path.exists():
            return None
        return pd.read_feather(path)

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        funding = self._load_funding(metadata["pair"])
        if funding is None or funding.empty:
            dataframe["funding_rate"] = float("nan")
            return dataframe
        return attach_funding(dataframe, funding)

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        threshold = self.buy_funding_bps.value / 10000
        dataframe.loc[
            (dataframe["funding_rate"] <= threshold)
            & (dataframe["volume"] > 0),
            "enter_long",
        ] = 1
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            dataframe["funding_rate"] >= 0,
            "exit_long",
        ] = 1
        return dataframe
