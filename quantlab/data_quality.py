"""K 线数据质量检查：缺口/重复/OHLC 一致性/零成交量/新鲜度。

原则：坏数据必须被主动发现——静默的坏数据会产出貌似可信的错误回测结论。
少量缺口是交易所维护的正常现象（软告警）；重复、OHLC 矛盾、数据过期是硬失败。
"""

import argparse
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from quantlab.strategy_loader import PROJECT_DIR

DATA_DIR = PROJECT_DIR / "user_data" / "data" / "okx"
TIMEFRAME_DELTAS = {
    "5m": timedelta(minutes=5), "15m": timedelta(minutes=15),
    "1h": timedelta(hours=1), "4h": timedelta(hours=4), "1d": timedelta(days=1),
}
GAP_HARD_LIMIT = 10          # 缺口超过此数视为硬失败
ZERO_VOLUME_PCT_LIMIT = 5.0


@dataclass
class DataReport:
    name: str
    rows: int = 0
    gaps: int = 0
    duplicates: int = 0
    ohlc_errors: int = 0
    zero_volume_pct: float = 0.0
    age_hours: float = 0.0
    problems: list = field(default_factory=list)
    warnings: list = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems


def check_ohlcv(df: pd.DataFrame, timeframe: str, now=None,
                max_age_hours: float = 48.0, name: str = "<df>") -> DataReport:
    delta = TIMEFRAME_DELTAS[timeframe]
    now = now or datetime.now(timezone.utc)
    report = DataReport(name=name, rows=len(df))

    report.duplicates = int(df["date"].duplicated().sum())
    if report.duplicates:
        report.problems.append(f"重复时间戳 {report.duplicates} 处")

    diffs = df["date"].diff().dropna()
    report.gaps = int((diffs != delta).sum())
    if report.gaps > GAP_HARD_LIMIT:
        report.problems.append(f"时间缺口 {report.gaps} 处 > {GAP_HARD_LIMIT}")
    elif report.gaps:
        report.warnings.append(f"时间缺口 {report.gaps} 处（交易所维护属正常，关注即可）")

    bad_high = df["high"] < df[["open", "close", "low"]].max(axis=1)
    bad_low = df["low"] > df[["open", "close", "high"]].min(axis=1)
    report.ohlc_errors = int((bad_high | bad_low).sum())
    if report.ohlc_errors:
        report.problems.append(f"OHLC 不一致 {report.ohlc_errors} 行")

    report.zero_volume_pct = float((df["volume"] <= 0).mean() * 100)
    if report.zero_volume_pct > ZERO_VOLUME_PCT_LIMIT:
        report.problems.append(f"零成交量占比 {report.zero_volume_pct:.1f}%")

    report.age_hours = (now - df["date"].iloc[-1]).total_seconds() / 3600
    if report.age_hours > max_age_hours:
        report.problems.append(f"数据过期 {report.age_hours:.0f}h > {max_age_hours}h（请 make data）")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="检查已下载 K 线的数据质量")
    parser.add_argument("--max-age-hours", type=float, default=48.0)
    args = parser.parse_args()

    files = sorted(DATA_DIR.glob("*.feather"))
    if not files:
        print(f"未找到数据文件：{DATA_DIR}（先运行 make data）")
        return 1

    failed = False
    for file in files:
        timeframe = file.stem.rsplit("-", 1)[-1]
        df = pd.read_feather(file)
        report = check_ohlcv(df, timeframe, max_age_hours=args.max_age_hours, name=file.name)
        status = "OK " if report.ok else "FAIL"
        print(f"[{status}] {report.name}: {report.rows} 行, 缺口 {report.gaps}, "
              f"最后K线 {report.age_hours:.1f}h 前")
        for message in report.problems:
            print(f"       ✗ {message}")
        for message in report.warnings:
            print(f"       ! {message}")
        failed = failed or not report.ok
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
