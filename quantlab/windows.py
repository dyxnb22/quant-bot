"""Walk-forward 窗口切分（纯函数，不依赖 freqtrade）。"""

import calendar
from dataclasses import dataclass
from datetime import date


def add_months(d: date, months: int) -> date:
    total = d.year * 12 + (d.month - 1) + months
    year, month0 = divmod(total, 12)
    day = min(d.day, calendar.monthrange(year, month0 + 1)[1])
    return date(year, month0 + 1, day)


@dataclass(frozen=True)
class Window:
    is_start: date
    is_end: date  # 同时是 oos_start
    oos_end: date

    @property
    def is_timerange(self) -> str:
        return f"{self.is_start:%Y%m%d}-{self.is_end:%Y%m%d}"

    @property
    def oos_timerange(self) -> str:
        return f"{self.is_end:%Y%m%d}-{self.oos_end:%Y%m%d}"


def build_windows(start: date, end: date, is_months: int = 12,
                  oos_months: int = 3, step_months: int = 3) -> list[Window]:
    windows = []
    cursor = start
    while True:
        is_end = add_months(cursor, is_months)
        oos_end = add_months(is_end, oos_months)
        if oos_end > end:
            return windows
        windows.append(Window(cursor, is_end, oos_end))
        cursor = add_months(cursor, step_months)
