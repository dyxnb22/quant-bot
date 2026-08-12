"""资金费率反转策略：第一个 K 线之外的信息源（07 号研究批次）。

论点（预登记）：资金费率相对极端负值 = 杠杆空头拥挤 = 现货逆向做多机会；
情绪回归常态（z ≥ 0）= 离场。阈值可优化，论点不可优化。

"极端"用滚动 z-score（90 期 ≈ 30 天）定义而非绝对 bps——分布统计显示
绝对阈值跨时代失效（BTC 2023-2026 全期最小仅 -1.5bps，而 2021-2022 年
-30bps 常见）。z 逐期只用截至该期的历史，无未来函数（tests/test_funding.py 锁死）。

数据口径：信号来自 Binance 永续（全球最大永续市场）+ OKX 尾部补齐，
执行于 OKX 现货。费率文件缺失时安全降级为永不入场。
"""

import sys
from pathlib import Path

import pandas as pd
from pandas import DataFrame

from freqtrade.strategy import IntParameter, IStrategy

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from quantlab.funding import (FUNDING_DIR, attach_funding, funding_file,
                              funding_zscore)


class FundingRevertStrategy(IStrategy):
    INTERFACE_VERSION = 3

    REQUIRED_INDICATOR_COLUMNS = ("funding_rate", "funding_z")

    timeframe = "1h"
    can_short = False
    process_only_new_candles = True
    startup_candle_count = 30

    minimal_roi = {"0": 0.06, "360": 0.03, "720": 0.015, "1440": 0}
    stoploss = -0.08
    trailing_stop = False

    # 入场阈值：funding_z ≤ buy_funding_z/10（即 -3.5 ~ -1.5 个滚动标准差）
    buy_funding_z = IntParameter(-35, -15, default=-20, space="buy", optimize=True)

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
            dataframe["funding_z"] = float("nan")
            return dataframe
        return attach_funding(dataframe, funding_zscore(funding))

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        threshold = self.buy_funding_z.value / 10
        dataframe.loc[
            (dataframe["funding_z"] <= threshold)
            & (dataframe["volume"] > 0),
            "enter_long",
        ] = 1
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            dataframe["funding_z"] >= 0,
            "exit_long",
        ] = 1
        return dataframe
