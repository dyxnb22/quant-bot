import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

STRATEGY_DIR = Path(__file__).parent.parent / "user_data" / "strategies"


def load_strategy_class(name: str):
    """从 user_data/strategies/ 按文件名加载策略类（文件名 = 类名）。"""
    spec = importlib.util.spec_from_file_location(name, STRATEGY_DIR / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return getattr(module, name)


@pytest.fixture
def ohlcv_df() -> pd.DataFrame:
    """600 根合成 1h K 线：下跌 → 长上涨 → 急跌回调 → 恢复。

    覆盖两类策略的触发条件：EMA 金叉/死叉、长期趋势向上时的 RSI 超卖回调。
    """
    n = 600
    rng = np.random.default_rng(42)
    trend = np.concatenate([
        np.linspace(100, 70, 150),   # 下跌段
        np.linspace(70, 140, 300),   # 长上涨段（价格站上 EMA200）
        np.linspace(140, 118, 30),   # 急跌回调（制造上升趋势中的 RSI 超卖）
        np.linspace(118, 150, 120),  # 恢复段
    ])
    close = trend + rng.normal(0, 0.8, n)
    df = pd.DataFrame({
        "date": pd.date_range("2024-01-01", periods=n, freq="1h", tz="UTC"),
        "open": close + rng.normal(0, 0.3, n),
        "high": close + np.abs(rng.normal(0, 0.8, n)) + 0.5,
        "low": close - np.abs(rng.normal(0, 0.8, n)) - 0.5,
        "close": close,
        "volume": rng.uniform(100, 1000, n),
    })
    return df
