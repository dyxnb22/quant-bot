"""美股日频数据管道：S&P 500 股池 + yfinance 批量下载 + feather 落地。

已知限制（如实记录，见路线图 D5）：股池为当前成分（幸存者偏差——
已退市/被剔除的标的不在池中，回测收益会系统性偏乐观），
点时化股池与退市标的处理列入后续。
"""

import argparse
import csv
import io
import sys
import time
from pathlib import Path

import pandas as pd
import yfinance as yf

from quantlab.funding import _get
from quantlab.strategy_loader import PROJECT_DIR

US_DATA_DIR = PROJECT_DIR / "user_data" / "data" / "us"
CONSTITUENTS_URL = ("https://raw.githubusercontent.com/datasets/s-and-p-500-companies/"
                    "main/data/constituents.csv")
PIT_URL = ("https://raw.githubusercontent.com/fja05680/sp500/master/"
           "sp500_ticker_start_end.csv")
CHUNK_SIZE = 50


def fetch_sp500_tickers() -> list[str]:
    """S&P 500 当前成分（开源数据集仓库，yfinance 符号格式：. → -）。"""
    rows = list(csv.DictReader(io.StringIO(_get(CONSTITUENTS_URL).decode())))
    return sorted(r["Symbol"].replace(".", "-") for r in rows)


def download_us_daily(tickers: list[str], years: int = 4) -> Path:
    closes, volumes = [], []
    for i in range(0, len(tickers), CHUNK_SIZE):
        chunk = tickers[i:i + CHUNK_SIZE]
        for attempt in range(3):
            try:
                data = yf.download(chunk, period=f"{years}y", interval="1d",
                                   auto_adjust=True, progress=False, threads=True)
                break
            except Exception:
                if attempt == 2:
                    raise
                time.sleep(5 * (attempt + 1))
        closes.append(data["Close"])
        volumes.append(data["Volume"])
        print(f"  已下载 {min(i + CHUNK_SIZE, len(tickers))}/{len(tickers)}", flush=True)
        time.sleep(1)
    close = pd.concat(closes, axis=1).copy()
    volume = pd.concat(volumes, axis=1).copy()
    US_DATA_DIR.mkdir(parents=True, exist_ok=True)
    close.reset_index().to_feather(US_DATA_DIR / "close.feather")
    volume.reset_index().to_feather(US_DATA_DIR / "volume.feather")
    return US_DATA_DIR


def _load_pit_table() -> pd.DataFrame:
    """PIT 起止表：本地缓存（进数据指纹），仅缺失时才从上游拉取（P1-12）。"""
    cache = US_DATA_DIR / "pit_start_end.feather"
    if cache.exists():
        return pd.read_feather(cache)
    rows = list(csv.DictReader(io.StringIO(_get(PIT_URL).decode())))
    frame = pd.DataFrame(rows)
    US_DATA_DIR.mkdir(parents=True, exist_ok=True)
    frame.to_feather(cache)
    print(f"  点时起止表已缓存: {cache.name}（{len(frame)} 行）")
    return frame


def pit_membership_mask(dates: pd.DatetimeIndex, tickers) -> pd.DataFrame:
    """点时成员掩码：date × ticker 布尔表，True = 该日期该标的在 S&P 500 内。

    fail-closed（P1-12）：不在起止表中的标的按"全程不在指数内"处理——
    宁可少样本，不引入未来入选泄漏。已知残余偏差：已退市成员价格不可得。
    """
    table = _load_pit_table()
    spells: dict[str, list] = {}
    for _, row in table.iterrows():
        ticker = str(row["ticker"]).replace(".", "-")
        start = pd.Timestamp(row["start_date"])
        end = pd.Timestamp(row["end_date"]) if row["end_date"] else pd.Timestamp("2099-01-01")
        spells.setdefault(ticker, []).append((start, end))
    mask = pd.DataFrame(False, index=dates, columns=list(tickers))
    unknown = 0
    for ticker in mask.columns:
        if ticker not in spells:
            unknown += 1  # fail-closed：保持 False
            continue
        for start, end in spells[ticker]:
            mask.loc[(mask.index >= start) & (mask.index <= end), ticker] = True
    if unknown:
        print(f"  点时掩码: {unknown} 个标的不在起止表中，已按 fail-closed 排除")
    return mask


def load_us_daily() -> dict[str, pd.DataFrame]:
    out = {}
    for name in ("close", "volume"):
        df = pd.read_feather(US_DATA_DIR / f"{name}.feather")
        out[name] = df.set_index(df.columns[0])
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="下载 S&P 500 日频数据")
    parser.add_argument("--years", type=int, default=4)
    parser.add_argument("--limit", type=int, default=0, help="只取前 N 个标的（调试用）")
    args = parser.parse_args()

    tickers = fetch_sp500_tickers()
    if args.limit:
        tickers = tickers[:args.limit]
    print(f"股池: {len(tickers)} 个标的（S&P 500 当前成分，幸存者偏差已知）")
    download_us_daily(tickers, years=args.years)
    close = load_us_daily()["close"]
    coverage = close.notna().mean().mean()
    print(f"[OK] close/volume 已落地 {US_DATA_DIR}")
    print(f"     {close.shape[0]} 个交易日 × {close.shape[1]} 标的 | "
          f"{close.index[0]:%Y-%m-%d} ~ {close.index[-1]:%Y-%m-%d} | 覆盖率 {coverage:.1%}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
