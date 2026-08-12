# 体制过滤研究迭代实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 检验研究假设——"给趋势策略加长期趋势体制闸门（close > EMA200）能显著减少熊市窗口亏损、改善 OOS 拼接收益"，并依据 walk-forward 证据决定模拟盘运行哪个策略。

**Architecture:** 复用阶段 1.5 的验证流水线；新增策略 `EmaRsiTrendStrategy`（EmaRsi 信号 + 体制闸门）；WF 编排器增加 `--report-to` 保护历史报告；三管线（EmaRsi / EmaRsiTrend / RsiMeanRevert）对比后做部署决策。

**Tech Stack:** 不变（零新依赖，无新数据下载——闸门用 1h EMA200 ≈ 8.3 天趋势）。

## Global Constraints

- 假设依据：`docs/results/03-walk-forward.md` 第 3 条解读（OOS 亏损窗口与熊市完全重合）。
- 新策略必须纳入 `AUDITED_STRATEGIES` 与测试矩阵；体制闸门参数固定（EMA200），不给 hyperopt 增加过拟合面。
- 部署决策标准（写在前面防止事后合理化）：切换模拟盘策略当且仅当新策略 **OOS 拼接收益更高且 OOS 亏损窗口的平均亏损更小**；否则维持现状。

---

### Task 1: WF 编排器支持 --report-to

**Files:**
- Modify: `quantlab/walk_forward.py`

- [ ] Step 1: argparse 增加 `--report-to`（默认维持 `docs/results/03-walk-forward.md` 兼容），main 中 `REPORT_TARGET` 改为 `Path(args.report_to)`

```python
parser.add_argument("--report-to", default=str(REPORT_TARGET),
                    help="汇总报告写入路径（历史报告不被覆盖）")
```

- [ ] Step 2: 冒烟：`--help` 显示新参数；commit

```bash
git add quantlab/walk_forward.py && git commit -m "feat: walk-forward 支持 --report-to 保护历史报告"
```

### Task 2: EmaRsiTrendStrategy（TDD）

**Files:**
- Create: `user_data/strategies/EmaRsiTrendStrategy.py`
- Modify: `tests/test_strategies.py`（策略矩阵 + 体制闸门专项测试 + 上升趋势夹具）、`quantlab/risk_policy.py`（AUDITED_STRATEGIES）

**Interfaces:**
- Produces: 策略类 `EmaRsiTrendStrategy`——EmaRsi 原信号 ∧ close > EMA200（体制闸门，参数固定不可优化）；`REQUIRED_INDICATOR_COLUMNS = ("ema_fast", "ema_slow", "rsi", "ema_trend")`。

- [ ] Step 1: 测试矩阵加入新策略；`test_entry_exit_signals_valid` 的"至少一次入场"断言改为按策略选夹具（新策略用上升趋势夹具）；新增体制闸门专项测试

```python
# tests/test_strategies.py 顶部
STRATEGIES = ["EmaRsiStrategy", "RsiMeanRevertStrategy", "EmaRsiTrendStrategy"]


@pytest.fixture
def uptrend_df(ohlcv_df):
    """确立 EMA200 后的深回调-强反弹形态：保证体制闸门策略必然出现合规入场。"""
    import numpy as np
    import pandas as pd
    n = 700
    rng = np.random.default_rng(7)
    trend = np.concatenate([
        np.full(300, 100.0),          # 平台期（确立 EMA200）
        np.linspace(100, 88, 60),     # 回调（制造死叉）
        np.linspace(88, 150, 340),    # 强反弹（金叉时 close 远高于 EMA200）
    ])
    close = trend + rng.normal(0, 0.6, n)
    return pd.DataFrame({
        "date": pd.date_range("2024-01-01", periods=n, freq="1h", tz="UTC"),
        "open": close + rng.normal(0, 0.2, n),
        "high": close + np.abs(rng.normal(0, 0.6, n)) + 0.4,
        "low": close - np.abs(rng.normal(0, 0.6, n)) - 0.4,
        "close": close,
        "volume": rng.uniform(100, 1000, n),
    })


def test_trend_gate_blocks_entries_below_ema200(ohlcv_df):
    """体制闸门：所有入场信号必须发生在 close > ema_trend 的 K 线上。"""
    cls = load_strategy_class("EmaRsiTrendStrategy")
    strategy = cls(config={"stake_currency": "USDT", "runmode": "backtest"})
    meta = {"pair": "BTC/USDT"}
    df = strategy.populate_indicators(ohlcv_df.copy(), meta)
    df = strategy.populate_entry_trend(df, meta)
    entries = df[df["enter_long"] == 1]
    assert (entries["close"] > entries["ema_trend"]).all()


def test_trend_strategy_enters_in_uptrend(uptrend_df):
    cls = load_strategy_class("EmaRsiTrendStrategy")
    strategy = cls(config={"stake_currency": "USDT", "runmode": "backtest"})
    meta = {"pair": "BTC/USDT"}
    df = strategy.populate_indicators(uptrend_df.copy(), meta)
    df = strategy.populate_entry_trend(df, meta)
    assert df["enter_long"].sum() > 0
```

`test_entry_exit_signals_valid` 中 sum>0 断言对 `EmaRsiTrendStrategy` 跳过（由上面专项测试覆盖）：

```python
    if strategy.__class__.__name__ != "EmaRsiTrendStrategy":
        assert df["enter_long"].sum() > 0, "合成数据上应至少产生一次入场信号"
```

- [ ] Step 2: 运行确认新用例失败（策略文件不存在）

- [ ] Step 3: 实现策略（继承自 EmaRsi 的信号结构，闸门固定）

```python
"""趋势跟随 + 体制闸门：EmaRsi 原信号，且仅在长期趋势向上（close > EMA200）时入场。

研究依据：03 号 walk-forward 报告显示 EmaRsiStrategy 的 OOS 亏损窗口与熊市完全重合
（策略只有 beta）。本策略用体制闸门在熊市把敞口关掉。EMA200 周期固定，
不进入 hyperopt 空间——体制定义属于风险政策范畴，不属于可优化参数。
"""

import talib.abstract as ta
from pandas import DataFrame
from technical import qtpylib

from freqtrade.strategy import IntParameter, IStrategy


class EmaRsiTrendStrategy(IStrategy):
    INTERFACE_VERSION = 3

    REQUIRED_INDICATOR_COLUMNS = ("ema_fast", "ema_slow", "rsi", "ema_trend")

    timeframe = "1h"
    can_short = False
    process_only_new_candles = True
    startup_candle_count = 220

    minimal_roi = {"0": 0.10, "240": 0.05, "720": 0.02, "1440": 0}
    stoploss = -0.08
    trailing_stop = False

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
        dataframe["ema_trend"] = ta.EMA(dataframe, timeperiod=200)
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            qtpylib.crossed_above(dataframe["ema_fast"], dataframe["ema_slow"])
            & (dataframe["close"] > dataframe["ema_trend"])
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

- [ ] Step 4: `risk_policy.AUDITED_STRATEGIES` 加入 `"EmaRsiTrendStrategy"`

- [ ] Step 5: 全量测试 + `make audit` 通过；commit

```bash
git add tests/ user_data/strategies/EmaRsiTrendStrategy.py quantlab/risk_policy.py
git commit -m "feat: 体制闸门策略 EmaRsiTrendStrategy（熊市关敞口，闸门不可优化）"
```

### Task 3: 双策略 walk-forward

- [ ] Step 1: `python -m quantlab.walk_forward --strategy EmaRsiTrendStrategy --epochs 30 --report-to docs/results/04-wf-trend.md`
- [ ] Step 2: `python -m quantlab.walk_forward --strategy RsiMeanRevertStrategy --epochs 30 --report-to docs/results/04-wf-meanrevert.md`

### Task 4: 三管线对比报告与部署决策

**Files:**
- Create: `docs/results/04-regime-filter-comparison.md`（合并 04-wf-*.md 的数据 + 03 号基线，删除两个中间文件）
- Modify（视决策）: `scripts/bot_run.sh` 的 `--strategy`

- [ ] Step 1: 汇总三管线对比表（OOS 拼接、正窗口占比、熊市窗口平均亏损、合规率），按预设标准做出切换/维持决策并记录理由
- [ ] Step 2: 如切换：改 `bot_run.sh` → `make bot-stop && make bot-start` → `make health` 验证；如维持：记录理由
- [ ] Step 3: Commit

### Task 5: README 与全量验收

- [ ] Step 1: README"项目定位"补充研究迭代结论一行；目录结构说明 04 号报告
- [ ] Step 2: `make check` 全绿 + `make bot-status` 正常 + git 干净
- [ ] Step 3: Commit

---

## Self-Review 记录

- 决策标准前置（Task 4 之前写死在 Global Constraints/Task 1），防止看到数据后事后合理化。
- 体制闸门 EMA200 固定不进 hyperopt——控制过拟合自由度，与 03 号报告"优化器卖风险"教训一致。
- 新策略同时进入测试矩阵、审计清单、WF 管线，三处一致。
