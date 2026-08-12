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

# E402 豁免原因：超时兜底必须先于 baostock 建连
import baostock as bs  # noqa: E402
import pandas as pd  # noqa: E402

from quantlab.strategy_loader import PROJECT_DIR  # noqa: E402

CN_DATA_DIR = PROJECT_DIR / "user_data" / "data" / "cn"

# 宇宙注册表：中证 500 复用同一管道（字段/点时化/事务与沪深 300 完全一致）
UNIVERSES = {
    "hs300": {"dir": CN_DATA_DIR, "label": "沪深 300", "index": "sh.000300",
              "query": lambda **kw: bs.query_hs300_stocks(**kw), "lock": "cn_data"},
    "zz500": {"dir": PROJECT_DIR / "user_data" / "data" / "cn500", "label": "中证 500",
              "index": "sh.000905",
              "query": lambda **kw: bs.query_zz500_stocks(**kw), "lock": "cn500_data"},
}


def fetch_csi300_tickers() -> list[str]:
    result = bs.query_hs300_stocks()
    tickers = []
    while result.next():
        tickers.append(result.get_row_data()[1])  # 形如 sh.600000
    return sorted(tickers)


def fetch_hs300_membership(month_ends, query=None) -> pd.DataFrame:
    """逐月末抓取点时成分快照（节假日自动回退至最近有效日）。"""
    query = query or UNIVERSES["hs300"]["query"]
    rows = []
    for month_end_date in month_ends:
        for back in range(8):
            query_date = (month_end_date - timedelta(days=back)).strftime("%Y-%m-%d")
            result = query(date=query_date)
            snapshot = []
            while result.next():
                snapshot.append(result.get_row_data()[1])
            if snapshot:
                rows.extend((month_end_date, ticker) for ticker in snapshot)
                break
        else:
            print(f"  成分快照缺失: {month_end_date:%Y-%m-%d}", flush=True)
    return pd.DataFrame(rows, columns=["date", "ticker"])


def cn_membership_mask(monthly_index, tickers, data_dir: Path = CN_DATA_DIR
                       ) -> pd.DataFrame | None:
    """点时成员掩码（date × ticker）：每个月末用最近一期成分快照。"""
    path = data_dir / "membership.feather"
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


# 日频字段：估值比率与换手率天然点时（无财报披露滞后问题）
FIELDS = ("close", "volume", "turn", "pe", "pb", "ps")
QUERY_FIELDS = "date,close,volume,turn,peTTM,pbMRQ,psTTM"


def _save(frames: dict, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for field in FIELDS:
        (pd.DataFrame(frames[field]).sort_index().reset_index()
         .to_feather(out_dir / f"{field}.feather"))


def download_cn_daily(tickers: list[str], years: int = 4,
                      out_dir: Path | None = None) -> Path:
    out_dir = out_dir or CN_DATA_DIR
    start = (date.today() - timedelta(days=365 * years)).isoformat()
    end = date.today().isoformat()
    frames = {field: {} for field in FIELDS}
    if all((out_dir / f"{f}.feather").exists() for f in FIELDS):
        for field in FIELDS:
            df = pd.read_feather(out_dir / f"{field}.feather")
            df = df.set_index(df.columns[0])
            frames[field] = {c: df[c] for c in df.columns}
        print(f"  断点续传: 已有 {len(frames['close'])} 个标的", flush=True)
    pending = [t for t in tickers if t not in frames["close"]]
    failed = []
    for i, ticker in enumerate(pending, 1):
        rows = []
        for attempt in range(3):
            try:
                result = bs.query_history_k_data_plus(
                    ticker, QUERY_FIELDS,
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
        frame = pd.DataFrame(rows, columns=QUERY_FIELDS.split(","))
        frame["date"] = pd.to_datetime(frame["date"])
        frame = frame.set_index("date")
        for field, column in zip(FIELDS, ("close", "volume", "turn", "peTTM", "pbMRQ", "psTTM")):
            frames[field][ticker] = pd.to_numeric(frame[column], errors="coerce")
        if i % 25 == 0:
            _save(frames, out_dir)
            print(f"  已下载 {i}/{len(pending)}（增量已落盘）", flush=True)
        time.sleep(0.4)  # 礼貌间隔：降低触发服务端限流的概率（2026-08-12 实测被限速）
    _save(frames, out_dir)
    if failed:
        print(f"  下载失败 {len(failed)} 个: {failed[:10]}", flush=True)
    return out_dir


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
    atomic_write_feather(frame, path)
    return frame


def fetch_index(years: int, code: str = "sh.000300",
                out_dir: Path = CN_DATA_DIR) -> None:
    """价格指数日线（基准列；注明不含股息的局限）。调用方负责 login。"""
    start = (date.today() - timedelta(days=365 * years)).isoformat()
    result = bs.query_history_k_data_plus(
        code, "date,close", start_date=start, end_date=date.today().isoformat(),
        frequency="d")
    rows = []
    while result.next():
        rows.append(result.get_row_data())
    frame = pd.DataFrame(rows, columns=["date", "close"])
    frame["date"] = pd.to_datetime(frame["date"])
    frame["close"] = pd.to_numeric(frame["close"], errors="coerce")
    atomic_write_feather(frame, out_dir / "index.feather")
    print(f"指数基准: {code} {len(frame)} 个交易日已落盘", flush=True)


def load_index(data_dir: Path = CN_DATA_DIR) -> pd.Series | None:
    path = data_dir / "index.feather"
    if not path.exists():
        return None
    frame = pd.read_feather(path)
    return frame.set_index("date")["close"]


def load_cn_daily(data_dir: Path = CN_DATA_DIR) -> dict[str, pd.DataFrame]:
    out = {}
    for name in FIELDS:
        path = data_dir / f"{name}.feather"
        if path.exists():
            df = pd.read_feather(path)
            out[name] = df.set_index(df.columns[0])
    return out


def atomic_write_feather(frame: pd.DataFrame, target: Path) -> None:
    """单文件原子写：临时文件 + os.replace。"""
    import os
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_suffix(".tmp.feather")
    frame.to_feather(temp)
    os.replace(temp, target)


def main() -> int:
    from quantlab.locking import file_lock

    parser = argparse.ArgumentParser(description="下载 A 股日频数据（baostock）")
    parser.add_argument("--years", type=int, default=10)
    parser.add_argument("--universe", choices=list(UNIVERSES), default="hs300")
    parser.add_argument("--refresh", action="store_true",
                        help="清空 staging 全量重下（否则断点续传 staging）")
    args = parser.parse_args()
    universe = UNIVERSES[args.universe]
    data_dir = universe["dir"]
    staging = data_dir / "staging"
    # P0 修复：live 目录只接受"校验通过后的原子切换"，下载一律写 staging。
    # 断点续传也发生在 staging；staging 为空且 live 完整时以 live 为种子（拷贝）。
    if args.refresh:
        for name in FIELDS:
            (staging / f"{name}.feather").unlink(missing_ok=True)
        print("已清空 staging（--refresh 全量重下）", flush=True)

    login = bs.login()
    if login.error_code != "0":
        print(f"baostock 登录失败: {login.error_msg}")
        return 1
    try:
        with file_lock(universe["lock"]):
            membership_file = data_dir / "membership.feather"
            if membership_file.exists() and not args.refresh:
                membership = pd.read_feather(membership_file)
                print(f"点时成分使用缓存（{membership['date'].nunique()} 期快照）", flush=True)
            else:
                month_ends = pd.date_range(end=date.today(), periods=args.years * 12, freq="ME")
                print(f"抓取 {universe['label']} 点时成分: {len(month_ends)} 个月末快照 ...",
                      flush=True)
                membership = fetch_hs300_membership(month_ends, query=universe["query"])
                atomic_write_feather(membership, membership_file)
            tickers = sorted(membership["ticker"].unique())
            print(f"股池: {universe['label']} 点时成分并集 {len(tickers)} 个标的", flush=True)
            fetch_index(args.years, code=universe["index"], out_dir=data_dir)

            staging.mkdir(parents=True, exist_ok=True)
            if (not (staging / "close.feather").exists()
                    and all((data_dir / f"{f}.feather").exists() for f in FIELDS)):
                import shutil
                for name in FIELDS:
                    shutil.copy(data_dir / f"{name}.feather", staging / f"{name}.feather")
                print("staging 以 live 数据为种子（增量补齐）", flush=True)
            download_cn_daily(tickers, years=args.years, out_dir=staging)

            staged = pd.read_feather(staging / "close.feather")
            coverage = (staged.shape[1] - 1) / len(tickers)
            if coverage < 0.9:
                print(f"校验未过：staging 覆盖率 {coverage:.0%} < 90%，"
                      f"live 数据保持不变（下次运行自动续传 staging）")
                return 1
            import os
            for name in FIELDS:
                os.replace(staging / f"{name}.feather", data_dir / f"{name}.feather")
            staging.rmdir()
            print(f"校验通过（覆盖率 {coverage:.0%}），已原子切换 live", flush=True)
    finally:
        bs.logout()
    close = load_cn_daily(data_dir)["close"]
    print(f"[OK] {close.shape[0]} 个交易日 × {close.shape[1]} 标的 | "
          f"{close.index[0]:%Y-%m-%d} ~ {close.index[-1]:%Y-%m-%d} | "
          f"覆盖率 {close.notna().mean().mean():.1%}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
