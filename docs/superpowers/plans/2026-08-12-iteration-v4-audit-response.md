# 迭代 v4：第二轮审计响应（P0×1 + P1×12 + P2/P3）

依据：2026-08-12 第二轮外部审计（整改核查：7 项中 1 真实 6 部分）。
本计划先于任何代码修改提交；协议变更条款自提交起对**后续批次**生效，不回改历史判定。

## 预登记协议变更（v2 → v3）

1. **显著性统计（P1-02）**：自本提交后的新批次与 Gate，显著性以 **Newey-West HAC p 值**为准
   （正态近似双侧转单侧），置换 p 保留为信息列。块自助（block bootstrap）列为后续升级项。
2. **试验计数（P1-03）**：`docs/results/registry.json` 为机器可读登记册，按市场家族记录
   **只增不减**的累计试验数；factor_eval 自动读取，CLI 手工覆盖入口删除。
3. **G4 重定义（P1-05）**：成本翻倍压力改为 **tradable_sim 引擎**（佣金与印花税均 ×2），
   与 G1-G3 同引擎同区间；基准改按**相同成交日区间**计算。
4. **部分月剔除（P1-09）**：`month_end()` 默认剔除未完成月（判定规则：面板最后交易日的
   次一工作日仍在同月 → 该月未完成）。清单的信号标签随之修正为"最近完整月末"。
5. **G5 证据源（P1-04）**：前向月份计数改读 **append-only 前向账本**
   （`docs/research/cn-momentum/forward-ledger.jsonl`，入库，git 历史即防篡改时间戳），
   不再数数据行。清单工具每次运行追加账本条目。
6. **冻结护栏（P1-04）**：portfolio_compare 加运行护栏（需 `FROZEN_OVERRIDE=1` 并打印
   退役声明）；Gate 未通过时退出码非零。

## 简化决策（声明而非隐瞒）

- **数据事务（P0）**：不建完整版本指针系统；采用"staging 唯一写路径 + 校验后逐文件
  os.replace + 跨进程文件锁（下载/清单/Gate 共用）+ manifest"。个人单机规模下该组合
  已消除混合版本与并发损毁风险；版本指针列为触发项（多机或多写者出现时）。
- **PIT 行业（P1-08）**：免费源无历史行业快照；维持当前快照并在登记册/报告声明
  "行业内数量中性 + 行业漂移误差"；PIT 行业数据列为付费数据触发项。
- **portfolio_sim 费用模型（P1-06）**：作为研究粗筛保留，模块与 12 号报告加"忽略保留
  仓位再平衡费用"声明；可交易结论一律以 tradable_sim 为准。
- **块自助置换（P1-02 后半）**：NW-p 先行；moving-block bootstrap 列为统计工具箱下一项。

## 交付清单

- [ ] T1 `quantlab/locking.py` 跨进程锁；cn_data 下载/清单/Gate 接入（P0）
- [ ] T2 cn_data：下载一律写 staging（断点续传也在 staging），校验通过才切换 live；
      membership/index/industry 改临时文件+os.replace 单文件原子写（P0）
- [ ] T3 `month_end(drop_partial=True)` + 测试（P1-09）
- [ ] T4 stats：DSR 接受真实偏度/峰度（Gate 从月收益计算矩）；`newey_west_pvalue`；
      registry.json + factor_eval 自动 n_trials（删 --n-trials）（P1-01/02/03）
- [ ] T5 gate：G1-G4 全 tradable 引擎（成本参数化）、基准按 fill 区间、退出码、G5 读账本（P1-04/05）
- [ ] T6 tradable_sim：佣金/印花参数化；持仓连续 60 交易日无价 → 清算减记为 0（幽灵资产）（P1-10）
- [ ] T7 清单：结算按明确月份标签取起止行（不再取"最后两行"）；写前向账本；持锁写 state（P1-11）
- [ ] T8 us_data：PIT 表本地缓存（进 manifest）；起止表未知 ticker fail-closed（P1-12）
- [ ] T9 funding merge_asof tolerance=3 天（P2）
- [ ] T10 P2 快修：make setup 装 lock 文件依赖+ruff；daily_brief 平仓计数；bot_start 强制
      .env 0600 且拒绝 change_me；bot_run.sh 内嵌启动审计（KeepAlive 重启也过审计）；
      夜间任务完成后自卸载；CI 加 ruff step；ft-bias-check 输出归档 user_data/logs/bias/
- [ ] T11 文档：README（五特质计数、检验计数口径注释、前置条件）；路线图 C2 矛盾；
      v3 计划 N3/N7 状态改"代码就绪待数据/部分完成"；12 号加审计附注（P1-06/07/08 声明）；
      登记册加 P1-07（部署对象=冻结长仓规则，验证=前向账本）与 P1-08 局限声明
- [ ] T12 新增测试：锁互斥、部分月剔除、NW-p、账本 G5 计数、幽灵资产清算
