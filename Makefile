.PHONY: help setup data test backtest hyperopt oos bot-start bot-stop bot-status log \
	audit data-check wf health health-install health-uninstall check

FT := .venv/bin/freqtrade
CFG := --config config/config.json

help: ## 显示所有命令
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-12s %s\n", $$1, $$2}'

setup: ## 创建虚拟环境并按锁文件安装依赖（可复现）
	python3 -m venv .venv
	.venv/bin/pip install --upgrade pip wheel
	.venv/bin/pip install -r requirements.lock

data: ## 下载/增量更新历史数据
	./scripts/download_data.sh

funding: ## 下载/更新资金费率历史（Binance 归档 + OKX 尾部）
	.venv/bin/python -m quantlab.funding

us-data: ## 下载 S&P 500 日频数据（YEARS 可覆盖，默认 4）
	.venv/bin/python -m quantlab.us_data --years $(or $(YEARS),4)

us-smoke: ## 美股截面管道冒烟（12-1 动量端到端）
	.venv/bin/python -m quantlab.factors

cn-data: ## 下载沪深300日频数据（baostock，YEARS 可覆盖）
	.venv/bin/python -u -m quantlab.cn_data --years $(or $(YEARS),4)

factors-us: ## 美股四因子初检（预登记协议）
	.venv/bin/python -m quantlab.factor_eval --market us

factors-cn: ## A股四因子初检（预登记协议）
	.venv/bin/python -m quantlab.factor_eval --market cn

factors-cn-batch2: ## A股批次2检验：EP/BP/SP/低换手（需深夜数据落地后运行）
	.venv/bin/python -m quantlab.factor_eval --market cn \
		--factors ep bp sp low_turnover \
		--report-to docs/results/13-cn-value-factors.md

cn-data-refresh: ## 全量刷新沪深300行情（月度更新用，先存档 manifest）
	.venv/bin/python -m quantlab.manifest
	.venv/bin/python -u -m quantlab.cn_data --years 10 --refresh

cn500-data-refresh: ## 全量刷新中证500行情（月度更新用）
	.venv/bin/python -u -m quantlab.cn_data --universe zz500 --years 10 --refresh

gates: ## 三候选 Deployment Gate 全跑（季度复查）
	-.venv/bin/python -m quantlab.deployment_gate --rule momentum
	-.venv/bin/python -m quantlab.deployment_gate --rule composite
	-.venv/bin/python -m quantlab.deployment_gate --rule cn500_composite

manifest: ## 数据快照指纹（行数/哈希，研究输入可追溯）
	.venv/bin/python -m quantlab.manifest

results-index: ## 重新生成研究报告索引
	.venv/bin/python -m quantlab.results_index

momentum-list: ## 生成 CN 动量月度研究清单（PASS 因子落地）
	.venv/bin/python -m quantlab.cn_momentum_list

test: ## 运行策略单元测试
	.venv/bin/python -m pytest tests/ -v

backtest: ## 双策略对比回测（TIMERANGE 可覆盖，默认 20240101-）
	$(FT) backtesting $(CFG) --strategy-list EmaRsiStrategy RsiMeanRevertStrategy --timerange $(or $(TIMERANGE),20240101-) --breakdown month

hyperopt: ## 样本内参数优化（STRATEGY 可覆盖，默认 EmaRsiStrategy）
	$(FT) hyperopt $(CFG) --strategy $(or $(STRATEGY),EmaRsiStrategy) --hyperopt-loss SharpeHyperOptLoss --spaces buy roi stoploss --timerange 20230601-20250601 -e 60

oos: ## 样本外验证回测（永远用未参与优化的时间段）
	$(FT) backtesting $(CFG) --strategy $(or $(STRATEGY),EmaRsiStrategy) --timerange 20250601-

bot-start: ## 启动 dry-run 模拟盘（launchd 常驻，崩溃自启）
	./scripts/bot_start.sh

bot-stop: ## 停止模拟盘并卸载 launchd 服务
	./scripts/bot_stop.sh

bot-status: ## 查看模拟盘状态（服务/进程/API/持仓/收益）
	./scripts/bot_status.sh

recon: ## 成交对账（dry-run 成交 vs 回测假设滑点）
	.venv/bin/python -m quantlab.trade_recon

log: ## 跟踪模拟盘日志
	tail -f user_data/logs/freqtrade.log

ft-bias-check: ## Freqtrade 官方前视/递归偏差检查（策略变更后的发布闸门，输出归档）
	mkdir -p user_data/logs/bias
	.venv/bin/freqtrade lookahead-analysis $(CFG) --config config/config.bias-check.json --strategy $(or $(STRATEGY),EmaRsiStrategy) --timerange 20250101-20260101 2>&1 | tee "user_data/logs/bias/$$(date +%F)-$(or $(STRATEGY),EmaRsiStrategy)-lookahead.log"
	.venv/bin/freqtrade recursive-analysis $(CFG) --strategy $(or $(STRATEGY),EmaRsiStrategy) --timerange 20250101-20250401 --startup-candle 100 199 399 499 999 2>&1 | tee "user_data/logs/bias/$$(date +%F)-$(or $(STRATEGY),EmaRsiStrategy)-recursive.log"

audit: ## 风险政策审计（config + 策略生效参数）
	.venv/bin/python -m quantlab.risk_policy

data-check: ## 数据质量检查（缺口/重复/OHLC/新鲜度）
	.venv/bin/python -m quantlab.data_quality

wf: ## walk-forward 验证（STRATEGY/EPOCHS 可覆盖）
	.venv/bin/python -m quantlab.walk_forward --strategy $(or $(STRATEGY),EmaRsiStrategy) --epochs $(or $(EPOCHS),30)

health: ## 健康巡检（手动）
	.venv/bin/python -m quantlab.health

health-install: ## 安装 15 分钟定时巡检（launchd + 本地通知）
	./scripts/health_install.sh

health-uninstall: ## 卸载定时巡检
	./scripts/health_uninstall.sh

review: ## LLM 交易复盘（ZIP/STRATEGY 可覆盖，需 DEEPSEEK_API_KEY）
	.venv/bin/python -m quantlab.trade_review $(if $(ZIP),--zip $(ZIP)) --strategy $(or $(STRATEGY),EmaRsiStrategy)

brief: ## LLM 值班日报（手动生成，需 DEEPSEEK_API_KEY）
	.venv/bin/python -m quantlab.daily_brief

brief-install: ## 安装每日 09:00 值班日报（launchd）
	./scripts/brief_install.sh

brief-uninstall: ## 卸载值班日报定时任务
	./scripts/brief_uninstall.sh

lint: ## 静态检查（ruff，高信号规则集）
	.venv/bin/ruff check quantlab/ tests/ user_data/strategies/

check: ## 一键体检：静态检查 + 测试 + 风险审计 + 数据质量
	.venv/bin/ruff check quantlab/ tests/ user_data/strategies/
	.venv/bin/python -m pytest tests/ -q
	.venv/bin/python -m quantlab.risk_policy
	.venv/bin/python -m quantlab.data_quality
