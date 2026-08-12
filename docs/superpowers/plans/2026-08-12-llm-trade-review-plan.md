# LLM 交易复盘接入实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 接入真实 LLM API（DeepSeek，key 已在环境中），以方法论干净的方式用于历史数据：LLM 复盘回测交易记录、归纳亏损模式、产出可被 `make wf` 检验的假设——而非让 LLM 对历史 K 线做决策（训练数据污染，结论不可外推）。

**Architecture:** `quantlab/llm.py`（stdlib 客户端，走系统代理）+ `quantlab/trade_review.py`（纯函数聚合统计 → prompt → 报告落盘）。聚合逻辑有单测；LLM 调用不进 pytest（外部依赖，CLI 手动验证）。

**Tech Stack:** DeepSeek chat API（OpenAI 兼容），零新增依赖。

## Global Constraints

- API key 只从环境变量 / `.env` 读取，绝不入库；报告注明模型与数据来源。
- 报告必须包含固定免责段：LLM 输出是分析假设，不是预测；任何假设上线前必须过 walk-forward。
- 控制 token：不喂原始 743 笔交易，喂聚合统计 + 最差/最好各 10 笔。

## Tasks

### Task 1: llm.py 客户端 + backtest_io 暴露 load_export_zip
- `chat(system, user, ...) -> str`；`load_export_zip(zip_path) -> dict` 供按路径读取导出。

### Task 2: trade_review.py（聚合纯函数 TDD + CLI）
- `aggregate_trades(trades) -> dict`：笔数/胜率/平均收益、按出场原因与币对分桶、赢家/输家平均持仓时长、最差最好各 10 笔。
- 单测：合成 trades 验证统计正确性。
- CLI：`--zip`（默认取 user_data/backtest_results 最新）`--strategy`；输出 `docs/results/05-llm-trade-review.md`。

### Task 3: 集成与验证
- `.env.example` 加 `DEEPSEEK_API_KEY=` 槽位；Makefile 加 `review` 目标。
- 真实运行一次（EmaRsi 743 笔基线回测），人工检查报告质量。
- README 增补 LLM 用法与方法论警告；`make check` 全绿；commit + push。
