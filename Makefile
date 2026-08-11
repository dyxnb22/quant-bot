.PHONY: help setup data test backtest hyperopt oos bot-start bot-stop bot-status log

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
