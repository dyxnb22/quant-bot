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
    """500 根合成 1h K 线：先跌后涨，保证金叉/死叉/RSI 极值都会出现。"""
    n = 500
    rng = np.random.default_rng(42)
    trend = np.concatenate([
        np.linspace(100, 70, n // 2),
        np.linspace(70, 130, n - n // 2),
    ])
    close = trend + rng.normal(0, 1.0, n)
    df = pd.DataFrame({
        "date": pd.date_range("2024-01-01", periods=n, freq="1h", tz="UTC"),
        "open": close + rng.normal(0, 0.3, n),
        "high": close + np.abs(rng.normal(0, 0.8, n)) + 0.5,
        "low": close - np.abs(rng.normal(0, 0.8, n)) - 0.5,
        "close": close,
        "volume": rng.uniform(100, 1000, n),
    })
    return df
