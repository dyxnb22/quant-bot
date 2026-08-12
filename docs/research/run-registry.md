# 运行台账：脚本与产物地图 + 运行记录

回答两个问题：**每个脚本什么时候启动？记录的数据存放在哪？**
上半部分是静态地图（新增脚本时手工维护）；下半部分由 `make daily` 自动追加运行记录。

## 脚本与产物地图

### 常驻 / 定时（launchd 自动启动，无须手动）

| 任务 | 启动时机 | 做什么 | 数据/日志存放 |
|---|---|---|---|
| `com.quantbot.dryrun` | 开机常驻，崩溃自启 | freqtrade dry-run 模拟盘（实时行情虚拟交易） | 交易库 `user_data/tradesv3.dryrun.sqlite`；日志 `user_data/logs/freqtrade.log`（launchd 输出 `launchd.out.log` / `launchd.err.log`） |
| `com.quantbot.health` | 每 15 分钟 | 服务/进程/API/日志心跳巡检，连续 ≥2 次失败弹 macOS 通知 | `user_data/logs/health.log`（失败计数 `health_fail_streak`） |
| `com.quantbot.brief` | 每天 09:00 | LLM 值班日报（状态+持仓+24h 行情 → 风险观察） | `user_data/logs/daily_brief/YYYY-MM-DD.md`（launchd 输出 `daily_brief/launchd.log`） |
| `com.quantbot.cndownload` | 深夜 02:30（按需安装，成功后自卸载） | A 股行情断点续传下载 | 数据 `user_data/data/cn|cn500/`；日志 `user_data/logs/cn_download.log` |
| `com.quantbot.cnfundamentals` | 深夜 02:30（按需安装，成功后自卸载） | A 股季频财报下载（点时 ROE，hs300→zz500） | 数据 `user_data/data/cn|cn500/fundamentals.feather`；日志 `user_data/logs/cn_fundamentals.log` |

### 手动（你启动的）

| 命令 | 建议节奏 | 做什么 | 结果存放 |
|---|---|---|---|
| `make daily` | **每天一次（唯一必做）** | 币市数据增量更新 → 模拟盘健康+账面 → 数据质量 → G5 进度；追加日志与本台账 | 日检日志 `docs/research/daily-log.md`；本文件「运行记录」 |
| `make recon` | 每周（平仓样本增长后） | dry-run 成交 vs 回测假设对账 | `docs/results/06-trade-recon.md` |
| 晨间 Runbook（见 OPERATIONS §2） | 每月第一个交易日 | A 股数据校验 → 三候选清单入账本 → 月报 | 账本 `docs/research/cn-momentum/forward-ledger.jsonl`（append-only，G5 唯一证据源）；清单 `docs/research/cn-momentum/YYYY-MM.md` |
| `make gates` | 每季度 | 三候选 Deployment Gate G1-G5 复查 | `docs/results/14-deployment-gate*.md` |
| `make check` | 改代码后 | ruff + 全量测试 + 风险审计 + 数据质量 | 终端输出（CI 同款） |

### 数据目录速查

| 目录 | 内容 | 更新方式 |
|---|---|---|
| `user_data/data/okx/` | 币市 1h/4h K 线（5 交易对） | `make daily`（增量）或 `make data` |
| `user_data/data/cn/`、`cn500/` | A 股六字段日频面板 + 点时成分 + 指数 | 月度 `make cn-data-refresh` / `cn500-data-refresh`（或深夜任务） |
| `user_data/data/us/` | 美股日频收盘面板 + PIT 成分表 + EDGAR 基本面 | 按需 `make us-data` / `make us-fundamentals` |
| `user_data/data/funding/` | 资金费率历史 | 按需 `make funding` |
| `docs/results/` | 编号研究报告（含溯源戳） | 各研究脚本写入，入 git |
| `docs/research/` | 前向账本、月度清单、日检日志、本台账 | 入 git（账本 append-only） |

## 运行记录（make daily 自动追加）

| 启动时间 | 命令 | 结果 | 详情位置 |
|---|---|---|---|
| 2026-08-12 22:32 | make daily | 5/5 通过 | `docs/research/daily-log.md` § 2026-08-12 22:32 |
