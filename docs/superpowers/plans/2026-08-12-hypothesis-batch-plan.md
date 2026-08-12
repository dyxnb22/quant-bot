# 假设检验批次 + LLM 值班日报实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 05 号 LLM 复盘的三条假设 + 04 号报告的"更快体制"假设实现为四个策略变体，逐个过 walk-forward；落地 LLM 值班日报（每日定时，不进交易回路）。

**Architecture:** 变体以继承 `EmaRsiStrategy` 实现（freqtrade 支持同目录策略继承）；loader 与 WF 编排器补继承支持；审计改为自动发现全部策略。日报复用 `quantlab/llm.py` + bot REST API（本机绕代理）+ K 线数据。

**Tech Stack:** 不变，零新依赖。

## Global Constraints

- **预登记部署标准（防事后合理化）**：变体替换运行中策略，当且仅当 OOS 拼接收益 > 基线 -1.19% **且** OOS 正窗口 ≥ 5/10。全部不满足则维持基线，报告如实记录。
- 四变体全部纳入测试矩阵与审计（审计自动发现 `user_data/strategies/*.py`）。
- 04 号报告的"反转早期豁免"假设**跳过**：金叉与死叉必然交替，"死叉后首次金叉豁免"逻辑上等价于移除闸门，假设不完备，记录于 06 号报告。
- 日报只读（bot API + 数据文件），不写任何交易指令。

---

### Task 1: 基础设施

**Files:**
- Modify: `quantlab/strategy_loader.py`（load 时把策略目录临时加入 sys.path，支持 `from EmaRsiStrategy import ...`；新增 `discover_strategies()`）
- Modify: `quantlab/walk_forward.py`（临时目录复制全部 `*.py` 而非单文件）
- Modify: `quantlab/risk_policy.py`（`AUDITED_STRATEGIES` 改为 `discover_strategies()` 动态获取）
- Modify: `tests/test_strategies.py`（`STRATEGIES = discover_strategies()`；entry-sum>0 断言改为按 `GATED_STRATEGIES` 集合跳过体制类变体）

**Interfaces:**
- Produces: `discover_strategies(strategy_dir=None) -> list[str]`（按文件名排序）

核心改动（strategy_loader）：

```python
def discover_strategies(strategy_dir=None) -> list[str]:
    d = Path(strategy_dir) if strategy_dir else DEFAULT_STRATEGY_DIR
    return sorted(p.stem for p in d.glob("*.py"))


def load_strategy_class(name: str, strategy_dir=None):
    d = Path(strategy_dir) if strategy_dir else DEFAULT_STRATEGY_DIR
    d_str = str(d)
    sys.path.insert(0, d_str)
    try:
        spec = importlib.util.spec_from_file_location(name, d / f"{name}.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return getattr(module, name)
    finally:
        sys.path.remove(d_str)
```

walk_forward 复制改为：

```python
for src in DEFAULT_STRATEGY_DIR.glob("*.py"):
    shutil.copy(src, strategy_dir)
```

- [ ] 全量测试通过；commit

### Task 2: 四个假设变体（TDD）

**Files:**
- Create: `user_data/strategies/EmaRsiH1TightStop.py`、`EmaRsiH2TimeExit.py`、`EmaRsiH3PairSpecific.py`、`EmaRsiH4FastRegime.py`
- Modify: `tests/test_strategies.py`（专项测试）

**变体定义（均继承 EmaRsiStrategy，单点改动）：**

| 变体 | 假设来源 | 改动 |
|---|---|---|
| H1TightStop | LLM 假设 1 | `stoploss = -0.04` |
| H2TimeExit | LLM 假设 2 | `custom_exit`：持仓 ≥720 分钟且浮盈 <3% → 平仓；roi 240 档 0.05→0.04 |
| H3PairSpecific | LLM 假设 3 | ETH/SOL：出场用更快 EMA12/35 交叉 + `custom_exit` 浮盈 ≥3.5% 止盈 |
| H4FastRegime | 04 号方向 1 | 入场加体制闸门 close > EMA100（≈4.2 天，比 EMA200 快一倍） |

H2 核心代码：

```python
class EmaRsiH2TimeExit(EmaRsiStrategy):
    minimal_roi = {"0": 0.10, "240": 0.04, "720": 0.02, "1440": 0}

    def custom_exit(self, pair, trade, current_time, current_rate, current_profit, **kwargs):
        held_minutes = (current_time - trade.open_date_utc).total_seconds() / 60
        if held_minutes >= 720 and current_profit < 0.03:
            return "time_cutoff"
        return None
```

H3 核心代码：

```python
class EmaRsiH3PairSpecific(EmaRsiStrategy):
    FAST_EXIT_PAIRS = {"ETH/USDT", "SOL/USDT"}
    REQUIRED_INDICATOR_COLUMNS = ("ema_fast", "ema_slow", "rsi", "ema_fast2", "ema_slow2")

    def populate_indicators(self, dataframe, metadata):
        dataframe = super().populate_indicators(dataframe, metadata)
        dataframe["ema_fast2"] = ta.EMA(dataframe, timeperiod=12)
        dataframe["ema_slow2"] = ta.EMA(dataframe, timeperiod=35)
        return dataframe

    def populate_exit_trend(self, dataframe, metadata):
        fast, slow = (("ema_fast2", "ema_slow2")
                      if metadata["pair"] in self.FAST_EXIT_PAIRS
                      else ("ema_fast", "ema_slow"))
        dataframe.loc[qtpylib.crossed_below(dataframe[fast], dataframe[slow]),
                      "exit_long"] = 1
        return dataframe

    def custom_exit(self, pair, trade, current_time, current_rate, current_profit, **kwargs):
        if pair in self.FAST_EXIT_PAIRS and current_profit >= 0.035:
            return "pair_roi"
        return None
```

H4 核心代码：

```python
class EmaRsiH4FastRegime(EmaRsiStrategy):
    REQUIRED_INDICATOR_COLUMNS = ("ema_fast", "ema_slow", "rsi", "ema_regime")
    startup_candle_count = 120

    def populate_indicators(self, dataframe, metadata):
        dataframe = super().populate_indicators(dataframe, metadata)
        dataframe["ema_regime"] = ta.EMA(dataframe, timeperiod=100)
        return dataframe

    def populate_entry_trend(self, dataframe, metadata):
        dataframe = super().populate_entry_trend(dataframe, metadata)
        dataframe.loc[dataframe["close"] <= dataframe["ema_regime"], "enter_long"] = 0
        return dataframe
```

**专项测试（新增到 test_strategies.py）：**

```python
def test_h1_tight_stoploss():
    cls = load_strategy_class("EmaRsiH1TightStop")
    assert cls.stoploss == -0.04


def test_h2_time_cutoff():
    from datetime import datetime, timedelta, timezone
    from types import SimpleNamespace
    cls = load_strategy_class("EmaRsiH2TimeExit")
    s = cls(config={"stake_currency": "USDT", "runmode": "backtest"})
    now = datetime(2026, 1, 2, tzinfo=timezone.utc)
    old = SimpleNamespace(open_date_utc=now - timedelta(minutes=800))
    fresh = SimpleNamespace(open_date_utc=now - timedelta(minutes=100))
    assert s.custom_exit("BTC/USDT", old, now, 100.0, 0.01) == "time_cutoff"
    assert s.custom_exit("BTC/USDT", old, now, 100.0, 0.05) is None
    assert s.custom_exit("BTC/USDT", fresh, now, 100.0, 0.01) is None


def test_h3_pair_specific_exit(ohlcv_df):
    cls = load_strategy_class("EmaRsiH3PairSpecific")
    s = cls(config={"stake_currency": "USDT", "runmode": "backtest"})
    assert s.custom_exit("ETH/USDT", None, None, 100.0, 0.04) == "pair_roi"
    assert s.custom_exit("BTC/USDT", None, None, 100.0, 0.04) is None
    df = s.populate_indicators(ohlcv_df.copy(), {"pair": "ETH/USDT"})
    assert "ema_fast2" in df.columns


def test_h4_regime_gate(ohlcv_df):
    cls = load_strategy_class("EmaRsiH4FastRegime")
    s = cls(config={"stake_currency": "USDT", "runmode": "backtest"})
    meta = {"pair": "BTC/USDT"}
    df = s.populate_indicators(ohlcv_df.copy(), meta)
    df = s.populate_entry_trend(df, meta)
    entries = df[df["enter_long"] == 1]
    assert (entries["close"] > entries["ema_regime"]).all()
```

- [ ] 先写测试确认失败 → 实现四变体 → 全量测试 + `make audit` 通过 → commit

### Task 3: 四变体 walk-forward

- [ ] 逐个运行（报告写 `docs/results/06-wf-h{1..4}.md`，run 档自动存 user_data）

### Task 4: 06 号报告与部署决策

- [ ] 五管线对比表（基线 + 四变体）+ 按预登记标准决策 + 删除中间报告文件；如切换策略：改 `bot_run.sh` 并重启验证；commit

### Task 5: LLM 值班日报

**Files:**
- Create: `quantlab/daily_brief.py`、`scripts/brief_install.sh`、`scripts/brief_uninstall.sh`
- Modify: `Makefile`（brief / brief-install / brief-uninstall）

设计：
- 输入：bot API（/profit、/status、/trades 最近 20 笔，本机绕代理）+ 各币对最近 24 根 1h K 线涨跌摘要 + health 检查结果。
- Prompt：值班风控助手；输出固定三段——状态摘要 / 风险观察 / 今日关注点；禁止交易建议与预测。
- 输出：`user_data/logs/daily_brief/YYYY-MM-DD.md`（运行产物不入库）。
- launchd `com.quantbot.dailybrief`：每日 09:00（StartCalendarInterval）。

- [ ] 实现 + 真实跑一次检查质量 → 安装定时 → commit

### Task 6: 收尾

- [ ] README 更新（研究批次结论一行 + make brief 用法）；`make check` 全绿；commit + push

---

## Self-Review 记录

- 部署标准预登记于 Global Constraints；四变体单点改动便于归因；反转豁免假设的不完备性如实记录而非硬编。
- H2/H3 的 custom_exit 在回测中由 freqtrade 逐 K 线评估，无未来函数风险；H4 闸门复用已验证的实现模式。
- 日报为只读消费者，与交易回路物理隔离（不同进程、不同 launchd 任务）。
