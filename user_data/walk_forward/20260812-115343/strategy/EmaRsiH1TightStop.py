"""假设 1（来自 05 号 LLM 复盘）：收紧止损 -8% → -4%。

预期：截断 exit_signal 慢性失血与 stop_loss 深亏；代价是止损触发频率上升。
检验：walk-forward OOS 拼接收益 vs 基线。
"""

from EmaRsiStrategy import EmaRsiStrategy


class EmaRsiH1TightStop(EmaRsiStrategy):
    stoploss = -0.04
