# 阶段 A 实施计划：截面研究底座（统计工具箱 + 截面引擎 + 美股数据）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 落地多市场路线图的阶段 A：市场无关的统计检验工具箱、日频截面回测引擎、美股数据管道，并用真实数据完成动量因子的端到端冒烟。

**Architecture:** 三个独立 quantlab 模块，纯函数优先、TDD；数据落地 feather；冒烟结果只作"管道可用"证明，因子正式检验属阶段 B（预登记标准见路线图 A5）。

**Tech Stack:** 新增依赖 `yfinance`（美股日频，免费）；其余零新增。

## Global Constraints

- 统计模块必须先于因子结论存在（防"先看结果再选检验"）。
- 股池用 S&P 500 当前成分（Wikipedia）作 MVP，**幸存者偏差如实标注**；点时化列入 D5。
- 下载分块 + 重试 + 落地缓存；数据质量检查复用既有模式（缺口/新鲜度按交易日历放宽）。
- 冒烟不做参数搜索（无过拟合面），不宣称因子有效性。

## Tasks

### Task 1: quantlab/stats_tests.py（TDD）

**Interfaces:**
- `deflated_sharpe(sharpe, n_obs, n_trials, skew=0.0, kurt=3.0) -> float`（DSR 概率，Bailey & López de Prado）
- `permutation_pvalue(series, n_permutations=1000, seed=0) -> float`（均值>0 的置换检验，符号翻转法）
- `benjamini_hochberg(pvalues, alpha=0.05) -> list[bool]`（FDR 校正后的显著性判定）

测试要点：DSR 对 trials 单调递减、完美序列 p≈0、随机序列 p 均匀、BH 边界案例（全显著/全不显著/教科书例子）。

### Task 2: quantlab/cross_section.py（TDD）

**Interfaces:**
- `rank_ic(factor: DataFrame, forward_returns: DataFrame) -> Series`（逐期 Spearman rank IC；factor/returns 均为 date × ticker 宽表）
- `quantile_portfolios(factor, forward_returns, quantiles=5) -> DataFrame`（各分层逐期等权收益）
- `long_short(quantile_returns, cost_bps=10, turnover: Series | None = None) -> DataFrame`（Q5-Q1 多空，扣双边成本）
- `turnover(factor, quantiles=5) -> Series`（顶层组合逐期换手率）

测试要点：构造"因子=未来收益"的完美数据 → IC=1、分层严格单调、多空=Q 顶-Q 底；随机因子 → IC≈0；换手率边界（不变持仓=0，全换=1）；成本扣减方向正确。

### Task 3: quantlab/us_data.py

**Interfaces:**
- `fetch_sp500_tickers() -> list[str]`（Wikipedia 当前成分，带 UA，重试）
- `download_us_daily(tickers, years=4) -> Path`（yfinance 分块批量，复权价，宽表 close/volume 落地 `user_data/data/us/`）
- `load_us_daily() -> dict[str, DataFrame]`（close/volume 宽表）
- CLI `python -m quantlab.us_data` + Makefile `us-data` 目标

### Task 4: 真实数据端到端冒烟

- 下载 S&P 500 近 4 年日频 → 12-1 动量因子（月度再平衡）→ rank IC / 分层 / 多空（10bps/边）→ stats_tests 三件套输出
- 结果写 `docs/results/08-us-pipeline-smoke.md`（明确标注：管道验证，非因子结论；幸存者偏差声明）

### Task 5: 收尾

- requirements.lock 更新、README 快速开始加 `make us-data`、`make check` 全绿、commit + push、勾选路线图 S1/A1/A2

## Self-Review 记录

- 统计模块先行的顺序约束写入 Global Constraints；冒烟与正式检验的边界（无预登记不下结论）明确。
- 幸存者偏差不可在 MVP 内根除，选择"如实标注 + 路线图 D5 跟进"而非隐瞒。
- 新依赖仅 yfinance 一个，失败备选 Stooq 已记录。
