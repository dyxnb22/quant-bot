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
