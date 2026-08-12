"""A 股日频数据管道：沪深 300 股池 + baostock 日频（前复权）落地。

数据源选型记录（2026-08-12 实测）：
- akshare/东方财富：HTTP 请求被 macOS 系统级代理劫持且连接不稳定（67 分钟仅 13/300），弃用
- baostock：自有 TCP 协议（不经 HTTP 代理）、专为批量历史数据设计，采用

定位：纯研究搭车（个人程序化执行在 A 股受限，见路线图 M3）。
股池为当前成分（幸存者偏差已声明，同美股口径）。
"""

import argparse
import socket
import sys
import time
from datetime import date, timedelta
from pathlib import Path

# 超时兜底必须先于 baostock 建连：无超时的 TCP recv 在连接断开后会永久阻塞
# （2026-08-12 实测卡死在 250/300）
socket.setdefaulttimeout(30)

import baostock as bs  # noqa: E402
import pandas as pd  # noqa: E402

from quantlab.strategy_loader import PROJECT_DIR

CN_DATA_DIR = PROJECT_DIR / "user_data" / "data" / "cn"


def fetch_csi300_tickers() -> list[str]:
    result = bs.query_hs300_stocks()
    tickers = []
    while result.next():
        tickers.append(result.get_row_data()[1])  # 形如 sh.600000
    return sorted(tickers)


def fetch_hs300_membership(month_ends) -> pd.DataFrame:
    """逐月末抓取沪深 300 点时成分快照（节假日自动回退至最近有效日）。"""
    rows = []
    for month_end_date in month_ends:
        for back in range(8):
            query_date = (month_end_date - timedelta(days=back)).strftime("%Y-%m-%d")
            result = bs.query_hs300_stocks(date=query_date)
            snapshot = []
            while result.next():
                snapshot.append(result.get_row_data()[1])
            if snapshot:
                rows.extend((month_end_date, ticker) for ticker in snapshot)
                break
        else:
            print(f"  成分快照缺失: {month_end_date:%Y-%m-%d}", flush=True)
    return pd.DataFrame(rows, columns=["date", "ticker"])


def cn_membership_mask(monthly_index, tickers) -> pd.DataFrame | None:
    """点时成员掩码（date × ticker）：每个月末用最近一期成分快照。"""
    path = CN_DATA_DIR / "membership.feather"
    if not path.exists():
        return None
    membership = pd.read_feather(path)
    membership["date"] = pd.to_datetime(membership["date"])
    snapshots = {d: set(g["ticker"]) for d, g in membership.groupby("date")}
    snapshot_dates = sorted(snapshots)
    mask = pd.DataFrame(False, index=monthly_index, columns=list(tickers))
    for month_end_date in monthly_index:
        usable = [d for d in snapshot_dates if d <= month_end_date]
        if not usable:
            continue
        members = snapshots[usable[-1]]
        mask.loc[month_end_date, [t for t in mask.columns if t in members]] = True
    return mask


def _save(closes: dict, volumes: dict) -> None:
    CN_DATA_DIR.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(closes).sort_index().reset_index().to_feather(CN_DATA_DIR / "close.feather")
    pd.DataFrame(volumes).sort_index().reset_index().to_feather(CN_DATA_DIR / "volume.feather")


def download_cn_daily(tickers: list[str], years: int = 4) -> Path:
    start = (date.today() - timedelta(days=365 * years)).isoformat()
    end = date.today().isoformat()
    closes, volumes = {}, {}
    if (CN_DATA_DIR / "close.feather").exists():
        existing = load_cn_daily()
        closes = {c: existing["close"][c] for c in existing["close"].columns}
        volumes = {c: existing["volume"][c] for c in existing["volume"].columns}
        print(f"  断点续传: 已有 {len(closes)} 个标的", flush=True)
    pending = [t for t in tickers if t not in closes]
    failed = []
    for i, ticker in enumerate(pending, 1):
        rows = []
        for attempt in range(3):
            try:
                result = bs.query_history_k_data_plus(
                    ticker, "date,close,volume",
                    start_date=start, end_date=end, frequency="d", adjustflag="2")  # 2=前复权
                while result.next():
                    rows.append(result.get_row_data())
                break
            except Exception:
                rows = []
                # 连接可能已死：重登陆后重试
                try:
                    bs.logout()
                except Exception:
                    pass
                time.sleep(2 * (attempt + 1))
                bs.login()
        if not rows:
            failed.append(ticker)
            continue
        frame = pd.DataFrame(rows, columns=["date", "close", "volume"])
        frame["date"] = pd.to_datetime(frame["date"])
        frame = frame.set_index("date")
        closes[ticker] = pd.to_numeric(frame["close"], errors="coerce")
        volumes[ticker] = pd.to_numeric(frame["volume"], errors="coerce")
        if i % 50 == 0:
            _save(closes, volumes)
            print(f"  已下载 {i}/{len(pending)}（增量已落盘）", flush=True)
    _save(closes, volumes)
    if failed:
        print(f"  下载失败 {len(failed)} 个: {failed[:10]}", flush=True)
    return CN_DATA_DIR


def fetch_industry() -> pd.DataFrame:
    """全市场行业分类（申万），调用方负责 bs.login。"""
    result = bs.query_stock_industry()
    rows = []
    while result.next():
        rows.append(result.get_row_data())
    frame = pd.DataFrame(rows, columns=["updateDate", "code", "code_name",
                                        "industry", "industryClassification"])
    return frame[["code", "code_name", "industry"]]


def load_industry() -> pd.DataFrame:
    """行业分类（带本地缓存）。"""
    path = CN_DATA_DIR / "industry.feather"
    if path.exists():
        return pd.read_feather(path)
    login = bs.login()
    if login.error_code != "0":
        raise RuntimeError(f"baostock 登录失败: {login.error_msg}")
    try:
        frame = fetch_industry()
    finally:
        bs.logout()
    CN_DATA_DIR.mkdir(parents=True, exist_ok=True)
    frame.to_feather(path)
    return frame


def load_cn_daily() -> dict[str, pd.DataFrame]:
    out = {}
    for name in ("close", "volume"):
        df = pd.read_feather(CN_DATA_DIR / f"{name}.feather")
        out[name] = df.set_index(df.columns[0])
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="下载沪深 300 日频数据（baostock）")
    parser.add_argument("--years", type=int, default=10)
    parser.add_argument("--refresh", action="store_true",
                        help="删除现有行情后全量重下（月度更新用）")
    args = parser.parse_args()
    if args.refresh:
        for name in ("close.feather", "volume.feather"):
            (CN_DATA_DIR / name).unlink(missing_ok=True)
        print("已清除现有行情缓存（--refresh）", flush=True)
    login = bs.login()
    if login.error_code != "0":
        print(f"baostock 登录失败: {login.error_msg}")
        return 1
    try:
        month_ends = pd.date_range(end=date.today(), periods=args.years * 12, freq="ME")
        print(f"抓取点时成分: {len(month_ends)} 个月末快照 ...", flush=True)
        membership = fetch_hs300_membership(month_ends)
        CN_DATA_DIR.mkdir(parents=True, exist_ok=True)
        membership.to_feather(CN_DATA_DIR / "membership.feather")
        tickers = sorted(membership["ticker"].unique())
        print(f"股池: 点时成分并集 {len(tickers)} 个标的"
              f"（{len(month_ends)} 期快照，消除'未来入选'泄漏）", flush=True)
        download_cn_daily(tickers, years=args.years)
    finally:
        bs.logout()
    close = load_cn_daily()["close"]
    print(f"[OK] {close.shape[0]} 个交易日 × {close.shape[1]} 标的 | "
          f"{close.index[0]:%Y-%m-%d} ~ {close.index[-1]:%Y-%m-%d} | "
          f"覆盖率 {close.notna().mean().mean():.1%}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
