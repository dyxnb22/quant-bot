# M3b 实施计划：CN 动量月度调仓研究清单

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 11 号复检 PASS 的沪深 300 动量因子变成可日常使用的研究产品：每月生成 Q5 名单（含行业集中度与相关性风险指标）、自动跟踪历史清单的已实现表现。**不是交易系统**——A 股个人自动化受限，执行与否是人的决策，清单页脚带免责声明。

**Architecture:** `quantlab/cn_momentum_list.py`；纯函数（选取/集中度/跟踪计算）可测；产物提交至 `docs/research/cn-momentum/`（跟踪记录本身就是研究产品）；状态存 `state.json`。

## Tasks

### Task 1: cn_data --refresh
- `--refresh` 删除现有 close/volume feather 后全量重下（月度更新用；断点续传在中断场景仍有效）
- Makefile: `cn-data-refresh`

### Task 2: 行业分类
- `fetch_industry() -> DataFrame[code, code_name, industry]`（bs.query_stock_industry，申万一级）
- 缓存 `user_data/data/cn/industry.feather`，缺失时自动抓取

### Task 3: 清单生成器（TDD）
- `select_top_quintile(factor_row) -> Series`（降序动量值）
- `industry_weights(tickers, industry_map) -> Series`（权重降序，>30% 标记警示）
- `avg_pairwise_correlation(close_daily, tickers, window=60) -> float`
- `realized_performance(prev_tickers, close_monthly, universe_row) -> dict`（上期清单等权收益 vs 成分等权基准）
- main：数据新鲜度警告（>7 天提示 refresh）→ 生成当月 `YYYY-MM.md` → 更新 `tracking.md` 与 `state.json`
- Makefile: `momentum-list`

### Task 4: 首次真实运行 + 文档收口
- 生成 2026-08 清单并提交
- 路线图：M3b 完成；M4 港股给出评估结论（触发条件已满足故必须评估：CN 动量为本土截面信号，不构成购买港股付费数据的依据 → 维持缓议）；M2/C2/D3/D4 以触发条件收口
- README 工作流补充月度节奏；make check 全绿；push

## Self-Review
- 清单产物入库（跟踪记录 = 产品）与 user_data 惯例（运行产物不入库）的例外已说明理由
- 免责声明与"研究非建议"定位写入每页页脚
- 数据新鲜度检查防止用陈旧数据生成清单
