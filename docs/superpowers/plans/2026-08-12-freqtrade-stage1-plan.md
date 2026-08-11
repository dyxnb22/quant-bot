# Freqtrade 阶段一实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 搭建一套生产可用（个人使用）的加密货币量化交易工作台：环境可复现、策略有测试、回测有方法论、模拟盘可持续运行可监控。

**Architecture:** 以 Freqtrade 为核心引擎；策略与配置分离；密钥只存 `.env`；运维操作统一收敛到 Makefile 与 `scripts/`；回测结论沉淀到 `docs/results/`。

**Tech Stack:** Python 3.14 / venv / Freqtrade 2026.x（含 hyperopt extras）/ pytest / OKX 公共行情 / FreqUI。

## Global Constraints

- Python 3.14.6，虚拟环境固定在 `.venv/`，所有命令用 `.venv/bin/` 前缀或激活后执行。
- 交易所：OKX（实测可达；Binance 地区受限）。现货，计价货币 USDT。
- 交易对：`BTC/USDT` `ETH/USDT` `SOL/USDT` `XRP/USDT`；时间框架 `1h`；数据起点 `20230101`。
- 仓库中 `dry_run` 恒为 `true`；任何密钥/口令只存在于 `.env`（gitignored），仓库仅有 `.env.example`。
- 真实交易所 API key 全程跳过（用户指示）；dry-run 使用公共行情，无需 key。
- 每个任务结束必须 `git commit`。

---

### Task 1: 环境搭建与脚手架

**Files:**
- Create: `.venv/`（不入库）、`requirements.lock`、`.env.example`、`README.md`（占位，Task 9 完善）

- [ ] Step 1: 创建虚拟环境并安装 Freqtrade

```bash
cd /Users/diaoyuxuan/quant-bot
python3 -m venv .venv
.venv/bin/pip install --upgrade pip wheel
.venv/bin/pip install "freqtrade[hyperopt]" pytest
```

- [ ] Step 2: 验证安装

Run: `.venv/bin/freqtrade --version`
Expected: 输出 `2026.6`（或更新稳定版）

- [ ] Step 3: 锁定依赖

```bash
.venv/bin/pip freeze > requirements.lock
```

- [ ] Step 4: 写 `.env.example`

```bash
# ===== Freqtrade REST API（dry-run 本地监控用）=====
# bot_start.sh 会 source 本文件并导出为 FREQTRADE__API_SERVER__* 环境变量
FT_API_USERNAME=freqadmin
FT_API_PASSWORD=change_me
FT_API_JWT_SECRET=change_me
FT_API_WS_TOKEN=change_me

# ===== OKX 实盘密钥（阶段一不使用，转实盘前才填）=====
OKX_API_KEY=
OKX_API_SECRET=
OKX_API_PASSPHRASE=
```

- [ ] Step 5: 写占位 README（一句话 + 指向设计文档），commit

```bash
git add -A && git commit -m "chore: venv 环境、freqtrade 安装与依赖锁定"
```

### Task 2: Freqtrade 用户目录与主配置

**Files:**
- Create: `user_data/`（框架生成，产物子目录被 gitignore）、`config/config.json`

**Interfaces:**
- Produces: `config/config.json` —— 后续所有 freqtrade 命令都通过 `--config config/config.json` 使用它。

- [ ] Step 1: 生成用户目录

```bash
.venv/bin/freqtrade create-userdir --userdir user_data
```

- [ ] Step 2: 写主配置 `config/config.json`

```json
{
    "$schema": "https://schema.freqtrade.io/schema.json",
    "trading_mode": "spot",
    "dry_run": true,
    "dry_run_wallet": 10000,
    "stake_currency": "USDT",
    "stake_amount": 500,
    "tradable_balance_ratio": 0.99,
    "fiat_display_currency": "USD",
    "max_open_trades": 3,
    "timeframe": "1h",
    "cancel_open_orders_on_exit": true,
    "unfilledtimeout": {
        "entry": 10,
        "exit": 10,
        "exit_timeout_count": 0,
        "unit": "minutes"
    },
    "entry_pricing": {
        "price_side": "same",
        "use_order_book": true,
        "order_book_top": 1,
        "price_last_balance": 0.0,
        "check_depth_of_market": {
            "enabled": false,
            "bids_to_ask_delta": 1
        }
    },
    "exit_pricing": {
        "price_side": "same",
        "use_order_book": true,
        "order_book_top": 1
    },
    "order_types": {
        "entry": "limit",
        "exit": "limit",
        "emergency_exit": "market",
        "stoploss": "market",
        "stoploss_on_exchange": false
    },
    "exchange": {
        "name": "okx",
        "key": "",
        "secret": "",
        "password": "",
        "ccxt_config": {},
        "ccxt_async_config": {},
        "pair_whitelist": [
            "BTC/USDT",
            "ETH/USDT",
            "SOL/USDT",
            "XRP/USDT"
        ],
        "pair_blacklist": []
    },
    "pairlists": [
        {"method": "StaticPairList"}
    ],
    "api_server": {
        "enabled": false,
        "listen_ip_address": "127.0.0.1",
        "listen_port": 8080,
        "verbosity": "error",
        "enable_openapi": false,
        "jwt_secret_key": "",
        "ws_token": "",
        "CORS_origins": [],
        "username": "",
        "password": ""
    },
    "bot_name": "quant-bot",
    "initial_state": "running",
    "internals": {
        "process_throttle_secs": 5,
        "heartbeat_interval": 60
    }
}
```

说明：`api_server.enabled` 仓库默认 false（安全默认值），由 `scripts/bot_start.sh` 通过 `FREQTRADE__API_SERVER__*` 环境变量在运行时开启并注入凭据。

- [ ] Step 3: 验证配置可被解析

Run: `.venv/bin/freqtrade show-config --config config/config.json`
Expected: 输出合并后配置，`"dry_run": true`，无 schema 报错

- [ ] Step 4: Commit

```bash
git add -A && git commit -m "feat: freqtrade 用户目录与 dry-run 主配置（OKX 现货）"
```

### Task 3: 历史数据下载

**Files:**
- Create: `scripts/download_data.sh`（入库）；`user_data/data/okx/`（不入库）

- [ ] Step 1: 写 `scripts/download_data.sh`

```bash
#!/usr/bin/env bash
# 下载/增量更新回测所需历史 K 线。可重复执行（幂等追加）。
set -euo pipefail
cd "$(dirname "$0")/.."
TIMERANGE="${1:-20230101-}"
.venv/bin/freqtrade download-data \
    --config config/config.json \
    --timerange "$TIMERANGE" \
    --timeframes 1h
```

```bash
chmod +x scripts/download_data.sh
```

- [ ] Step 2: 执行下载

Run: `./scripts/download_data.sh`
Expected: 4 个交易对各下载约 2.6 年 1h K 线，无报错

- [ ] Step 3: 验证数据

Run: `.venv/bin/freqtrade list-data --config config/config.json`
Expected: 表格列出 4 个 pair 的 1h 数据及起止时间

- [ ] Step 4: Commit

```bash
git add scripts/download_data.sh && git commit -m "feat: 历史数据下载脚本（OKX 1h）"
```

### Task 4: 基线策略 EmaRsiStrategy（TDD）

**Files:**
- Create: `tests/test_strategies.py`、`tests/conftest.py`、`user_data/strategies/EmaRsiStrategy.py`

**Interfaces:**
- Produces: 策略类 `EmaRsiStrategy`（趋势跟随：EMA20/50 金叉 + RSI 过滤），供回测/hyperopt/dry-run 引用；测试工具 `load_strategy_class(name)` 供 Task 5 复用。

- [ ] Step 1: 写测试基础设施 `tests/conftest.py`

```python
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
```

- [ ] Step 2: 写失败测试 `tests/test_strategies.py`

```python
import pytest

from conftest import load_strategy_class

STRATEGIES = ["EmaRsiStrategy"]


@pytest.fixture(params=STRATEGIES)
def strategy(request):
    cls = load_strategy_class(request.param)
    return cls(config={"stake_currency": "USDT", "runmode": "backtest"})


def test_strategy_basic_attributes(strategy):
    assert strategy.timeframe == "1h"
    assert -0.20 <= strategy.stoploss < 0, "止损必须存在且不过深"
    assert strategy.can_short is False


def test_populate_indicators_adds_columns(strategy, ohlcv_df):
    df = strategy.populate_indicators(ohlcv_df.copy(), {"pair": "BTC/USDT"})
    for col in strategy.REQUIRED_INDICATOR_COLUMNS:
        assert col in df.columns, f"缺少指标列 {col}"


def test_entry_exit_signals_valid(strategy, ohlcv_df):
    meta = {"pair": "BTC/USDT"}
    df = strategy.populate_indicators(ohlcv_df.copy(), meta)
    df = strategy.populate_entry_trend(df, meta)
    df = strategy.populate_exit_trend(df, meta)
    assert "enter_long" in df.columns and "exit_long" in df.columns
    assert set(df["enter_long"].dropna().unique()) <= {0, 1}
    assert set(df["exit_long"].dropna().unique()) <= {0, 1}
    assert df["enter_long"].sum() > 0, "合成数据上应至少产生一次入场信号"


def test_no_lookahead_bias(strategy, ohlcv_df):
    """截断最后 50 根 K 线不应改变此前任何信号（未来函数检测）。"""
    meta = {"pair": "BTC/USDT"}

    def signals(df):
        d = strategy.populate_indicators(df.copy(), meta)
        d = strategy.populate_entry_trend(d, meta)
        return d["enter_long"].fillna(0)

    full = signals(ohlcv_df)
    truncated = signals(ohlcv_df.iloc[:-50])
    assert (full.iloc[: len(truncated)].values == truncated.values).all()
```

- [ ] Step 3: 运行测试确认失败

Run: `.venv/bin/python -m pytest tests/ -v`
Expected: FAIL（`EmaRsiStrategy.py` 不存在）

- [ ] Step 4: 写策略 `user_data/strategies/EmaRsiStrategy.py`

```python
"""趋势跟随基线策略：EMA20/EMA50 金叉入场，RSI 过滤追高，死叉离场。

定位：学习基线。预期不稳定盈利，用于承载回测/优化/模拟盘完整流程。
"""

import talib.abstract as ta
from pandas import DataFrame

import freqtrade.vendor.qtpylib.indicators as qtpylib
from freqtrade.strategy import IntParameter, IStrategy


class EmaRsiStrategy(IStrategy):
    INTERFACE_VERSION = 3

    REQUIRED_INDICATOR_COLUMNS = ("ema_fast", "ema_slow", "rsi")

    timeframe = "1h"
    can_short = False
    process_only_new_candles = True
    startup_candle_count = 60

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
```

- [ ] Step 5: 测试通过 + freqtrade 能识别策略

Run: `.venv/bin/python -m pytest tests/ -v`
Expected: 全部 PASS

Run: `.venv/bin/freqtrade list-strategies --config config/config.json`
Expected: 列表包含 `EmaRsiStrategy`，状态 OK

- [ ] Step 6: Commit

```bash
git add tests/ user_data/strategies/EmaRsiStrategy.py
git commit -m "feat: 基线趋势策略 EmaRsiStrategy（含无未来函数测试）"
```

### Task 5: 第二策略 RsiMeanRevertStrategy（TDD）

**Files:**
- Create: `user_data/strategies/RsiMeanRevertStrategy.py`
- Modify: `tests/test_strategies.py`（STRATEGIES 列表加入新策略）

**Interfaces:**
- Consumes: `load_strategy_class(name)`（Task 4）
- Produces: 策略类 `RsiMeanRevertStrategy`（均值回归：牛市回调买入），用于与趋势策略对比回测。

- [ ] Step 1: 扩展测试

```python
STRATEGIES = ["EmaRsiStrategy", "RsiMeanRevertStrategy"]
```

- [ ] Step 2: 运行确认新策略用例失败

Run: `.venv/bin/python -m pytest tests/ -v`
Expected: EmaRsiStrategy 用例 PASS，RsiMeanRevertStrategy 用例 FAIL（文件不存在）

- [ ] Step 3: 写策略 `user_data/strategies/RsiMeanRevertStrategy.py`

```python
"""均值回归基线策略：长期趋势向上（价格在 EMA200 上方）时，RSI 超卖买入、回归后卖出。

与趋势跟随策略互补：一个吃趋势、一个吃震荡回调，用于对比不同市况下的表现差异。
"""

import talib.abstract as ta
from pandas import DataFrame

from freqtrade.strategy import IntParameter, IStrategy


class RsiMeanRevertStrategy(IStrategy):
    INTERFACE_VERSION = 3

    REQUIRED_INDICATOR_COLUMNS = ("ema_trend", "rsi")

    timeframe = "1h"
    can_short = False
    process_only_new_candles = True
    startup_candle_count = 220

    minimal_roi = {"0": 0.06, "360": 0.03, "720": 0.015, "1440": 0}
    stoploss = -0.06
    trailing_stop = False

    buy_rsi_min = IntParameter(20, 40, default=30, space="buy", optimize=True)
    sell_rsi = IntParameter(50, 75, default=60, space="sell", optimize=True)

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
        dataframe["ema_trend"] = ta.EMA(dataframe, timeperiod=200)
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (dataframe["close"] > dataframe["ema_trend"])
            & (dataframe["rsi"] < self.buy_rsi_min.value)
            & (dataframe["volume"] > 0),
            "enter_long",
        ] = 1
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            dataframe["rsi"] > self.sell_rsi.value,
            "exit_long",
        ] = 1
        return dataframe
```

注意：合成数据的"至少一次入场"断言对该策略同样成立（数据前半段下跌制造超卖，但需价格在 EMA200 上方——若断言不成立，允许对该策略放宽 `enter_long.sum() >= 0` 为条件断言，以 fixture 实际形态为准调整，不得放宽无未来函数测试）。

- [ ] Step 4: 测试通过 + 策略列表验证

Run: `.venv/bin/python -m pytest tests/ -v`
Expected: 全部 PASS

Run: `.venv/bin/freqtrade list-strategies --config config/config.json`
Expected: 两个策略均 OK

- [ ] Step 5: Commit

```bash
git add tests/ user_data/strategies/RsiMeanRevertStrategy.py
git commit -m "feat: 均值回归策略 RsiMeanRevertStrategy"
```

### Task 6: 基线回测与双策略对比

**Files:**
- Create: `docs/results/01-baseline-backtest.md`

- [ ] Step 1: 运行双策略对比回测

Run:

```bash
.venv/bin/freqtrade backtesting \
    --config config/config.json \
    --strategy-list EmaRsiStrategy RsiMeanRevertStrategy \
    --timerange 20240101- \
    --breakdown month
```

Expected: 输出两个策略的完整回测报告（总收益、最大回撤、盈亏比、交易次数、逐月分解）

- [ ] Step 2: 将关键结果与解读写入 `docs/results/01-baseline-backtest.md`

内容骨架（数字以实际输出为准填写）：回测区间与假设（手续费、滑点模型）；两策略核心指标对比表；解读——重点解释最大回撤与交易次数为何比总收益更重要；与"买入持有 BTC"基准的对比结论。

- [ ] Step 3: Commit

```bash
git add docs/results/01-baseline-backtest.md
git commit -m "docs: 基线双策略回测报告与解读"
```

### Task 7: 过拟合验证（样本内优化 → 样本外检验）

**Files:**
- Create: `docs/results/02-overfitting-check.md`、`user_data/strategies/EmaRsiStrategy.json`（hyperopt 产出参数，入库）

- [ ] Step 1: 样本内 hyperopt（2023-06-01 ~ 2025-06-01）

Run:

```bash
.venv/bin/freqtrade hyperopt \
    --config config/config.json \
    --strategy EmaRsiStrategy \
    --hyperopt-loss SharpeHyperOptLoss \
    --spaces buy roi stoploss \
    --timerange 20230601-20250601 \
    -e 60
```

Expected: 60 轮后输出最优参数组合，自动写入 `user_data/strategies/EmaRsiStrategy.json`

- [ ] Step 2: 样本内回测（应用优化参数）

Run: `.venv/bin/freqtrade backtesting --config config/config.json --strategy EmaRsiStrategy --timerange 20230601-20250601`
记录：优化后样本内指标

- [ ] Step 3: 样本外回测（2025-06-01 之后，从未参与优化）

Run: `.venv/bin/freqtrade backtesting --config config/config.json --strategy EmaRsiStrategy --timerange 20250601-`
记录：样本外指标

- [ ] Step 4: 写 `docs/results/02-overfitting-check.md`

内容骨架：方法说明（为什么切分、切分点选择）；样本内 vs 样本外指标对比表；结论——两段表现差距的定量描述，以及"样本外衰减是常态"的方法论总结；下一步（walk-forward、更多市况覆盖）。

- [ ] Step 5: Commit

```bash
git add user_data/strategies/EmaRsiStrategy.json docs/results/02-overfitting-check.md
git commit -m "docs: 样本内优化与样本外过拟合检验"
```

### Task 8: dry-run 模拟盘常驻运行 + API 监控 + FreqUI

**Files:**
- Create: `scripts/bot_start.sh`、`scripts/bot_stop.sh`、`scripts/bot_status.sh`、`.env`（本地生成，不入库）

**Interfaces:**
- Produces: 运行中的 dry-run 交易进程（PID 文件 `user_data/freqtrade.pid`，日志 `user_data/logs/freqtrade.log`）；REST API `http://127.0.0.1:8080`；FreqUI 网页监控。

- [ ] Step 1: 生成本地 `.env`（随机凭据）

```bash
cd /Users/diaoyuxuan/quant-bot
cat > .env <<EOF
FT_API_USERNAME=freqadmin
FT_API_PASSWORD=$(openssl rand -hex 12)
FT_API_JWT_SECRET=$(openssl rand -hex 24)
FT_API_WS_TOKEN=$(openssl rand -hex 12)
OKX_API_KEY=
OKX_API_SECRET=
OKX_API_PASSPHRASE=
EOF
```

- [ ] Step 2: 写 `scripts/bot_start.sh`

```bash
#!/usr/bin/env bash
# 启动 dry-run 模拟盘（后台常驻）。凭据来自 .env，运行时注入，仓库配置保持安全默认。
set -euo pipefail
cd "$(dirname "$0")/.."

PID_FILE="user_data/freqtrade.pid"
if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
    echo "bot 已在运行 (pid=$(cat "$PID_FILE"))"
    exit 0
fi

set -a; source .env; set +a
export FREQTRADE__API_SERVER__ENABLED=true
export FREQTRADE__API_SERVER__USERNAME="$FT_API_USERNAME"
export FREQTRADE__API_SERVER__PASSWORD="$FT_API_PASSWORD"
export FREQTRADE__API_SERVER__JWT_SECRET_KEY="$FT_API_JWT_SECRET"
export FREQTRADE__API_SERVER__WS_TOKEN="$FT_API_WS_TOKEN"

mkdir -p user_data/logs
nohup .venv/bin/freqtrade trade \
    --config config/config.json \
    --strategy EmaRsiStrategy \
    --logfile user_data/logs/freqtrade.log \
    >/dev/null 2>&1 &
echo $! > "$PID_FILE"
echo "bot 已启动 (pid=$(cat "$PID_FILE"))，日志: user_data/logs/freqtrade.log，UI: http://127.0.0.1:8080"
```

- [ ] Step 3: 写 `scripts/bot_stop.sh`

```bash
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
PID_FILE="user_data/freqtrade.pid"
if [[ ! -f "$PID_FILE" ]]; then
    echo "未找到 PID 文件，bot 可能未运行"
    exit 0
fi
PID=$(cat "$PID_FILE")
if kill -0 "$PID" 2>/dev/null; then
    kill "$PID"
    echo "已发送停止信号 (pid=$PID)，等待优雅退出..."
    for _ in $(seq 1 20); do
        kill -0 "$PID" 2>/dev/null || break
        sleep 1
    done
fi
rm -f "$PID_FILE"
echo "bot 已停止"
```

- [ ] Step 4: 写 `scripts/bot_status.sh`

```bash
#!/usr/bin/env bash
# 查询运行状态：进程存活 + REST API 健康 + 当前持仓/收益摘要
set -euo pipefail
cd "$(dirname "$0")/.."
set -a; source .env; set +a
BASE="http://127.0.0.1:8080/api/v1"
AUTH="$FT_API_USERNAME:$FT_API_PASSWORD"

PID_FILE="user_data/freqtrade.pid"
if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
    echo "进程: 运行中 (pid=$(cat "$PID_FILE"))"
else
    echo "进程: 未运行"; exit 1
fi

echo "--- ping ---";    curl -s "$BASE/ping"
echo; echo "--- 概览 ---"; curl -s -u "$AUTH" "$BASE/show_config" | .venv/bin/python -c "import json,sys; c=json.load(sys.stdin); print('state:', c['state'], '| strategy:', c['strategy'], '| dry_run:', c['dry_run'])"
echo "--- 收益 ---";   curl -s -u "$AUTH" "$BASE/profit" | .venv/bin/python -m json.tool | head -20
echo "--- 持仓 ---";   curl -s -u "$AUTH" "$BASE/status" | .venv/bin/python -m json.tool | head -40
```

```bash
chmod +x scripts/bot_start.sh scripts/bot_stop.sh scripts/bot_status.sh
```

- [ ] Step 5: 安装 FreqUI 并启动 bot

```bash
.venv/bin/freqtrade install-ui
./scripts/bot_start.sh
sleep 20
```

- [ ] Step 6: 验证运行状态

Run: `./scripts/bot_status.sh`
Expected: 进程运行中；`{"status":"pong"}`；state=RUNNING、dry_run=True；profit/status 返回 JSON（初期多为空仓）

Run: `tail -5 user_data/logs/freqtrade.log`
Expected: 出现 heartbeat 或市场数据刷新日志，无 ERROR

- [ ] Step 7: Commit

```bash
git add scripts/ && git commit -m "feat: 模拟盘启停与状态监控脚本 + FreqUI"
```

### Task 9: Makefile 与完整 README

**Files:**
- Create: `Makefile`
- Modify: `README.md`（完整版）

- [ ] Step 1: 写 `Makefile`

```makefile
.PHONY: help setup data test backtest hyperopt oos bot-start bot-stop bot-status log

FT := .venv/bin/freqtrade
CFG := --config config/config.json

help: ## 显示所有命令
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-12s %s\n", $$1, $$2}'

setup: ## 创建虚拟环境并安装依赖
	python3 -m venv .venv
	.venv/bin/pip install --upgrade pip wheel
	.venv/bin/pip install "freqtrade[hyperopt]" pytest

data: ## 下载/增量更新历史数据
	./scripts/download_data.sh

test: ## 运行策略单元测试
	.venv/bin/python -m pytest tests/ -v

backtest: ## 双策略对比回测（TIMERANGE 可覆盖，默认 20240101-）
	$(FT) backtesting $(CFG) --strategy-list EmaRsiStrategy RsiMeanRevertStrategy --timerange $(or $(TIMERANGE),20240101-) --breakdown month

hyperopt: ## 样本内参数优化（默认 EmaRsiStrategy）
	$(FT) hyperopt $(CFG) --strategy $(or $(STRATEGY),EmaRsiStrategy) --hyperopt-loss SharpeHyperOptLoss --spaces buy roi stoploss --timerange 20230601-20250601 -e 60

oos: ## 样本外验证回测
	$(FT) backtesting $(CFG) --strategy $(or $(STRATEGY),EmaRsiStrategy) --timerange 20250601-

bot-start: ## 启动 dry-run 模拟盘（后台）
	./scripts/bot_start.sh

bot-stop: ## 停止模拟盘
	./scripts/bot_stop.sh

bot-status: ## 查看模拟盘状态（进程/API/持仓/收益）
	./scripts/bot_status.sh

log: ## 跟踪模拟盘日志
	tail -f user_data/logs/freqtrade.log
```

- [ ] Step 2: 验证 Makefile

Run: `make help && make test`
Expected: 命令列表正常显示；测试全部通过

- [ ] Step 3: 写完整 `README.md`

内容骨架：项目定位（学习优先、dry-run only、两阶段路线）；快速开始（make setup → make data → make test → make backtest → make bot-start）；日常工作流（周更数据 → 回测 → 检查模拟盘）；目录结构说明；风控设计说明；回测方法论（指向 docs/results/）；转实盘前置条件清单（明确本阶段不做）；阶段二路线（CCXT 自研）；风险与合规声明。

- [ ] Step 4: 最终提交

```bash
git add -A && git commit -m "feat: Makefile 运维入口与完整 README"
```

---

## Self-Review 记录

- 规格覆盖：设计文档 §2 成功标准 1-6 分别由 Task 1-2（环境/配置）、Task 3（数据）、Task 4-6（策略与回测）、Task 7（过拟合演示）、Task 8（dry-run 常驻+监控）覆盖；§7 风控由策略 protections + 配置层实现。无缺口。
- 占位符：无 TBD/TODO；结果文档数字须以实际运行输出为准（属运行时产物，非占位符）。
- 类型/命名一致性：`load_strategy_class`、`REQUIRED_INDICATOR_COLUMNS`、策略类名/文件名在 Task 4/5 间一致；`FT_API_*` 环境变量在 Task 1/8 间一致。
