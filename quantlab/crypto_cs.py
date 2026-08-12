"""加密截面数据管道：Binance Vision 日线 → 币种面板（close / 美元成交额）。

宇宙口径（预登记）：种子池 = 当前活跃前 150（含幸存偏差残余，登记册已声明）；
成员资格 = 池内每月末按 60 日美元成交额排名前 80（点时重排）。
"""

import argparse
import csv
import io
import json
import sys
import time
import urllib.error
import zipfile
from datetime import date
from pathlib import Path

import pandas as pd

from quantlab.funding import _get
from quantlab.strategy_loader import PROJECT_DIR

CRYPTO_CS_DIR = PROJECT_DIR / "user_data" / "data" / "crypto_cs"
KLINE_URL = ("https://data.binance.vision/data/spot/monthly/klines/"
             "{symbol}/1d/{symbol}-1d-{year}-{month:02d}.zip")
OKX_TICKERS_URL = "https://www.okx.com/api/v5/market/tickers?instType=SPOT"
SEED_SIZE = 150
TOP_N = 80
START = (2020, 1)


def fetch_seed_symbols() -> list[str]:
    """当前活跃前 SEED_SIZE 的 USDT 币对（OKX 快照排名 → Binance 符号）。"""
    data = json.loads(_get(OKX_TICKERS_URL))["data"]
    usdt = [t for t in data if t["instId"].endswith("-USDT")]
    usdt.sort(key=lambda t: float(t.get("volCcy24h") or 0), reverse=True)
    symbols = []
    for t in usdt[:SEED_SIZE]:
        base = t["instId"].split("-")[0]
        symbols.append(f"{base}USDT")
    return symbols


def _months(start: tuple, end: tuple):
    y, m = start
    while (y, m) <= end:
        yield y, m
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)


def fetch_symbol_daily(symbol: str) -> pd.DataFrame:
    """单币种全历史日线（月度归档拼接；缺失月 404 跳过）。"""
    today = date.today()
    end = (today.year, today.month - 1) if today.month > 1 else (today.year - 1, 12)
    rows = []
    for year, month in _months(START, end):
        url = KLINE_URL.format(symbol=symbol, year=year, month=month)
        try:
            payload = _get(url, retries=2)
        except urllib.error.HTTPError as error:
            if error.code == 404:
                continue
            raise
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            with archive.open(archive.namelist()[0]) as fh:
                for row in csv.reader(io.TextIOWrapper(fh)):
                    # 列: open_time,open,high,low,close,volume,close_time,quote_volume,...
                    rows.append((int(row[0]), float(row[4]), float(row[7])))
        time.sleep(0.05)
    if not rows:
        return pd.DataFrame(columns=["date", "close", "dollar_volume"])
    frame = pd.DataFrame(rows, columns=["ts", "close", "dollar_volume"])
    # open_time 毫秒或微秒（2025 起归档为微秒），按量级判别
    unit = "us" if frame["ts"].iloc[-1] > 10 ** 14 else "ms"
    frame["date"] = pd.to_datetime(frame["ts"], unit=unit).dt.normalize()
    return frame[["date", "close", "dollar_volume"]].drop_duplicates("date")


def download_crypto_cs(symbols: list[str]) -> Path:
    closes, dollars = {}, {}
    state_file = CRYPTO_CS_DIR / "close.feather"
    if state_file.exists():
        existing_close = pd.read_feather(state_file).set_index("date")
        existing_dollar = pd.read_feather(CRYPTO_CS_DIR / "dollar_volume.feather").set_index("date")
        closes = {c: existing_close[c] for c in existing_close.columns}
        dollars = {c: existing_dollar[c] for c in existing_dollar.columns}
        print(f"  断点续传: 已有 {len(closes)} 个币种", flush=True)
    pending = [s for s in symbols if s not in closes]
    failed = []
    for i, symbol in enumerate(pending, 1):
        try:
            frame = fetch_symbol_daily(symbol)
        except Exception:
            failed.append(symbol)
            continue
        if frame.empty:
            failed.append(symbol)
            continue
        series = frame.set_index("date")
        closes[symbol] = series["close"]
        dollars[symbol] = series["dollar_volume"]
        if i % 10 == 0:
            _save(closes, dollars)
            print(f"  已下载 {i}/{len(pending)}（增量已落盘）", flush=True)
    _save(closes, dollars)
    if failed:
        print(f"  无数据/失败 {len(failed)} 个: {failed[:8]}", flush=True)
    return CRYPTO_CS_DIR


def _save(closes: dict, dollars: dict) -> None:
    CRYPTO_CS_DIR.mkdir(parents=True, exist_ok=True)
    (pd.DataFrame(closes).sort_index().reset_index()
     .to_feather(CRYPTO_CS_DIR / "close.feather"))
    (pd.DataFrame(dollars).sort_index().reset_index()
     .to_feather(CRYPTO_CS_DIR / "dollar_volume.feather"))


def load_crypto_cs() -> dict[str, pd.DataFrame]:
    out = {}
    for name in ("close", "dollar_volume"):
        df = pd.read_feather(CRYPTO_CS_DIR / f"{name}.feather")
        out[name] = df.set_index(df.columns[0])
    return out


def crypto_membership_mask(monthly_index, tickers,
                           dollar_daily: pd.DataFrame, top_n: int = TOP_N) -> pd.DataFrame:
    """点时成员：每月末按 60 日美元成交额均值排名前 top_n。"""
    trailing = dollar_daily.rolling(60, min_periods=30).mean()
    trailing_monthly = trailing.resample("ME").last()
    mask = pd.DataFrame(False, index=monthly_index, columns=list(tickers))
    for month_end_date in monthly_index:
        if month_end_date not in trailing_monthly.index:
            continue
        row = trailing_monthly.loc[month_end_date].dropna()
        members = row.nlargest(top_n).index
        mask.loc[month_end_date, [t for t in mask.columns if t in members]] = True
    return mask


def main() -> int:
    parser = argparse.ArgumentParser(description="下载加密截面日线（Binance Vision）")
    parser.parse_args()
    symbols = fetch_seed_symbols()
    print(f"种子池: {len(symbols)} 个币对（当前活跃快照，幸存偏差残余已声明）", flush=True)
    download_crypto_cs(symbols)
    close = load_crypto_cs()["close"]
    print(f"[OK] {close.shape[0]} 个交易日 × {close.shape[1]} 币种 | "
          f"{close.index[0]:%Y-%m-%d} ~ {close.index[-1]:%Y-%m-%d}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
