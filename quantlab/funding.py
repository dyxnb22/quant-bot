"""永续合约资金费率数据：拉取（Binance Vision 归档 + OKX 尾部）与 K 线对齐。

- Binance Vision 月度归档从 2023-01 起完整（静态文件，不受 API 地区限制）
- OKX 费率 API 仅保留约 3 个月（实测），只用于补最近尾部
- 对齐语义：K 线时刻只能看到"最近一次已结算"的费率（merge_asof backward，
  结构性无未来函数，由 tests/test_funding.py 锁死）
"""

import argparse
import csv
import io
import json
import sys
import time
import urllib.error
import urllib.request
import zipfile
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd

from quantlab.strategy_loader import PROJECT_DIR

FUNDING_DIR = PROJECT_DIR / "user_data" / "data" / "funding"
PAIRS = ("BTC/USDT", "ETH/USDT", "SOL/USDT", "XRP/USDT")
START_MONTH = (2023, 1)
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}
BINANCE_URL = ("https://data.binance.vision/data/futures/um/monthly/fundingRate/"
               "{symbol}/{symbol}-fundingRate-{year}-{month:02d}.zip")
OKX_URL = ("https://www.okx.com/api/v5/public/funding-rate-history"
           "?instId={inst}&limit=100{after}")


def attach_funding(candles: pd.DataFrame, funding: pd.DataFrame) -> pd.DataFrame:
    """为 K 线附加最近一次已结算的资金费率（backward 合并，无未来函数）。"""
    return pd.merge_asof(
        candles.sort_values("date"),
        funding[["date", "funding_rate"]].sort_values("date"),
        on="date", direction="backward",
    )


def funding_file(pair: str) -> Path:
    return FUNDING_DIR / f"{pair.replace('/', '_')}-funding.feather"


def _months(start: tuple, end: tuple):
    y, m = start
    while (y, m) <= end:
        yield y, m
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)


def _get(url: str, retries: int = 3) -> bytes:
    """带退避重试的 GET（代理链路偶发 SSL 断连，重试是数据管道标配）。"""
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(
                    urllib.request.Request(url, headers=UA), timeout=30) as response:
                return response.read()
        except urllib.error.HTTPError:
            raise  # HTTP 状态码错误交给调用方（如 404）
        except (urllib.error.URLError, OSError):
            if attempt == retries - 1:
                raise
            time.sleep(2 * (attempt + 1))
    raise RuntimeError("unreachable")


def fetch_binance_month(symbol: str, year: int, month: int) -> pd.DataFrame:
    url = BINANCE_URL.format(symbol=symbol, year=year, month=month)
    try:
        payload = _get(url)
    except urllib.error.HTTPError as error:
        if error.code == 404:  # 该月归档缺失（如标的尚未上市）
            return pd.DataFrame(columns=["date", "funding_rate"])
        raise
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        with archive.open(archive.namelist()[0]) as fh:
            rows = list(csv.DictReader(io.TextIOWrapper(fh)))
    return pd.DataFrame({
        "date": pd.to_datetime([int(r["calc_time"]) for r in rows], unit="ms", utc=True),
        "funding_rate": [float(r["last_funding_rate"]) for r in rows],
    })


def fetch_okx_recent(pair: str) -> pd.DataFrame:
    """OKX 近 3 个月费率（补 Binance 月度归档之后的尾部）。"""
    inst = pair.replace("/", "-") + "-SWAP"
    frames, after = [], ""
    for _ in range(30):
        url = OKX_URL.format(inst=inst, after=after)
        rows = json.loads(_get(url)).get("data", [])
        if not rows:
            break
        frames.append(pd.DataFrame({
            "date": pd.to_datetime([int(r["fundingTime"]) for r in rows], unit="ms", utc=True),
            "funding_rate": [float(r["fundingRate"]) for r in rows],
        }))
        after = f"&after={min(int(r['fundingTime']) for r in rows)}"
        time.sleep(0.3)
    if not frames:
        return pd.DataFrame(columns=["date", "funding_rate"])
    return pd.concat(frames, ignore_index=True)


def download_funding(pair: str) -> Path:
    symbol = pair.replace("/", "")
    today = date.today()
    # 最新完整月 = 上个月
    end = (today.year, today.month - 1) if today.month > 1 else (today.year - 1, 12)
    frames = []
    for year, month in _months(START_MONTH, end):
        frames.append(fetch_binance_month(symbol, year, month))
        time.sleep(0.15)
    frames.append(fetch_okx_recent(pair))
    merged = (pd.concat(frames, ignore_index=True)
              .drop_duplicates(subset="date").sort_values("date").reset_index(drop=True))
    FUNDING_DIR.mkdir(parents=True, exist_ok=True)
    target = funding_file(pair)
    merged.to_feather(target)
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description="下载永续资金费率历史")
    parser.add_argument("--pairs", nargs="*", default=list(PAIRS))
    args = parser.parse_args()
    for pair in args.pairs:
        target = download_funding(pair)
        df = pd.read_feather(target)
        age_hours = (datetime.now(timezone.utc) - df["date"].iloc[-1]).total_seconds() / 3600
        print(f"[OK] {pair}: {len(df)} 条 | {df['date'].iloc[0]:%Y-%m-%d} ~ "
              f"{df['date'].iloc[-1]:%Y-%m-%d %H:%M} | 尾部距今 {age_hours:.1f}h | {target.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
