# quant-bot

个人**多市场量化研究平台**：quantlab 方法论层（验证/风控/统计/LLM 辅助）市场无关，币市（Freqtrade + OKX 现货 dry-run）是第一个执行器，美股/A 股截面研究进行中。**研究优先，仓库内恒为 dry-run（模拟盘），不涉及真实资金。**

基于 Python 3.14 / [Freqtrade](https://www.freqtrade.io/) 2026.x / 自研 `quantlab/` 工具层。总路线图见 `docs/superpowers/specs/2026-08-12-multimarket-roadmap.md`。**日常操作以 [`OPERATIONS.md`](OPERATIONS.md) 为唯一入口**（周/月/季节奏、研究纪律、故障速查、开发触发表）。

## 项目定位

一套完整的个人量化研究与运行闭环，五个核心特质：

1. **验证自动化**：`make wf` 一条命令跑 walk-forward 多窗口验证（样本内优化 → 样本外检验 → 拼接汇总 + 合规标注），上线依据不再是手工回测。
2. **风险政策代码化**：止损边界、仓位上限、必备 protections 写成可执行审计（`quantlab/risk_policy.py`）；**bot 启动前强制审计，不过不起**。实证价值：hyperopt 曾把止损优化到 -23.4%，walk-forward 十个窗口中七个试图越界——优化器没有风险观，审计是常设机制。
3. **数据质量保障**：`make data-check` 检查缺口/重复/OHLC 矛盾/新鲜度，坏数据主动暴露而不是默默产出错误结论。
4. **自动巡检告警**：launchd 每 15 分钟巡检服务/进程/API/日志心跳，异常直接弹 macOS 通知，无需任何外部服务。
5. **LLM 复盘与值班助手**：`make review` 把回测交易聚合后交给 DeepSeek 做归因分析、产出可检验假设（`docs/results/05`，其三条假设已全部经 walk-forward 检验并证伪，见 `06`）；`make brief` 生成每日值班日报（状态+行情→风险观察，launchd 每天 09:00 自动跑，只读不进交易回路）。**方法论边界**：LLM 只做复盘归因与状态观察，不做"LLM 对历史 K 线的决策回测"——主流模型训练语料覆盖历史行情，那种回测是开卷考试（数据污染），成绩不可外推；LLM-in-loop 唯一干净的检验方式是接入 dry-run 做前向测试。

预期管理：当前基线策略经 10 窗口 walk-forward 验证**无泛化能力**（OOS 拼接 -1.19%，详见 `docs/results/03-walk-forward.md`），价值在承载方法论。回测好看 ≠ 实盘赚钱，本仓库用自己的数据证明了这一点。

研究迭代记录（计数口径：22 个市场-假设对象 / 24 次检验运行 / 通过 5 个）——**跨市场空间 OOS（16-18 号）**：A 股信号族在中证 500 独立宇宙复制成功（复合 NW t 4.80、DSR 0.92，全面强于沪深 300 版本）；美股大盘动量 15 年复检决定性死亡（IC≈0）；加密截面动量显著但分层倒 U 如实拒绝——信号族确认为 **A 股市场结构特异**。此前记录：币市 8 个时序管线 walk-forward 全部证伪（`03-07`）；美股四因子初检全拒（`09`）；A 股四因子初检 3 拒 1 存疑（`10`）；存疑的沪深 300 动量经预登记复检（10 年 × 622 标的点时成分）**PASS**——IC +0.053（p=0.012 过校正）、五层完美单调、多空净 +1.36%/月、输家层为负（`11`）。诚实的弱点同样在案：净夏普 0.19、DSR 0.77，经济强度中等；A 股做空受限，落地形态为月度调仓研究清单而非自动交易。所有检验按预登记协议执行（`factor-registry.md`），先提交标准后跑数。**当前状态（迭代 v3 后）**：该组合参数已冻结、部署门槛 G5 的前向时钟从 2026-08-12 起算——研究 PASS 距离部署 PASS，还差 12 个月度周期的真实前向证据。

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

股市截面研究（美股 + A 股）：

```bash
make us-data     # 下载 S&P 500 日频数据（yfinance，免费）
make cn-data     # 下载沪深 300 日频数据（baostock，免费）
make factors-us  # 美股四因子初检（预登记协议 + 多重检验校正）
make factors-cn  # A股四因子初检（同一流水线）
```

## 日常工作流

1. 改动任何策略/配置后：`make check`（全绿才继续）。
2. 币市研究：`make backtest` 快速对比 → `make review` 让 LLM 归因出假设 → `make wf` 出上线依据（只看 OOS 拼接数字）。
3. 股市研究：新因子先在 `factor-registry.md` 预登记 → `make factors-us` / `factors-cn`（自动多重检验校正）。
4. **月度节奏（CN 动量，PASS 因子）**：`make cn-data-refresh && make momentum-list` → 产出 Q5 研究清单 + 自动回填上期表现（`docs/research/cn-momentum/`）。
5. 数据维护：每周 `make data && make data-check`。
6. 运行观察：`make bot-status` / `make log`；巡检告警自动弹通知。
7. 停机：`make bot-stop`（连同 launchd 服务一起卸载）。

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

## 风控与研究治理

- **政策边界（代码强制）**：止损 ∈ [-20%, -0.5%]；max_open_trades ≤ 5；单笔 ≤ 钱包 10%；必含 MaxDrawdown + StoplossGuard protections；dry_run 恒 true。
- **研究治理（迭代 v3）**：CN 组合参数已冻结（十年样本退役，前向为唯一验证）；研究 PASS ≠ 部署 PASS——部署另过 **Deployment Gate G1-G5**（DSR≥0.95 / 基准超额>0 / IR≥0.3 / 成本翻倍净夏普>0 / 前向≥12 期）；统计显著性带 Newey-West 稳健列；`make ft-bias-check`（freqtrade 官方前视/递归检查）为策略变更发布闸门；`make recon` 对账 dry-run 成交与回测假设。
- 配置层：最多 3 仓、单笔 500 USDT（模拟资金 10000）、限价进出。
- 运维层：launchd 托管崩溃自愈（已实测 8 秒拉起）、启动强制审计、定时巡检告警、本机 API 绕过系统代理；`make check` 含静态检查（ruff）+ 测试 + 审计 + 数据质量（覆盖币市/美股/A股）。
- 密钥纪律：仓库零密钥，`.env` 不入库；dry-run 全程无需交易所密钥。

## 转实盘前置条件（本阶段不做）

1. 信号侧：通过 **Deployment Gate G1-G5**（已工具化：`python -m quantlab.deployment_gate`，含 DSR/基准超额/IR/成本压力/前向时长五关；币市策略另须 walk-forward OOS 拼接为正——当前均不满足）。
2. 执行侧：模拟盘连续稳定运行 ≥ 4 周，`make recon` 成交对账样本 ≥ 30 笔且偏差可解释。
3. 账户侧：API key 最小权限（禁提币）+ 独立子账户 + 硬性资金上限 + 交易所端止损。
4. 自行评估所在地监管合规风险。

## 多市场路线（进行中）

原"阶段二自研框架"路线已作废（体制过滤已证伪、自研引擎非瓶颈，见路线图"已作废项"）。现行战略：**美股日频截面因子研究（主攻）→ A 股研究搭车 → 港股缓议**，同步补齐统计严谨性工具箱（deflated Sharpe、多重检验校正、置换检验）。完整清单与进度：`docs/superpowers/specs/2026-08-12-multimarket-roadmap.md`。

## 免责声明

加密货币波动极大，历史回测不代表未来收益。本仓库仅供学习研究，不构成投资建议；实盘交易风险自担。
