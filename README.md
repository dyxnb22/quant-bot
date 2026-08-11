# quant-bot

个人加密货币量化交易工作台。**学习与研究优先，仓库内恒为 dry-run（模拟盘），不涉及真实资金。**

基于 [Freqtrade](https://www.freqtrade.io/) 2026.x / Python 3.14 / OKX 现货公共行情。

## 项目定位

这是一套完整可用的个人量化研究闭环：**历史数据 → 策略（带测试）→ 回测 → 参数优化 → 过拟合检验 → 模拟盘常驻运行**。

明确的预期管理：当前两个基线策略在回测中均跑输"买入持有"（见 `docs/results/`），它们的价值是承载方法论，不是赚钱。回测结论已实证：**回测好看 ≠ 实盘赚钱，样本外衰减是常态**。

## 快速开始

```bash
make setup        # 创建 .venv 并安装 freqtrade + pytest
cp .env.example .env  # 然后编辑 .env，凭据随意生成（仅本机 API 监控用）
make data         # 下载 OKX 1h 历史数据（2023 至今，4 个交易对）
make test         # 策略单元测试（含无未来函数检测）
make backtest     # 双策略对比回测
make bot-start    # 启动 dry-run 模拟盘（launchd 常驻）
make bot-status   # 查看进程/API/持仓/收益
```

浏览器打开 `http://127.0.0.1:8080` 进入 FreqUI 监控界面（账号密码见 `.env`）。

## 日常工作流

1. `make data` —— 增量更新 K 线（建议每周）。
2. `make test && make backtest` —— 改动策略后必跑。
3. `make hyperopt` —— 只在**样本内**时间段调参。
4. `make oos` —— 用**样本外**时间段检验，样本外数字才可信。
5. `make bot-status` / `make log` —— 观察模拟盘与回测预期是否一致。

## 目录结构

```
config/config.json        # 主配置（dry-run，无任何密钥）
user_data/strategies/     # 策略代码 + hyperopt 参数（.json 会覆盖类属性！）
scripts/                  # 数据下载、bot 启停/状态
tests/                    # 策略单元测试
docs/superpowers/         # 设计文档与实施计划
docs/results/             # 回测报告与过拟合检验（必读）
```

## 风控设计

- 配置层：最多 3 仓、单笔 500 USDT（模拟资金 10000）、限价进出。
- 策略层：强制止损；protections 三件套——连续止损熔断（StoplossGuard）、回撤超 15% 暂停（MaxDrawdown）、平仓冷却（CooldownPeriod）。
- 运维层：launchd 托管，崩溃自动拉起、登录自启；日志滚动落盘；API 仅绑定 127.0.0.1。
- 密钥纪律：仓库零密钥，`.env` 不入库；dry-run 全程无需交易所密钥。

## 转实盘前置条件（本阶段不做）

1. 模拟盘连续稳定运行 ≥ 4 周，且成交行为与回测假设偏差可解释。
2. 策略样本外指标为正且经 walk-forward 多窗口验证。
3. OKX API key 最小权限（禁提币）+ 独立子账户 + 硬性资金上限。
4. 自行评估所在地监管合规风险。

## 阶段二路线（远期）

基于 CCXT 自研事件驱动框架：行情网关、策略引擎、风控中间件、执行器四层解耦；walk-forward 优化器；多体制回测覆盖。届时另立设计文档。

## 免责声明

加密货币波动极大，历史回测不代表未来收益。本仓库仅供学习研究，不构成投资建议；实盘交易风险自担。
