"""假设 2（来自 05 号 LLM 复盘）：持仓时间熔断。

持仓 ≥12 小时且浮盈 <3% 的僵尸仓强制离场；roi 240 分钟档 5% → 4% 加快兑现。
预期：消灭"拖到亏"的长持仓；检验：walk-forward OOS 拼接收益 vs 基线。
"""

from EmaRsiStrategy import EmaRsiStrategy


class EmaRsiH2TimeExit(EmaRsiStrategy):
    minimal_roi = {"0": 0.10, "240": 0.04, "720": 0.02, "1440": 0}

    def custom_exit(self, pair, trade, current_time, current_rate, current_profit, **kwargs):
        held_minutes = (current_time - trade.open_date_utc).total_seconds() / 60
        if held_minutes >= 720 and current_profit < 0.03:
            return "time_cutoff"
        return None
