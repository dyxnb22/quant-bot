"""解析 freqtrade backtesting 导出结果（--backtest-directory 目录中的 zip）。

zip 内主结果文件与 zip 同名（<base>.json），另含 _config.json、
策略副本、market_change.feather 等附件。
"""

import json
import zipfile
from pathlib import Path


def load_export_zip(zip_path: Path) -> dict:
    """读取单个回测导出 zip 的主结果 json。"""
    zip_path = Path(zip_path)
    with zipfile.ZipFile(zip_path) as archive:
        with archive.open(f"{zip_path.stem}.json") as fh:
            return json.load(fh)


def _load_newest_export(results_dir: Path) -> dict:
    zips = sorted(results_dir.glob("*.zip"), key=lambda p: p.stat().st_mtime)
    if not zips:
        raise FileNotFoundError(f"{results_dir} 中没有回测导出 zip")
    return load_export_zip(zips[-1])


def read_backtest_metrics(results_dir, strategy: str) -> dict:
    stats = _load_newest_export(Path(results_dir))["strategy"][strategy]
    return {
        "profit_total": stats.get("profit_total", 0.0),
        "profit_total_abs": stats.get("profit_total_abs", 0.0),
        "max_drawdown": stats.get("max_drawdown_account", 0.0),
        "sharpe": stats.get("sharpe", 0.0),
        "trades": stats.get("total_trades", 0),
        "market_change": stats.get("market_change", 0.0),
    }
