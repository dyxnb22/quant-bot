# 阶段 1.5 设计文档：生产化加固（个人使用）

日期：2026-08-12
状态：已批准（用户全权委托推进）
前置：阶段一已完成（Freqtrade 闭环 + dry-run 常驻）

## 1. 目标

把阶段一的"跑得通"升级为"生产可用（个人）"。生产级的判定不是功能多，而是四个特质：

1. **验证自动化**：策略上线依据从"单次手动回测"升级为"自动化 walk-forward 多窗口验证"。
2. **风险政策代码化**：风险边界写成可执行的审计程序，任何配置/参数（包括 hyperopt 产物）越界即拒绝——bot 启动前强制审计。
3. **数据质量保障**：坏数据能被主动发现（缺口、异常值、过期），而不是默默产出错误回测结论。
4. **自动巡检与告警**：无人值守时故障能被发现（launchd 定时巡检 + macOS 本地通知），不依赖外部服务（无需 Telegram token）。

## 2. 新增架构：quantlab 包

自研逻辑收敛为可测试的 Python 包 `quantlab/`（与 Freqtrade 解耦，只通过 CLI 和文件产物交互）：

```
quantlab/
├── __init__.py
├── strategy_loader.py   # 策略类加载 + 生效参数合并（类属性 ⊕ <Strategy>.json）
├── windows.py           # walk-forward 窗口切分（纯函数）
├── risk_policy.py       # 风险政策定义 + 审计（python -m quantlab.risk_policy）
├── data_quality.py      # K 线质量检查（python -m quantlab.data_quality）
├── backtest_io.py       # 解析 freqtrade 回测导出 zip
├── walk_forward.py      # WF 编排器（python -m quantlab.walk_forward）
└── health.py            # 健康巡检（python -m quantlab.health）
```

原则：编排器通过 subprocess 调用 `.venv/bin/freqtrade`，核心逻辑（切窗、审计、解析、判定）全部为纯函数并有单元测试。

## 3. 各模块设计

### 3.1 windows.py —— 窗口切分

`build_windows(start, end, is_months, oos_months, step_months) -> list[Window]`
Window = (is_start, is_end, oos_start, oos_end)，oos 紧接 is，按 step 滚动，最后一个窗口的 oos_end ≤ end。默认：IS 12 个月 / OOS 3 个月 / 步长 3 个月。

### 3.2 risk_policy.py —— 风险政策

政策（对生效值检查，生效值 = 类属性被 `<Strategy>.json` 覆盖后的结果）：

| 规则 | 边界 |
|---|---|
| stoploss | -0.20 ≤ s ≤ -0.005（必须存在） |
| minimal_roi | 必须存在且含 "0" 档 |
| protections | 必含 MaxDrawdown 与 StoplossGuard |
| timeframe | ∈ {5m, 15m, 1h, 4h, 1d} |
| config.dry_run | 必须为 true（仓库内永远如此） |
| config.max_open_trades | ≤ 5 |
| config.stake_amount | ≤ dry_run_wallet 的 10% |

审计对象：`config/config.json` + 所有策略的生效参数。违规 → 明细输出 + 退出码 1。
**强制点：`scripts/bot_start.sh` 启动前审计，不过不起。** walk-forward 报告对每个窗口的优化参数标注合规性。

已知现存违规：阶段一 hyperopt 把 `EmaRsiStrategy.json` 的 stoploss 写成 -0.234（越界）。本阶段修复：将其收敛回类默认 -0.08，作为"审计抓住真实事故"的案例记录。

### 3.3 data_quality.py —— 数据质量

对 `user_data/data/okx/*.feather` 检查：时间戳连续性（按 timeframe 间隔的缺口数）、重复时间戳、OHLC 一致性（high ≥ max(open,close,low) 等）、零成交量占比、新鲜度（最后一根 K 线距今 ≤ 阈值，默认 48h，可 `--max-age-hours` 覆盖）。任一 FAIL → 退出码 1。

### 3.4 walk_forward.py —— 验证编排器

流程（每窗口）：
1. 复制策略 .py 到运行专属临时目录（`--strategy-path` 隔离，**绝不污染生产参数文件**——研究活动不得改变运行中 bot 的行为）。
2. 样本内 hyperopt（SharpeHyperOptLoss，spaces buy/roi/stoploss，默认 30 epochs）→ 参数写入临时目录。
3. 参数存档 + 风险政策合规检查。
4. 用优化参数分别回测 IS 与 OOS（`--export trades --export-filename` 定名导出）。
5. 解析导出 zip（backtest_io），提取 profit_total / max_drawdown / sharpe / trades。

汇总输出：`user_data/walk_forward/<run_id>/report.md` + 覆盖式写 `docs/results/03-walk-forward.md`（git 管理最新结论）。汇总指标：每窗口 IS/OOS 对比、OOS 拼接收益（各段 (1+r) 连乘）、OOS 为正的窗口占比、IS→OOS 平均衰减、参数合规率。

### 3.5 health.py —— 健康巡检

检查项：launchd 服务已加载、freqtrade 进程存活、API /ping 可达且 state=running、日志 10 分钟内有写入（心跳 60s）、日志尾部无新增 ERROR、数据新鲜度（软告警）。
失败 → macOS 本地通知（osascript display notification）+ 退出码 1。
部署：launchd 定时任务 `com.quantbot.healthcheck`（StartInterval 900s），巡检日志落 `user_data/logs/health.log`。

## 4. 运维入口变化

- `make audit` / `make data-check` / `make wf` / `make health`
- `make check` = pytest + audit + data-check（一键体检，改动后必跑）
- `make bot-start` 内部先 audit
- 巡检定时任务随 `make health-install` 安装

## 5. 非目标（YAGNI）

- 不做 tick/订单簿数据、不做多交易所
- 不做因子库/ML（FreqAI）
- 不做 Telegram/邮件告警（本地通知已闭环；外部渠道需 token，按用户指示跳过）
- 不做组合优化器（相关性/VaR 留待阶段二）

## 6. 成功标准

1. `make check` 一条命令全绿（测试 + 风险审计 + 数据质量）。
2. walk-forward 一条命令产出多窗口 IS/OOS 报告，含拼接 OOS 表现与参数合规标注。
3. 现存越界参数（stoploss -0.234）被审计发现并修复，bot 重启后运行在政策边界内。
4. 杀掉 bot 或数据过期等故障场景，15 分钟内收到 macOS 本地通知。
5. 全程 dry-run，零真实密钥。
