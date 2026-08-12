# quant-bot

个人加密货币量化交易工作台。**学习与研究优先，仓库内恒为 dry-run（模拟盘），不涉及真实资金。**

基于 [Freqtrade](https://www.freqtrade.io/) 2026.x / Python 3.14 / OKX 现货公共行情，自研 `quantlab/` 工具层。

## 项目定位

一套完整的个人量化研究与运行闭环，具备四个生产级特质：

1. **验证自动化**：`make wf` 一条命令跑 walk-forward 多窗口验证（样本内优化 → 样本外检验 → 拼接汇总 + 合规标注），上线依据不再是手工回测。
2. **风险政策代码化**：止损边界、仓位上限、必备 protections 写成可执行审计（`quantlab/risk_policy.py`）；**bot 启动前强制审计，不过不起**。实证价值：hyperopt 曾把止损优化到 -23.4%，walk-forward 十个窗口中七个试图越界——优化器没有风险观，审计是常设机制。
3. **数据质量保障**：`make data-check` 检查缺口/重复/OHLC 矛盾/新鲜度，坏数据主动暴露而不是默默产出错误结论。
4. **自动巡检告警**：launchd 每 15 分钟巡检服务/进程/API/日志心跳，异常直接弹 macOS 通知，无需任何外部服务。
5. **LLM 复盘与值班助手**：`make review` 把回测交易聚合后交给 DeepSeek 做归因分析、产出可检验假设（`docs/results/05`，其三条假设已全部经 walk-forward 检验并证伪，见 `06`）；`make brief` 生成每日值班日报（状态+行情→风险观察，launchd 每天 09:00 自动跑，只读不进交易回路）。**方法论边界**：LLM 只做复盘归因与状态观察，不做"LLM 对历史 K 线的决策回测"——主流模型训练语料覆盖历史行情，那种回测是开卷考试（数据污染），成绩不可外推；LLM-in-loop 唯一干净的检验方式是接入 dry-run 做前向测试。

预期管理：当前基线策略经 10 窗口 walk-forward 验证**无泛化能力**（OOS 拼接 -1.19%，详见 `docs/results/03-walk-forward.md`），价值在承载方法论。回测好看 ≠ 实盘赚钱，本仓库用自己的数据证明了这一点。

研究迭代记录：体制闸门（EMA200/EMA100 两版）、均值回归、LLM 复盘提出的紧止损/时间熔断/币对差异化、以及首个 K 线外信息源——资金费率反转（Binance 永续费率 z-score 极端逆向，`07`）——**八个管线的 walk-forward 全部证伪**（`docs/results/04`、`06`、`07`）。部署决策均按预登记标准执行，三轮拒绝了"听起来合理"的改动；资金费率论点更是样本内就无利润可拟合（最强证伪）。资金费率数据管道（2023 至今、对齐无未来函数）作为持久资产保留，可低成本检验 carry/截面等不同论点。

## 快速开始

```bash
make setup            # 创建 .venv 并安装 freqtrade + pytest
cp .env.example .env  # 编辑 .env（本机 API 凭据随意生成）
make data             # 下载 OKX 1h 历史数据
make check            # 一键体检：测试 + 风险审计 + 数据质量
make bot-start        # 启动 dry-run 模拟盘（先审计，launchd 常驻）
make health-install   # 安装 15 分钟定时巡检
```

FreqUI 监控：浏览器打开 `http://127.0.0.1:8080`（账号密码见 `.env`）。

## 日常工作流

1. 改动任何策略/配置后：`make check`（全绿才继续）。
2. 策略研究：`make backtest` 快速对比 → `make review` 让 LLM 归因出假设 → `make wf` 出上线依据（只看 OOS 拼接数字）。
3. 数据维护：每周 `make data && make data-check`。
4. 运行观察：`make bot-status` / `make log`；巡检告警自动弹通知。
5. 停机：`make bot-stop`（连同 launchd 服务一起卸载）。

## 目录结构

```
config/config.json        # 主配置（dry-run，无任何密钥）
quantlab/                 # 自研工具层：窗口切分/风险政策/数据质量/WF 编排/巡检
user_data/strategies/     # 策略代码 + hyperopt 参数（.json 会覆盖类属性，已纳入审计）
user_data/walk_forward/   # 每次 WF 运行的参数存档与明细（不入库）
scripts/                  # bot 启停/状态、数据下载、巡检安装
tests/                    # 单元测试（策略无未来函数 + quantlab 各模块）
docs/results/             # 回测/过拟合/walk-forward 报告（必读）
```

## 风控设计

- **政策边界（代码强制）**：止损 ∈ [-20%, -0.5%]；max_open_trades ≤ 5；单笔 ≤ 钱包 10%；必含 MaxDrawdown + StoplossGuard protections；dry_run 恒 true。
- 配置层：最多 3 仓、单笔 500 USDT（模拟资金 10000）、限价进出。
- 运维层：launchd 托管崩溃自愈（已实测 8 秒拉起）、启动强制审计、定时巡检告警、本机 API 绕过系统代理。
- 密钥纪律：仓库零密钥，`.env` 不入库；dry-run 全程无需交易所密钥。

## 转实盘前置条件（本阶段不做）

1. 策略 walk-forward OOS 拼接为正且多数窗口为正（当前策略不满足）。
2. 模拟盘连续稳定运行 ≥ 4 周，成交行为与回测假设偏差可解释。
3. OKX API key 最小权限（禁提币）+ 独立子账户 + 硬性资金上限。
4. 自行评估所在地监管合规风险。

## 阶段二路线（远期）

事件驱动自研框架（参考 Nautilus/vn.py 架构）：行情网关、策略引擎、风控中间件、执行器四层解耦；市场体制过滤与做空能力（walk-forward 报告指出当前策略只有 beta 没有 alpha）；组合级风险（相关性敞口）。届时另立设计文档。

## 免责声明

加密货币波动极大，历史回测不代表未来收益。本仓库仅供学习研究，不构成投资建议；实盘交易风险自担。
