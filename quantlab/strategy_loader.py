"""策略加载与生效参数合并。

freqtrade 运行时会用 <Strategy>.json（hyperopt 产物）覆盖类属性；
审计必须针对覆盖后的"生效值"，否则会漏掉优化器写入的越界参数。
"""

import importlib.util
import json
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_STRATEGY_DIR = PROJECT_DIR / "user_data" / "strategies"


def load_strategy_class(name: str, strategy_dir=None):
    d = Path(strategy_dir) if strategy_dir else DEFAULT_STRATEGY_DIR
    spec = importlib.util.spec_from_file_location(name, d / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return getattr(module, name)


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
