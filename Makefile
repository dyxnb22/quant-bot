.PHONY: help setup data test backtest hyperopt oos bot-start bot-stop bot-status log \
	audit data-check wf health health-install health-uninstall check

FT := .venv/bin/freqtrade
CFG := --config config/config.json

help: ## 显示所有命令
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-12s %s\n", $$1, $$2}'

setup: ## 创建虚拟环境并安装依赖
	python3 -m venv .venv
	.venv/bin/pip install --upgrade pip wheel
	.venv/bin/pip install "freqtrade[hyperopt]" pytest

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

log: ## 跟踪模拟盘日志
	tail -f user_data/logs/freqtrade.log

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

check: ## 一键体检：测试 + 风险审计 + 数据质量
	.venv/bin/python -m pytest tests/ -q
	.venv/bin/python -m quantlab.risk_policy
	.venv/bin/python -m quantlab.data_quality
