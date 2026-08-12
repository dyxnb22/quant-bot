# 运维手册（OPERATIONS）

本项目已进入"运维节奏"：**不再主动堆功能，让时间产生证据**。
本手册是日常操作的唯一入口；开发类工作只在《触发表》条件点亮时进行。

## 0. 常驻服务（无需操作，出问题会有 macOS 通知）

| 服务 | launchd 标签 | 职责 |
|---|---|---|
| 币市模拟盘 | com.quantbot.dryrun | dry-run 交易，崩溃自动拉起（重启也过风险审计） |
| 健康巡检 | com.quantbot.healthcheck | 每 15 分钟查服务/进程/API/心跳，连续 2 次失败才通知（去抖） |
| LLM 值班日报 | com.quantbot.dailybrief | 每天 09:00 生成，产物在 `user_data/logs/daily_brief/` |

状态速查：`make bot-status`；巡检手动跑：`make health`。

## 1. 周度（约 5 分钟）

```bash
make data && make data-check   # 币市 K 线增量 + 三市场数据质量
make recon                     # 成交对账（样本 <30 笔前只看管道是否正常）
```

顺手扫一眼最新日报（`user_data/logs/daily_brief/`）有无异常提示。

## 2. 月度（月初第一个交易日后，约 20 分钟）——最重要的节奏

```bash
make cn-data-refresh      # 沪深300 全量刷新（staging→校验→原子切换；断了重跑即续传）
make cn500-data-refresh   # 中证500 全量刷新（同机制；与上一条错开跑，避免 baostock 限流）
make data-check           # 确认 cn/cn500 覆盖率 ≥90% 且六字段一致
make momentum-list        # 三候选清单 + 前向账本各 +1 + 上月表现回填
make us-data              # 美股月度刷新（40 天新鲜度阈值）
git add -A && git commit -m "chore: YYYY-MM 月度清单与账本" && git push
```

产出检查：
- 三份清单：`cn-momentum/<月>.md`（冻结部署候选）、`cn-composite/<月>.md`、
  `cn500-composite/<月>.md`（两个观察期候选）
- `forward-ledger.jsonl` 三条新条目（rule = momentum / composite / cn500_composite）
- `tracking.md` 回填的上月实现收益 vs 基准

**这一步是 G5 时钟的唯一走针方式，漏跑一个月 = 前向证据晚一个月。**

## 3. 季度（约 30 分钟）

```bash
make gates       # 三候选 Deployment Gate 全跑（未过退出码非零属正常）
make review      # LLM 复盘（如模拟盘有新平仓）
```

复盘三个问题：账本上三候选的已实现超额 vs 回测预期偏差多大？对账样本滑点分布有无恶化？
各候选 G1（DSR）/G5（前向 N/12）走到哪了？观察期候选满 6 期后按登记册预登记标准评估主候选切换。

三候选基线存照（2026-08-12）：momentum 3/5（G1 0.555）；composite 3/5（G1 0.585，可交易年化 +9.15%）；
cn500_composite 2/5（G1 0.636 最高但 G3 IR 0.12——研究最强但中盘执行摩擦大，长仓可交易口径最弱）。

## 4. 任何代码/策略/配置变更时（不分周期）

```bash
make check          # lint + 104 测试 + 风险审计 + 数据质量，全绿才继续
make ft-bias-check  # 涉及策略逻辑变更时：官方前视/递归偏差检查（输出自动归档）
```

研究纪律（违反 = 结论作废）：
1. 新检验对象必须先在 `docs/results/factor-registry.md` 预登记 + `registry.json` 计数 +1，**先提交后跑数**；
2. 冻结口径（动量组合参数、2016-2026 样本）不得重开（代码护栏 `FROZEN_OVERRIDE` 仅供历史复现）；
3. 被拒因子不得换个说法重测（想复检 = 新登记 + 计数 +1，接受 DSR 惩罚）；
4. 前向账本只追加不修改，漏月如实留空。

## 5. 故障速查

| 症状 | 处置 |
|---|---|
| 获取锁超时 | 有其他任务（下载/清单/Gate）在跑，等它结束；确认无进程后可删 `user_data/cn_data.lock` |
| data-check FAIL: cn 覆盖率不足 | 下载中断，`make cn-data-refresh` 续传（staging 会接着跑，live 不受影响） |
| baostock 变慢/挂起 | 日间限流（约 1500+ 次查询触发，实测衰减曲线 0.6s→4s→>7min）；等 2-3 小时或深夜再跑 |
| 巡检告警 | `make bot-status` 看具体项；bot 死了 `make bot-start`（会先过审计） |
| 清单被拒：股池 <250 | 数据不完整守卫生效，先完成数据刷新 |
| CI 红 | 看 Actions 日志；本地 `make check` 复现 |

## 6. 触发表（什么时候才回来写代码）

| 触发条件 | 动作 |
|---|---|
| G5 满 12 期 且 G1 达标 | 进入真实资金讨论（另立风险评估，含交易所端止损/子账户/资金上限） |
| 复合候选前向 6+ 期且明显优于动量 | 评估月度清单主候选切换（预登记决策标准先行） |
| 对账样本 ≥30 笔 | 对账升级为订单事件级 + 名义加权统计 |
| 因子库 ≥10 且手工组合遇瓶颈 | ML 滚动训练工作流（Qlib 式） |
| 美股出现 PASS 因子 + 提供 Alpaca key | 美股 paper 前向验证 |
| 决定重启币市研究 | Binance Vision 微结构数据（aggTrades/清算/OI）+ WS 自录 |
| 出现跨市场可迁移因子证据 | 评估港股 |
| 免费/可接受成本的 PIT 行业数据出现 | 行业中性升级为基准权重中性 + 历史行业回放 |

## 7. 当前基线（2026-08-12 收口时）

- 检验记录：18 个对象，3 PASS（CN 动量=冻结部署候选、低换手=组合原料、复合=观察期候选）
- Gate：3/5（G2 超额 +7.54%/年、G3 IR 0.86、G4 压力通过；G1 DSR 0.578、G5 1/12 未过）
- 前向账本：2026-07 起双规则计数；对账样本 1 笔（SOL 入场 -1.3bps）
- 质量基线：104 测试 / lint 全绿 / CI 绿 / data-check 三市场全绿
