# 资金费率信号族实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 接入第一个 K 线之外的信息源——永续合约资金费率（杠杆多空情绪的直接读数），构建反转信号策略，走完整 walk-forward 检验。这是对 06 号报告"换信息源"结论的执行。

**Architecture:** 数据源 Binance Vision 月度归档（2023-01 起完整；OKX 费率 API 仅保留 3 个月，实测排除）+ OKX 费率 API 补最近尾部；`quantlab/funding.py` 负责拉取与对齐（merge_asof backward，结构性无未来函数）；策略经由类属性 `funding_dir` 读取 feather，测试可注入合成数据。

**Tech Stack:** 零新依赖（urllib + zipfile + pandas）。

## Global Constraints

- **信号论点（预登记）**：资金费率极端负值 = 空头拥挤 = 逆向做多机会；费率回正 = 情绪修复 = 离场。阈值可优化（bps），论点本身不可优化。
- **预登记部署标准**：与 06 号相同——OOS 拼接 > 基线 -1.19% 且正窗口 ≥ 5/10 才切换运行策略。
- 跨所口径如实记录：信号来自 Binance 永续，执行于 OKX 现货（同一标的的情绪代理，不同交易所）。
- 对齐必须 backward merge（K 线时刻只能看到已结算的费率），专项测试锁死。

## Tasks

### Task 1: quantlab/funding.py（TDD）

**Interfaces:**
- `attach_funding(candles, funding) -> DataFrame`：为 1h K 线附加 `funding_rate` 列（最近一次已结算费率，backward）
- `download_funding(pair) -> Path`：Binance 月度归档（2023-01 → 最新完整月）+ OKX 尾部补齐 → `user_data/data/funding/{BASE}_{QUOTE}-funding.feather`
- CLI：`python -m quantlab.funding`（4 对全量下载 + 覆盖摘要）；Makefile `funding` 目标

**测试（先写，锁对齐语义）：**

```python
def test_attach_funding_no_lookahead():
    candles = pd.DataFrame({"date": pd.date_range("2024-01-01", periods=24, freq="1h", tz="UTC")})
    funding = pd.DataFrame({
        "date": pd.to_datetime(["2024-01-01 00:00", "2024-01-01 08:00", "2024-01-01 16:00"], utc=True),
        "funding_rate": [0.0001, -0.0002, 0.0003],
    })
    out = attach_funding(candles, funding)
    assert out.loc[out["date"] == pd.Timestamp("2024-01-01 09:00", tz="UTC"), "funding_rate"].iloc[0] == -0.0002
    assert out.loc[out["date"] == pd.Timestamp("2024-01-01 15:00", tz="UTC"), "funding_rate"].iloc[0] == -0.0002
    assert out.loc[out["date"] == pd.Timestamp("2024-01-01 16:00", tz="UTC"), "funding_rate"].iloc[0] == 0.0003
```

Binance 归档格式：`data/futures/um/monthly/fundingRate/{SYM}/{SYM}-fundingRate-YYYY-MM.zip`，CSV 列 `calc_time,funding_interval_hours,last_funding_rate`（ms 时间戳）。OKX 尾部：`/api/v5/public/funding-rate-history`（需浏览器 UA，仅近 3 月）。合并去重按时间戳，来源标注列 `source`。

### Task 2: FundingRevertStrategy（TDD）

- 入场：`funding_rate <= buy_funding_bps/10000`（IntParameter(-30, -2, default=-10)，即 -0.30% ~ -0.02% 每 8h）
- 出场：`funding_rate >= 0`（情绪回正）+ roi/止损（-0.08，roi 同均值回归梯度）
- protections 三件套；`REQUIRED_INDICATOR_COLUMNS = ("funding_rate",)`
- 无资金费率文件时 funding_rate 为 NaN → 永不入场（安全降级）
- 专项测试：tmp funding_dir 注入合成费率，验证入场/出场触发与阈值边界；加入 GATED（通用夹具无费率文件）

### Task 3: 真实下载 + walk-forward

- `make funding` 下载 4 对（约 44 个月 × 4 ≈ 176 个 zip，几分钟）
- 覆盖检查后：`python -m quantlab.walk_forward --strategy FundingRevertStrategy --epochs 30 --report-to docs/results/07-wf-funding.md`

### Task 4: 07 号报告 + 决策 + README

- 对比基线，按预登记标准决策；README 记录新信息源与结论

### Task 5: 验收推送

- `make check` 全绿（新增测试计入）+ push

## Self-Review 记录

- OKX 3 个月保留期的排除依据已实测（探针输出在会话记录中）；Binance Vision 2024-01 样本已验证可下载解析。
- 对齐语义由专项测试锁死；策略降级路径（无数据→不交易）避免静默错误。
- 跨所信号口径、月度归档缺失月份（404 跳过）均如实记录于报告。
