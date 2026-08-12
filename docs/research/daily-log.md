# 日检日志（make daily 自动追加）

每天启动一次 `make daily`：增量更新币市数据 → 巡检模拟盘与数据面板 → 追加一节记录。
字段含义与各脚本的产物位置见 `docs/research/run-registry.md`。

---
## 2026-08-12 22:32

| 检查 | 结果 | 详情 |
|---|---|---|
| 币市数据增量更新 | ✓ | 增量更新完成 |
| 模拟盘健康（服务/进程/心跳/API） | ✓ | launchd✓ 进程✓ 日志心跳✓ API✓ |
| 模拟盘账面（实时 API） | ✓ | 平仓 0 笔 | 已实现 +0.00 USDT | 胜率 0% | 最大回撤 0.00% | 持仓 1 笔 | 对账样本 0/30 |
| 数据质量（币市 K 线 + 股市面板） | ✓ | 7 项全部通过 |
| 前向账本（三候选 G5 进度） | ✓ | G5 前向进度：momentum 1/12，composite 1/12，cn500_composite 1/12 |

结论：5/5 通过。溯源: commit 075914b+dirty | 数据指纹 sha1:6d59d23089 | 命令 `/Users/diaoyuxuan/quant-bot/quantlab/daily_check.py` | 2026-08-12 22:32:31

