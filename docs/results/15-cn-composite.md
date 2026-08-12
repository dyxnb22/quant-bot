# 因子初检报告：A 股 沪深 300

- 日期: 2026-08-12 19:11:46 | 协议与预登记: `docs/results/factor-registry.md`
- 股池: 沪深 300 点时成分掩码已应用（baostock 月末快照）
- 家族试验数 n_trials = 10（DSR 按此扣减；BH 在本批 1 个假设内）

| 因子 | 月数 | IC 均值 | IC t | NW t | NW p | 置换 p(信息) | BH 显著(NW) | 分段一致率 | 多空净(月) | 净夏普 | DSR | 单调性 | 判定 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| composite_mom_lto | 107 | +0.0752 | +3.34 | +3.86 | 0.000 | 0.001 | ✓ | 89% | +1.065% | +0.17 | 0.58 | +1.00 | PASS（初检） |

分层月均收益（Q1→Q5）：

- composite_mom_lto: -0.165% / +0.095% / +0.247% / +0.920% / +0.940%

---
溯源: commit 789cdbc+dirty | 数据指纹 sha1:4ae7c87592 | 命令 `/Users/diaoyuxuan/quant-bot/quantlab/factor_eval.py --market cn --factors composite_mom_lto --report-to` | 2026-08-12 19:11:46
