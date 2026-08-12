"""A 股财报点时管道：baostock 季频 roeAvg + 公告日（pubDate）→ PIT ROE 日频面板。

解锁登记册挂起项"ROE/应计批次"的第一步（ROE）。点时纪律与美股 EDGAR 管道一致：
数值只在公告日之后可见；前向填充上限 130 个交易日（约两季）。

体量：沪深300 十年 = 622 标的 × 40 季 ≈ 2.5 万次查询（约 3.5-4 小时）——
日间限流不可行，走深夜下载（scripts/cn_fundamentals_night.sh，02:30，成功自卸载）。
断点续传：按标的粒度（含"无数据"哨兵行，避免重复查询空标的）。
"""

import argparse
import socket
import sys
import time
from datetime import date, timedelta
from pathlib import Path

socket.setdefaulttimeout(30)

# E402 豁免原因：超时兜底必须先于 baostock 建连
import baostock as bs  # noqa: E402
import pandas as pd  # noqa: E402

from quantlab.cn_data import UNIVERSES, atomic_write_feather  # noqa: E402

FFILL_LIMIT_DAYS = 130  # 交易日，约两季（与美股管道一致）
POLITE_SLEEP = 0.3


def fundamentals_path(data_dir: Path) -> Path:
    return data_dir / "fundamentals.feather"


def fetch_ticker_quarters(ticker: str, years: int) -> list[dict]:
    """单标的全部季度 roeAvg（含公告日）；无数据季度自然跳过。"""
    rows = []
    today = date.today()
    for year in range(today.year - years, today.year + 1):
        for quarter in (1, 2, 3, 4):
            if (year, quarter * 3) > (today.year, today.month):
                continue
            result = bs.query_profit_data(code=ticker, year=year, quarter=quarter)
            while result.next():
                record = dict(zip(result.fields, result.get_row_data()))
                if record.get("roeAvg") and record.get("pubDate"):
                    rows.append({
                        "ticker": ticker,
                        "stat_date": pd.Timestamp(record["statDate"]),
                        "pub_date": pd.Timestamp(record["pubDate"]),
                        "roe": float(record["roeAvg"]),
                    })
            time.sleep(POLITE_SLEEP)
    return rows


def download_cn_fundamentals(universe: str = "hs300", years: int = 10) -> Path:
    """全宇宙季频下载（断点续传，每 10 个标的落盘一次）。"""
    data_dir = UNIVERSES[universe]["dir"]
    target = fundamentals_path(data_dir)
    close = pd.read_feather(data_dir / "close.feather")
    tickers = sorted(c for c in close.columns if c != close.columns[0])

    existing = pd.read_feather(target) if target.exists() else pd.DataFrame(
        columns=["ticker", "stat_date", "pub_date", "roe"])
    done = set(existing["ticker"])
    pending = [t for t in tickers if t not in done]
    print(f"{universe} 财报下载：总 {len(tickers)}，已完成 {len(done)}，"
          f"待下载 {len(pending)}（约 {len(pending) * years * 4 * 0.5 / 3600:.1f} 小时）",
          flush=True)

    login = bs.login()
    if login.error_code != "0":
        raise RuntimeError(f"baostock 登录失败: {login.error_msg}")
    slow_streak = 0
    try:
        buffer = []
        for i, ticker in enumerate(pending, 1):
            started = time.monotonic()
            try:
                rows = fetch_ticker_quarters(ticker, years)
            except Exception as error:
                print(f"  {ticker}: 失败 {error}，重登陆后继续", flush=True)
                try:
                    bs.logout()
                except Exception:
                    pass
                time.sleep(5)
                bs.login()
                rows = fetch_ticker_quarters(ticker, years)
            # 哨兵行：零数据标的也记录（NaT），断点续传不再重查
            buffer.extend(rows or [{"ticker": ticker, "stat_date": pd.NaT,
                                    "pub_date": pd.NaT, "roe": float("nan")}])
            if i % 10 == 0 or i == len(pending):
                existing = pd.concat([existing, pd.DataFrame(buffer)],
                                     ignore_index=True)
                buffer = []
                atomic_write_feather(existing, target)
                print(f"  {i}/{len(pending)} 已落盘（累计 {len(existing)} 行）",
                      flush=True)
            # 限流自保护：正常约 15-20s/标的；连续 2 个 >90s 判定被限流，
            # 存检查点退出——把干净会话留给下一次定时启动（02:30）续传
            elapsed = time.monotonic() - started
            slow_streak = slow_streak + 1 if elapsed > 90 else 0
            if slow_streak >= 2:
                existing = pd.concat([existing, pd.DataFrame(buffer)],
                                     ignore_index=True)
                atomic_write_feather(existing, target)
                print(f"  限流嫌疑（连续 {slow_streak} 个标的 >90s），"
                      f"已存检查点 {i}/{len(pending)}，退出待深夜续传", flush=True)
                raise SystemExit(75)
    finally:
        bs.logout()
    return target


def build_roe_panel(daily_index: pd.DatetimeIndex,
                    records: pd.DataFrame) -> pd.DataFrame:
    """财报记录 → 日频 PIT ROE 面板（pubDate 起生效，ffill 限约两季）。"""
    columns = {}
    limit = timedelta(days=FFILL_LIMIT_DAYS * 7 // 5)
    for ticker, group in records.dropna(subset=["pub_date"]).groupby("ticker"):
        # 同一公告日多条（更正公告）→ 取报告期最新的一条
        series = (group.sort_values(["pub_date", "stat_date"])
                  .drop_duplicates("pub_date", keep="last")
                  .set_index("pub_date")["roe"])
        aligned = series.reindex(series.index.union(daily_index)).ffill() \
            .reindex(daily_index)
        last_event = pd.Series(series.index, index=series.index).reindex(
            series.index.union(daily_index)).ffill().reindex(daily_index)
        age_ok = (daily_index - pd.DatetimeIndex(last_event)) <= limit
        columns[ticker] = aligned.where(age_ok)
    return pd.DataFrame(columns, index=daily_index)


def load_roe_panel(daily_index: pd.DatetimeIndex,
                   data_dir: Path) -> pd.DataFrame:
    target = fundamentals_path(data_dir)
    if not target.exists():
        raise FileNotFoundError(f"{target} 缺失：先运行深夜财报下载")
    return build_roe_panel(daily_index, pd.read_feather(target))


def main() -> int:
    parser = argparse.ArgumentParser(description="A 股财报季频下载（点时 ROE）")
    parser.add_argument("--universe", choices=list(UNIVERSES), default="hs300")
    parser.add_argument("--years", type=int, default=10)
    parser.add_argument("--smoke", type=int, default=0,
                        help="只下载前 N 个标的（管道可行性验证，不落地）")
    args = parser.parse_args()

    if args.smoke:
        data_dir = UNIVERSES[args.universe]["dir"]
        close = pd.read_feather(data_dir / "close.feather")
        tickers = sorted(c for c in close.columns if c != close.columns[0])[:args.smoke]
        login = bs.login()
        if login.error_code != "0":
            raise RuntimeError(f"baostock 登录失败: {login.error_msg}")
        try:
            for ticker in tickers:
                rows = fetch_ticker_quarters(ticker, years=2)
                sample = rows[-1] if rows else "无数据"
                print(f"  {ticker}: {len(rows)} 季，样例 {sample}", flush=True)
        finally:
            bs.logout()
        return 0

    from quantlab.locking import file_lock
    with file_lock(UNIVERSES[args.universe]["lock"] + "_fundamentals"):
        download_cn_fundamentals(args.universe, args.years)
    return 0


if __name__ == "__main__":
    sys.exit(main())
