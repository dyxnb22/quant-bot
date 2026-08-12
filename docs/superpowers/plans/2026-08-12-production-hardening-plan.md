# 生产化加固实施计划（阶段 1.5）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 quant-bot 补齐四个生产级特质：walk-forward 验证自动化、风险政策代码化（启动强制审计）、数据质量保障、定时巡检 + 本地告警。

**Architecture:** 自研逻辑收敛为可单测的 `quantlab/` Python 包；与 Freqtrade 只通过 CLI 子进程和文件产物交互；运维入口统一在 Makefile。

**Tech Stack:** Python 3.14（复用 .venv，零新增依赖）/ pandas / launchd / osascript。

## Global Constraints

- 全部命令在 `/Users/diaoyuxuan/quant-bot` 下执行，Python 一律用 `.venv/bin/python`。
- 风险政策边界：stoploss ∈ [-0.20, -0.005]；max_open_trades ≤ 5；stake ≤ 钱包 10%；必含 MaxDrawdown + StoplossGuard；dry_run 恒 true。
- walk-forward 绝不写生产参数文件（`--strategy-path` 隔离）。
- 每任务一次 commit；TDD：先测试后实现。

---

### Task 1: quantlab 包基础 + 窗口切分（TDD）

**Files:**
- Create: `quantlab/__init__.py`、`quantlab/windows.py`、`quantlab/strategy_loader.py`、`tests/test_windows.py`
- Modify: `tests/conftest.py`（项目根加入 sys.path；loader 复用 quantlab）

**Interfaces:**
- Produces: `build_windows(start, end, is_months, oos_months, step_months) -> list[Window]`；`Window.is_timerange / .oos_timerange`（freqtrade `YYYYMMDD-YYYYMMDD` 格式）；`load_strategy_class(name, strategy_dir=None)`；`load_effective_params(name, strategy_dir=None) -> dict`（类属性 ⊕ json 覆盖，含 stoploss/minimal_roi/timeframe/protections）。

- [ ] Step 1: 写失败测试 `tests/test_windows.py`

```python
from datetime import date

from quantlab.windows import Window, add_months, build_windows


def test_add_months_normal():
    assert add_months(date(2023, 1, 1), 12) == date(2024, 1, 1)
    assert add_months(date(2023, 11, 15), 3) == date(2024, 2, 15)


def test_add_months_clamps_month_end():
    assert add_months(date(2023, 1, 31), 1) == date(2023, 2, 28)


def test_build_windows_alignment():
    ws = build_windows(date(2023, 1, 1), date(2026, 8, 1), 12, 3, 3)
    assert ws[0].is_timerange == "20230101-20240101"
    assert ws[0].oos_timerange == "20240101-20240401"
    # OOS 紧接 IS，窗口按步长滚动
    assert ws[1].is_start == date(2023, 4, 1)
    # 所有窗口 oos_end 不越界
    assert all(w.oos_end <= date(2026, 8, 1) for w in ws)
    assert len(ws) == 10


def test_build_windows_empty_when_range_too_short():
    assert build_windows(date(2026, 1, 1), date(2026, 6, 1), 12, 3, 3) == []
```

- [ ] Step 2: 运行确认失败（ModuleNotFoundError）

Run: `.venv/bin/python -m pytest tests/test_windows.py -q`

- [ ] Step 3: 实现 `quantlab/windows.py`

```python
"""Walk-forward 窗口切分（纯函数，不依赖 freqtrade）。"""

import calendar
from dataclasses import dataclass
from datetime import date


def add_months(d: date, months: int) -> date:
    total = d.year * 12 + (d.month - 1) + months
    year, month0 = divmod(total, 12)
    day = min(d.day, calendar.monthrange(year, month0 + 1)[1])
    return date(year, month0 + 1, day)


@dataclass(frozen=True)
class Window:
    is_start: date
    is_end: date  # 同时是 oos_start
    oos_end: date

    @property
    def is_timerange(self) -> str:
        return f"{self.is_start:%Y%m%d}-{self.is_end:%Y%m%d}"

    @property
    def oos_timerange(self) -> str:
        return f"{self.is_end:%Y%m%d}-{self.oos_end:%Y%m%d}"


def build_windows(start: date, end: date, is_months: int = 12,
                  oos_months: int = 3, step_months: int = 3) -> list[Window]:
    windows = []
    cursor = start
    while True:
        is_end = add_months(cursor, is_months)
        oos_end = add_months(is_end, oos_months)
        if oos_end > end:
            return windows
        windows.append(Window(cursor, is_end, oos_end))
        cursor = add_months(cursor, step_months)
```

- [ ] Step 4: 实现 `quantlab/strategy_loader.py`（生效参数 = 类属性被 `<Strategy>.json` 覆盖）

```python
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
```

- [ ] Step 5: `tests/conftest.py` 顶部加入项目根路径并复用 loader

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quantlab.strategy_loader import load_strategy_class  # noqa: E402
```

（删除 conftest 中原有的 importlib 实现与 STRATEGY_DIR，保留 ohlcv_df fixture；test_strategies.py 的 `from conftest import load_strategy_class` 不变。）

- [ ] Step 6: 全量测试通过后提交

Run: `.venv/bin/python -m pytest tests/ -q` → 全 PASS

```bash
git add quantlab/ tests/ && git commit -m "feat: quantlab 包（窗口切分 + 策略生效参数加载）"
```

### Task 2: 风险政策代码化 + 修复现存越界 + 启动强制审计（TDD）

**Files:**
- Create: `quantlab/risk_policy.py`、`tests/test_risk_policy.py`
- Modify: `user_data/strategies/EmaRsiStrategy.json`（stoploss -0.234 → -0.08）、`scripts/bot_start.sh`（启动前审计）

**Interfaces:**
- Consumes: `load_effective_params`（Task 1）
- Produces: `audit_params(subject, params) -> list[Violation]`、`audit_config(config) -> list[Violation]`、`run_audit() -> list[Violation]`、CLI `python -m quantlab.risk_policy`（违规退出码 1）。

- [ ] Step 1: 写失败测试 `tests/test_risk_policy.py`

```python
from quantlab.risk_policy import audit_config, audit_params

COMPLIANT = {
    "stoploss": -0.08,
    "minimal_roi": {"0": 0.10, "1440": 0},
    "timeframe": "1h",
    "protections": ["CooldownPeriod", "MaxDrawdown", "StoplossGuard"],
}


def test_compliant_params_pass():
    assert audit_params("X", COMPLIANT) == []


def test_deep_stoploss_rejected():
    bad = {**COMPLIANT, "stoploss": -0.234}
    assert any("止损" in str(v) for v in audit_params("X", bad))


def test_missing_protection_rejected():
    bad = {**COMPLIANT, "protections": ["CooldownPeriod"]}
    assert any("protections" in str(v) for v in audit_params("X", bad))


def test_bad_timeframe_rejected():
    bad = {**COMPLIANT, "timeframe": "1m"}
    assert audit_params("X", bad)


def test_config_rules():
    ok = {"dry_run": True, "max_open_trades": 3, "stake_amount": 500, "dry_run_wallet": 10000}
    assert audit_config(ok) == []
    assert audit_config({**ok, "dry_run": False})
    assert audit_config({**ok, "max_open_trades": 9})
    assert audit_config({**ok, "stake_amount": 5000})
    assert audit_config({**ok, "stake_amount": "unlimited"})
```

- [ ] Step 2: 运行确认失败，实现 `quantlab/risk_policy.py`

```python
"""风险政策代码化：配置与策略生效参数必须通过审计才允许运行。

政策是项目的风险底线；hyperopt 等优化器只优化目标函数、没有风险观，
其产物必须经过本审计才能进入运行环境（bot_start.sh 强制执行）。
"""

import json
import sys
from dataclasses import dataclass
from pathlib import Path

from quantlab.strategy_loader import PROJECT_DIR, load_effective_params

STOPLOSS_DEEPEST = -0.20
STOPLOSS_SHALLOWEST = -0.005
MAX_OPEN_TRADES_LIMIT = 5
STAKE_RATIO_LIMIT = 0.10
ALLOWED_TIMEFRAMES = {"5m", "15m", "1h", "4h", "1d"}
REQUIRED_PROTECTIONS = {"MaxDrawdown", "StoplossGuard"}
AUDITED_STRATEGIES = ("EmaRsiStrategy", "RsiMeanRevertStrategy")


@dataclass
class Violation:
    subject: str
    rule: str
    actual: object

    def __str__(self) -> str:
        return f"[{self.subject}] {self.rule}（实际值: {self.actual}）"


def audit_params(subject: str, params: dict) -> list[Violation]:
    violations = []
    stoploss = params.get("stoploss")
    if not isinstance(stoploss, (int, float)) or not (
        STOPLOSS_DEEPEST <= stoploss <= STOPLOSS_SHALLOWEST
    ):
        violations.append(Violation(
            subject, f"止损必须在 [{STOPLOSS_DEEPEST}, {STOPLOSS_SHALLOWEST}] 内", stoploss))
    roi = params.get("minimal_roi") or {}
    if "0" not in {str(k) for k in roi}:
        violations.append(Violation(subject, "minimal_roi 必须存在且含 '0' 档", roi))
    if params.get("timeframe") not in ALLOWED_TIMEFRAMES:
        violations.append(Violation(
            subject, f"timeframe 必须属于 {sorted(ALLOWED_TIMEFRAMES)}", params.get("timeframe")))
    missing = REQUIRED_PROTECTIONS - set(params.get("protections") or [])
    if missing:
        violations.append(Violation(
            subject, f"缺少必需 protections: {sorted(missing)}", params.get("protections")))
    return violations


def audit_config(config: dict) -> list[Violation]:
    violations = []
    if config.get("dry_run") is not True:
        violations.append(Violation("config", "dry_run 必须为 true", config.get("dry_run")))
    max_open = config.get("max_open_trades", 0)
    if not isinstance(max_open, int) or not (0 < max_open <= MAX_OPEN_TRADES_LIMIT):
        violations.append(Violation(
            "config", f"max_open_trades 必须在 (0, {MAX_OPEN_TRADES_LIMIT}] 内", max_open))
    stake = config.get("stake_amount")
    wallet = config.get("dry_run_wallet", 0)
    if not isinstance(stake, (int, float)) or stake > wallet * STAKE_RATIO_LIMIT:
        violations.append(Violation(
            "config", f"stake_amount 不得超过 dry_run_wallet 的 {STAKE_RATIO_LIMIT:.0%}", stake))
    return violations


def run_audit(config_path=None, strategies=AUDITED_STRATEGIES, strategy_dir=None):
    config_file = Path(config_path) if config_path else PROJECT_DIR / "config" / "config.json"
    violations = audit_config(json.loads(config_file.read_text()))
    for name in strategies:
        violations += audit_params(name, load_effective_params(name, strategy_dir))
    return violations


def main() -> int:
    violations = run_audit()
    if violations:
        print("风险审计未通过：")
        for violation in violations:
            print(f"  ✗ {violation}")
        return 1
    print("风险审计通过：config 与全部策略生效参数均在政策边界内")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] Step 3: 单测通过后运行全量审计，**预期抓住现存违规**

Run: `.venv/bin/python -m quantlab.risk_policy`
Expected: 退出码 1，报告 EmaRsiStrategy 生效 stoploss -0.234 越界（hyperopt 产物覆盖类属性）

- [ ] Step 4: 修复 `user_data/strategies/EmaRsiStrategy.json`：`params.stoploss.stoploss` 改为 -0.08（其余优化参数保留），重跑审计 → 通过

- [ ] Step 5: `scripts/bot_start.sh` 在 launchctl bootstrap 之前插入强制审计

```bash
echo "启动前风险审计..."
if ! .venv/bin/python -m quantlab.risk_policy; then
    echo "审计未通过，拒绝启动。请修复违规项后重试。" >&2
    exit 1
fi
```

- [ ] Step 6: 重启 bot 使收敛后的参数生效并验证

```bash
./scripts/bot_stop.sh && ./scripts/bot_start.sh && sleep 15 && ./scripts/bot_status.sh
```

- [ ] Step 7: Commit

```bash
git add quantlab/risk_policy.py tests/test_risk_policy.py user_data/strategies/EmaRsiStrategy.json scripts/bot_start.sh
git commit -m "feat: 风险政策代码化+启动强制审计；修复 hyperopt 越界止损(-0.234→-0.08)"
```

### Task 3: 数据质量检查（TDD）

**Files:**
- Create: `quantlab/data_quality.py`、`tests/test_data_quality.py`

**Interfaces:**
- Produces: `check_ohlcv(df, timeframe, now, max_age_hours, name) -> DataReport`（`.problems` 硬失败 / `.warnings` 软告警）；CLI `python -m quantlab.data_quality [--max-age-hours N]`（扫 `user_data/data/okx/*.feather`，问题则退出码 1）。

- [ ] Step 1: 写失败测试 `tests/test_data_quality.py`

```python
from datetime import datetime, timezone

import pandas as pd

from quantlab.data_quality import check_ohlcv


def make_df(n=100, freq="1h"):
    dates = pd.date_range("2026-08-01", periods=n, freq=freq, tz="UTC")
    return pd.DataFrame({
        "date": dates,
        "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5,
        "volume": 10.0,
    })


NOW = datetime(2026, 8, 5, 12, tzinfo=timezone.utc)


def test_clean_data_passes():
    report = check_ohlcv(make_df(), "1h", now=NOW)
    assert report.ok and not report.warnings


def test_gap_detected():
    df = make_df().drop(index=[50, 51]).reset_index(drop=True)
    report = check_ohlcv(df, "1h", now=NOW)
    assert report.gaps == 1 and report.warnings


def test_duplicate_and_ohlc_error_fail():
    df = make_df()
    df.loc[10, "date"] = df.loc[9, "date"]   # 重复时间戳
    df.loc[20, "high"] = 90.0                # high < low
    report = check_ohlcv(df, "1h", now=NOW)
    assert not report.ok
    assert report.duplicates == 1 and report.ohlc_errors == 1


def test_stale_data_fails():
    report = check_ohlcv(make_df(), "1h", now=datetime(2026, 9, 1, tzinfo=timezone.utc))
    assert not report.ok
```

- [ ] Step 2: 实现 `quantlab/data_quality.py`

```python
"""K 线数据质量检查：缺口/重复/OHLC 一致性/零成交量/新鲜度。

原则：坏数据必须被主动发现——静默的坏数据会产出貌似可信的错误回测结论。
少量缺口是交易所维护的正常现象（软告警）；重复、OHLC 矛盾、数据过期是硬失败。
"""

import argparse
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from quantlab.strategy_loader import PROJECT_DIR

DATA_DIR = PROJECT_DIR / "user_data" / "data" / "okx"
TIMEFRAME_DELTAS = {
    "5m": timedelta(minutes=5), "15m": timedelta(minutes=15),
    "1h": timedelta(hours=1), "4h": timedelta(hours=4), "1d": timedelta(days=1),
}
GAP_HARD_LIMIT = 10          # 缺口超过此数视为硬失败
ZERO_VOLUME_PCT_LIMIT = 5.0


@dataclass
class DataReport:
    name: str
    rows: int = 0
    gaps: int = 0
    duplicates: int = 0
    ohlc_errors: int = 0
    zero_volume_pct: float = 0.0
    age_hours: float = 0.0
    problems: list = field(default_factory=list)
    warnings: list = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems


def check_ohlcv(df: pd.DataFrame, timeframe: str, now=None,
                max_age_hours: float = 48.0, name: str = "<df>") -> DataReport:
    delta = TIMEFRAME_DELTAS[timeframe]
    now = now or datetime.now(timezone.utc)
    report = DataReport(name=name, rows=len(df))

    report.duplicates = int(df["date"].duplicated().sum())
    if report.duplicates:
        report.problems.append(f"重复时间戳 {report.duplicates} 处")

    diffs = df["date"].diff().dropna()
    report.gaps = int((diffs != delta).sum())
    if report.gaps > GAP_HARD_LIMIT:
        report.problems.append(f"时间缺口 {report.gaps} 处 > {GAP_HARD_LIMIT}")
    elif report.gaps:
        report.warnings.append(f"时间缺口 {report.gaps} 处（交易所维护属正常，关注即可）")

    bad_high = df["high"] < df[["open", "close", "low"]].max(axis=1)
    bad_low = df["low"] > df[["open", "close", "high"]].min(axis=1)
    report.ohlc_errors = int((bad_high | bad_low).sum())
    if report.ohlc_errors:
        report.problems.append(f"OHLC 不一致 {report.ohlc_errors} 行")

    report.zero_volume_pct = float((df["volume"] <= 0).mean() * 100)
    if report.zero_volume_pct > ZERO_VOLUME_PCT_LIMIT:
        report.problems.append(f"零成交量占比 {report.zero_volume_pct:.1f}%")

    report.age_hours = (now - df["date"].iloc[-1]).total_seconds() / 3600
    if report.age_hours > max_age_hours:
        report.problems.append(f"数据过期 {report.age_hours:.0f}h > {max_age_hours}h（请 make data）")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="检查已下载 K 线的数据质量")
    parser.add_argument("--max-age-hours", type=float, default=48.0)
    args = parser.parse_args()

    files = sorted(DATA_DIR.glob("*.feather"))
    if not files:
        print(f"未找到数据文件：{DATA_DIR}（先运行 make data）")
        return 1

    failed = False
    for file in files:
        timeframe = file.stem.rsplit("-", 1)[-1]
        df = pd.read_feather(file)
        report = check_ohlcv(df, timeframe, max_age_hours=args.max_age_hours, name=file.name)
        status = "OK " if report.ok else "FAIL"
        print(f"[{status}] {report.name}: {report.rows} 行, 缺口 {report.gaps}, "
              f"最后K线 {report.age_hours:.1f}h 前")
        for message in report.problems:
            print(f"       ✗ {message}")
        for message in report.warnings:
            print(f"       ! {message}")
        failed = failed or not report.ok
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] Step 3: 单测通过后跑真实数据

Run: `.venv/bin/python -m quantlab.data_quality`
Expected: 4 个 feather 文件全 OK（数据 8 小时前刚下载）

- [ ] Step 4: Commit

```bash
git add quantlab/data_quality.py tests/test_data_quality.py
git commit -m "feat: 数据质量检查（缺口/重复/OHLC一致性/新鲜度）"
```

### Task 4: 回测结果解析 + walk-forward 编排器

**Files:**
- Create: `quantlab/backtest_io.py`、`quantlab/walk_forward.py`

**Interfaces:**
- Consumes: `build_windows`、`audit_params`、`load_effective_params`
- Produces: `read_backtest_metrics(export_path, strategy) -> dict`（profit_total/profit_total_abs/max_drawdown/sharpe/trades/market_change）；CLI `python -m quantlab.walk_forward --strategy X --epochs 30`，产物在 `user_data/walk_forward/<run_id>/`，报告写 `docs/results/03-walk-forward.md`。

- [ ] Step 1: 实现 `quantlab/backtest_io.py`

```python
"""解析 freqtrade backtesting --export trades 的导出结果（zip 内 json）。"""

import json
import zipfile
from pathlib import Path


def _load_export(export_path: Path) -> dict:
    zip_path = export_path.with_suffix(".zip")
    if zip_path.exists():
        with zipfile.ZipFile(zip_path) as archive:
            names = [n for n in archive.namelist()
                     if n.endswith(".json") and "config" not in n and not n.endswith(".meta.json")]
            preferred = [n for n in names if Path(n).name == export_path.name]
            with archive.open((preferred or sorted(names))[0]) as fh:
                return json.load(fh)
    return json.loads(export_path.read_text())


def read_backtest_metrics(export_path, strategy: str) -> dict:
    data = _load_export(Path(export_path))
    stats = data["strategy"][strategy]
    return {
        "profit_total": stats.get("profit_total", 0.0),
        "profit_total_abs": stats.get("profit_total_abs", 0.0),
        "max_drawdown": stats.get("max_drawdown_account", stats.get("max_drawdown", 0.0)),
        "sharpe": stats.get("sharpe", 0.0),
        "trades": stats.get("total_trades", 0),
        "market_change": stats.get("market_change", 0.0),
    }
```

- [ ] Step 2: 实现 `quantlab/walk_forward.py`

```python
"""Walk-forward 验证编排器：滚动『样本内优化 → 样本外检验』并汇总报告。

隔离原则：策略副本与参数都在运行专属目录（--strategy-path），
绝不触碰 user_data/strategies/ 下的生产文件——研究不得改变运行中 bot 的行为。
"""

import argparse
import shutil
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

from quantlab.backtest_io import read_backtest_metrics
from quantlab.risk_policy import audit_params
from quantlab.strategy_loader import DEFAULT_STRATEGY_DIR, PROJECT_DIR, load_effective_params
from quantlab.windows import build_windows

FT = PROJECT_DIR / ".venv" / "bin" / "freqtrade"
CONFIG = PROJECT_DIR / "config" / "config.json"
REPORT_TARGET = PROJECT_DIR / "docs" / "results" / "03-walk-forward.md"


def run_freqtrade(args: list[str]) -> None:
    result = subprocess.run([str(FT), *args], cwd=PROJECT_DIR,
                            capture_output=True, text=True)
    if result.returncode != 0:
        sys.stderr.write(result.stdout[-3000:] + result.stderr[-3000:])
        raise RuntimeError(f"freqtrade {args[0]} 失败（timerange 见上方输出）")


def run_window(index: int, window, strategy: str, strategy_dir: Path,
               out_dir: Path, epochs: int) -> dict:
    (strategy_dir / f"{strategy}.json").unlink(missing_ok=True)  # 每窗口从干净参数开始
    run_freqtrade([
        "hyperopt", "--config", str(CONFIG),
        "--strategy", strategy, "--strategy-path", str(strategy_dir),
        "--hyperopt-loss", "SharpeHyperOptLoss", "--spaces", "buy", "roi", "stoploss",
        "--timerange", window.is_timerange, "-e", str(epochs),
    ])
    shutil.copy(strategy_dir / f"{strategy}.json", out_dir / f"window_{index:02d}_params.json")
    effective = load_effective_params(strategy, strategy_dir)
    row = {
        "window": index,
        "is_range": window.is_timerange,
        "oos_range": window.oos_timerange,
        "stoploss": effective["stoploss"],
        "compliant": not audit_params(strategy, effective),
    }
    for phase, timerange in (("is", window.is_timerange), ("oos", window.oos_timerange)):
        export = out_dir / f"w{index:02d}_{phase}.json"
        run_freqtrade([
            "backtesting", "--config", str(CONFIG),
            "--strategy", strategy, "--strategy-path", str(strategy_dir),
            "--timerange", timerange,
            "--export", "trades", "--export-filename", str(export),
        ])
        row[phase] = read_backtest_metrics(export, strategy)
    return row


def render_report(strategy: str, run_id: str, epochs: int, rows: list[dict]) -> str:
    oos_profits = [r["oos"]["profit_total"] for r in rows]
    concat_return = 1.0
    for profit in oos_profits:
        concat_return *= 1 + profit
    concat_return -= 1
    positive = sum(1 for p in oos_profits if p > 0)
    decay = sum(r["oos"]["profit_total"] - r["is"]["profit_total"] for r in rows) / len(rows)
    compliant = sum(1 for r in rows if r["compliant"])

    lines = [
        "# Walk-Forward 验证报告",
        "",
        f"- 运行: `{run_id}` | 策略: {strategy} | 每窗口 hyperopt {epochs} epochs（SharpeHyperOptLoss）",
        f"- 窗口: 样本内 12 个月 → 样本外 3 个月，步长 3 个月，共 {len(rows)} 个",
        "- 产物与逐窗口参数存档: `user_data/walk_forward/" + run_id + "/`",
        "",
        "| # | 样本内区间 | IS 收益 | OOS 收益 | OOS Sharpe | OOS 回撤 | OOS 市场 | 交易数 | 参数合规 |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r['window']} | {r['is_range']} | {r['is']['profit_total']:+.2%} "
            f"| {r['oos']['profit_total']:+.2%} | {r['oos']['sharpe']:.2f} "
            f"| {r['oos']['max_drawdown']:.2%} | {r['oos']['market_change']:+.2%} "
            f"| {r['oos']['trades']} | {'✓' if r['compliant'] else '✗ 越界'} |")
    lines += [
        "",
        "## 汇总",
        "",
        f"- **OOS 拼接收益（各段连乘）: {concat_return:+.2%}** —— 这是最接近『真实使用』的数字",
        f"- OOS 为正的窗口: {positive}/{len(rows)}",
        f"- IS→OOS 平均衰减: {decay:+.2%}（负值 = 样本外普遍差于样本内，即过拟合程度）",
        f"- 优化参数通过风险政策审计: {compliant}/{len(rows)}"
        "（越界窗口说明优化器再次尝试卖风险换收益，已被审计标记）",
        "",
        "## 读法",
        "",
        "1. 只有当 OOS 拼接收益为正、且多数窗口 OOS 为正时，参数化流程才算有泛化能力。",
        "2. IS 好看 + OOS 难看 = 过拟合；IS/OOS 都难看 = 策略本身无效。",
        "3. 任何单窗口的好结果都不构成上线依据。",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="walk-forward 验证")
    parser.add_argument("--strategy", default="EmaRsiStrategy")
    parser.add_argument("--start", default="2023-01-01")
    parser.add_argument("--end", default=date.today().isoformat())
    parser.add_argument("--is-months", type=int, default=12)
    parser.add_argument("--oos-months", type=int, default=3)
    parser.add_argument("--step-months", type=int, default=3)
    parser.add_argument("--epochs", type=int, default=30)
    args = parser.parse_args()

    windows = build_windows(date.fromisoformat(args.start), date.fromisoformat(args.end),
                            args.is_months, args.oos_months, args.step_months)
    if not windows:
        print("时间范围不足以构成任何窗口")
        return 1

    run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir = PROJECT_DIR / "user_data" / "walk_forward" / run_id
    strategy_dir = out_dir / "strategy"
    strategy_dir.mkdir(parents=True)
    shutil.copy(DEFAULT_STRATEGY_DIR / f"{args.strategy}.py", strategy_dir)

    print(f"walk-forward: {len(windows)} 个窗口, 策略 {args.strategy}, run={run_id}")
    rows = []
    for index, window in enumerate(windows):
        print(f"[{index + 1}/{len(windows)}] IS {window.is_timerange} → OOS {window.oos_timerange} ...", flush=True)
        row = run_window(index, window, args.strategy, strategy_dir, out_dir, args.epochs)
        print(f"    IS {row['is']['profit_total']:+.2%} | OOS {row['oos']['profit_total']:+.2%}"
              f" | 合规 {'✓' if row['compliant'] else '✗'}", flush=True)
        rows.append(row)

    report = render_report(args.strategy, run_id, args.epochs, rows)
    (out_dir / "report.md").write_text(report)
    REPORT_TARGET.write_text(report)
    print(f"报告: {REPORT_TARGET} （存档: {out_dir / 'report.md'}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] Step 3: 冒烟验证（单窗口，快速）

Run: `.venv/bin/python -m quantlab.walk_forward --start 2025-01-01 --end 2026-05-01 --epochs 10`
Expected: 1 个窗口跑通，产出报告；如 zip 结构/字段名与假设不符，按实际结构修正 `backtest_io.py`

- [ ] Step 4: Commit

```bash
git add quantlab/backtest_io.py quantlab/walk_forward.py
git commit -m "feat: walk-forward 验证编排器（策略目录隔离+参数合规标注）"
```

### Task 5: 运行完整 walk-forward 并沉淀报告

- [ ] Step 1: 全量运行（约 10 个窗口，数分钟）

Run: `.venv/bin/python -m quantlab.walk_forward --strategy EmaRsiStrategy --epochs 30`

- [ ] Step 2: 检查 `docs/results/03-walk-forward.md`，在文末补充一段人工解读（对照 02 报告的单次切分结论）

- [ ] Step 3: Commit

```bash
git add docs/results/03-walk-forward.md
git commit -m "docs: EmaRsiStrategy walk-forward 多窗口验证报告"
```

### Task 6: 健康巡检 + launchd 定时 + 本地通知

**Files:**
- Create: `quantlab/health.py`、`scripts/health_install.sh`、`scripts/health_uninstall.sh`

**Interfaces:**
- Produces: CLI `python -m quantlab.health [--notify]`（异常退出码 1；--notify 时发 macOS 通知）；launchd 任务 `com.quantbot.healthcheck` 每 15 分钟运行并追加 `user_data/logs/health.log`。

- [ ] Step 1: 实现 `quantlab/health.py`

```python
"""健康巡检：launchd 服务/进程/API/日志新鲜度，异常时 macOS 本地通知。"""

import argparse
import base64
import json
import os
import subprocess
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

from quantlab.strategy_loader import PROJECT_DIR

LOG_FILE = PROJECT_DIR / "user_data" / "logs" / "freqtrade.log"
API_BASE = "http://127.0.0.1:8080/api/v1"
BOT_LABEL = "com.quantbot.dryrun"
LOG_FRESH_SECONDS = 600  # 心跳 60s，10 分钟无写入即异常


def load_env() -> dict:
    env = {}
    for line in (PROJECT_DIR / ".env").read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            env[key.strip()] = value.strip()
    return env


def check_service() -> bool:
    result = subprocess.run(
        ["launchctl", "print", f"gui/{os.getuid()}/{BOT_LABEL}"],
        capture_output=True)
    return result.returncode == 0


def check_process() -> bool:
    return subprocess.run(["pgrep", "-f", "freqtrade trade"],
                          capture_output=True).returncode == 0


def check_api_running(env: dict) -> bool:
    with urllib.request.urlopen(f"{API_BASE}/ping", timeout=5) as response:
        if json.load(response).get("status") != "pong":
            return False
    token = base64.b64encode(
        f"{env['FT_API_USERNAME']}:{env['FT_API_PASSWORD']}".encode()).decode()
    request = urllib.request.Request(
        f"{API_BASE}/show_config", headers={"Authorization": f"Basic {token}"})
    with urllib.request.urlopen(request, timeout=5) as response:
        return json.load(response).get("state") == "running"


def check_log_fresh() -> bool:
    return LOG_FILE.exists() and time.time() - LOG_FILE.stat().st_mtime <= LOG_FRESH_SECONDS


def notify(message: str) -> None:
    subprocess.run(
        ["osascript", "-e",
         f'display notification "{message}" with title "quant-bot 巡检告警"'],
        capture_output=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="quant-bot 健康巡检")
    parser.add_argument("--notify", action="store_true", help="异常时发送 macOS 本地通知")
    args = parser.parse_args()

    failures = []
    checks = [("launchd 服务", check_service), ("进程", check_process),
              ("日志新鲜度", check_log_fresh)]
    for name, check in checks:
        try:
            ok = check()
        except Exception:
            ok = False
        if not ok:
            failures.append(name)
    try:
        if not check_api_running(load_env()):
            failures.append("API 状态")
    except Exception:
        failures.append("API 可达性")

    timestamp = datetime.now().strftime("%F %T")
    if failures:
        message = "、".join(failures) + " 异常"
        print(f"[{timestamp}] FAIL: {message}")
        if args.notify:
            notify(message)
        return 1
    print(f"[{timestamp}] OK: 服务/进程/API/日志 全部正常")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] Step 2: 手动验证两种状态

Run: `.venv/bin/python -m quantlab.health` → OK 退出码 0
Run: `./scripts/bot_stop.sh && .venv/bin/python -m quantlab.health --notify; ./scripts/bot_start.sh`
Expected: FAIL 且弹出 macOS 通知，随后恢复启动

- [ ] Step 3: 写 `scripts/health_install.sh`（launchd 定时巡检，15 分钟一次）

```bash
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

LABEL="com.quantbot.healthcheck"
PLIST="$HOME/Library/LaunchAgents/${LABEL}.plist"
PROJECT_DIR="$(pwd)"

launchctl bootout "gui/$(id -u)/${LABEL}" 2>/dev/null || true
mkdir -p user_data/logs
cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>${LABEL}</string>
    <key>ProgramArguments</key>
    <array>
        <string>${PROJECT_DIR}/.venv/bin/python</string>
        <string>-m</string><string>quantlab.health</string><string>--notify</string>
    </array>
    <key>WorkingDirectory</key><string>${PROJECT_DIR}</string>
    <key>StartInterval</key><integer>900</integer>
    <key>RunAtLoad</key><true/>
    <key>StandardOutPath</key><string>${PROJECT_DIR}/user_data/logs/health.log</string>
    <key>StandardErrorPath</key><string>${PROJECT_DIR}/user_data/logs/health.log</string>
</dict>
</plist>
EOF
chmod 600 "$PLIST"
launchctl bootstrap "gui/$(id -u)" "$PLIST"
echo "巡检任务已安装（launchd: ${LABEL}，每 15 分钟一次，日志 user_data/logs/health.log）"
```

- [ ] Step 4: 写 `scripts/health_uninstall.sh`（对称卸载），`chmod +x`，安装并验证 `health.log` 出现首条 OK 记录

- [ ] Step 5: Commit

```bash
git add quantlab/health.py scripts/health_*.sh
git commit -m "feat: 健康巡检 + launchd 定时任务 + macOS 本地告警"
```

### Task 7: Makefile / README 集成与全量验收

**Files:**
- Modify: `Makefile`（新增 audit/data-check/wf/health/health-install/health-uninstall/check）、`README.md`

- [ ] Step 1: Makefile 新增目标

```makefile
audit: ## 风险政策审计（config + 策略生效参数）
	.venv/bin/python -m quantlab.risk_policy

data-check: ## 数据质量检查（缺口/重复/新鲜度）
	.venv/bin/python -m quantlab.data_quality

wf: ## walk-forward 验证（STRATEGY/EPOCHS 可覆盖）
	.venv/bin/python -m quantlab.walk_forward --strategy $(or $(STRATEGY),EmaRsiStrategy) --epochs $(or $(EPOCHS),30)

health: ## 健康巡检（手动）
	.venv/bin/python -m quantlab.health

health-install: ## 安装 15 分钟定时巡检（launchd）
	./scripts/health_install.sh

health-uninstall: ## 卸载定时巡检
	./scripts/health_uninstall.sh

check: ## 一键体检：测试 + 风险审计 + 数据质量
	.venv/bin/python -m pytest tests/ -q
	.venv/bin/python -m quantlab.risk_policy
	.venv/bin/python -m quantlab.data_quality
```

- [ ] Step 2: README 更新：定位段加入"生产化四特质"；快速开始加入 `make check` 与 `make health-install`；日常工作流改为"改动 → make check → make wf → 看模拟盘"；目录结构加 `quantlab/`；风控段落写明"风险政策代码化 + 启动强制审计"。

- [ ] Step 3: 全量验收

Run: `make check` → 全绿；`make bot-status` → 运行中；`git status` → 干净

- [ ] Step 4: Commit

```bash
git add Makefile README.md && git commit -m "feat: make check 一键体检与生产化文档更新"
```

---

## Self-Review 记录

- 规格覆盖：设计 §3.1-3.5 分别由 Task 1/2/3/4+5/6 实现；§4 由 Task 7 实现；§6 成功标准 1→Task 7、2→Task 5、3→Task 2、4→Task 6、5→全程 dry-run 不变。
- 占位符：无。回测 json 字段名（profit_total 等）基于 backtesting-show 的输出推断，Task 4 Step 3 冒烟窗口显式验证并允许按实际修正——已写入步骤，不属于隐式假设。
- 一致性：`PROJECT_DIR`/`DEFAULT_STRATEGY_DIR` 由 strategy_loader 单点导出；`audit_params` 签名在 Task 2 定义、Task 4 消费一致；Violation `__str__` 含"止损"文案与测试断言一致。
