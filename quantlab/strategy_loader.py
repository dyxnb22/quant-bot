"""策略加载与生效参数合并。

freqtrade 运行时会用 <Strategy>.json（hyperopt 产物）覆盖类属性；
审计必须针对覆盖后的"生效值"，否则会漏掉优化器写入的越界参数。
"""

import importlib.util
import json
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_STRATEGY_DIR = PROJECT_DIR / "user_data" / "strategies"


def discover_strategies(strategy_dir=None) -> list[str]:
    """按文件名发现全部策略（文件名 = 类名约定）。"""
    d = Path(strategy_dir) if strategy_dir else DEFAULT_STRATEGY_DIR
    return sorted(p.stem for p in d.glob("*.py"))


def load_strategy_class(name: str, strategy_dir=None):
    d = Path(strategy_dir) if strategy_dir else DEFAULT_STRATEGY_DIR
    # 变体策略通过 `from EmaRsiStrategy import ...` 继承基类，需要目录在 sys.path 上
    d_str = str(d)
    sys.path.insert(0, d_str)
    try:
        spec = importlib.util.spec_from_file_location(name, d / f"{name}.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return getattr(module, name)
    finally:
        sys.path.remove(d_str)


def load_effective_params(name: str, strategy_dir=None) -> dict:
    d = Path(strategy_dir) if strategy_dir else DEFAULT_STRATEGY_DIR
    cls = load_strategy_class(name, d)
    instance = cls(config={"stake_currency": "USDT", "runmode": "backtest"})
    params = {
        "stoploss": cls.stoploss,
        "minimal_roi": dict(getattr(cls, "minimal_roi", {})),
        "timeframe": cls.timeframe,
        "protections": [p["method"] for p in instance.protections],
    }
    params_file = d / f"{name}.json"
    if params_file.exists():
        payload = json.loads(params_file.read_text()).get("params", {})
        stoploss_block = payload.get("stoploss", {})
        if "stoploss" in stoploss_block:
            params["stoploss"] = stoploss_block["stoploss"]
        if payload.get("roi"):
            params["minimal_roi"] = payload["roi"]
        params["params_file"] = str(params_file)
    return params
