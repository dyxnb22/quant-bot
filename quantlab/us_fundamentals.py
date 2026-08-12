"""美股基本面点时管道：SEC EDGAR companyfacts → 季度净利润/股东权益 → PIT ROE 日频面板。

点时纪律（与 CN pubDate 同理）：任何数值只在其 `filed`（申报日）之后可见；
TTM 净利润 = 最近 4 个季度和（10-K 年度值减去三个已知季度推导 Q4）；
面板前向填充上限 130 个交易日（约两季，防退市/停报后的僵尸数值）。

声明的简化（登记册同步）：使用最终报告值但从最早申报日起生效——重述（restatement）
的影响未建模；us-gaap 标签缺失的公司如实缺值（fail-visible，不猜代理标签）。
"""

import json
import socket
import sys
import time
import urllib.request
from datetime import timedelta

import pandas as pd

from quantlab.strategy_loader import PROJECT_DIR

# SSL 读僵死兜底（2026-08-12 实测：代理静默导致单请求挂起 8 分钟+）
socket.setdefaulttimeout(30)

US_DATA_DIR = PROJECT_DIR / "user_data" / "data" / "us"
FUNDAMENTALS_FILE = US_DATA_DIR / "fundamentals.feather"
# SEC 要求可联系的 UA；含 "localhost" 的联系方式会被 403（2026-08-12 实测）
USER_AGENT = "quantlab research diaoyuxuan@example.com"
TICKER_MAP_URL = "https://www.sec.gov/files/company_tickers.json"
FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
FFILL_LIMIT_DAYS = 130          # 交易日，约两个季度
QUARTER_DAYS = (70, 100)        # 季度报告期时长窗口
ANNUAL_DAYS = (340, 380)


# 直连绕过本地代理：代理在持续请求下会 SSL EOF 后僵死（2026-08-12 实测两次卡死）
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _fetch_json(url: str, retries: int = 2) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    for attempt in range(retries + 1):
        try:
            with _OPENER.open(request, timeout=30) as response:
                return json.load(response)
        except Exception:
            if attempt == retries:
                raise
            time.sleep(2 * (attempt + 1))


def ticker_cik_map() -> dict[str, int]:
    raw = _fetch_json(TICKER_MAP_URL)
    return {row["ticker"]: int(row["cik_str"]) for row in raw.values()}


def extract_records(facts: dict, ticker: str) -> list[dict]:
    """companyfacts JSON → 最小记录集（NI 期间值 / 权益时点值）。"""
    gaap = facts.get("facts", {}).get("us-gaap", {})
    records = []
    for tag, kind in (("NetIncomeLoss", "ni"), ("StockholdersEquity", "eq")):
        for entry in gaap.get(tag, {}).get("units", {}).get("USD", []):
            if entry.get("form") not in ("10-Q", "10-K") or entry.get("val") is None:
                continue
            if not entry.get("end") or not entry.get("filed"):
                continue
            records.append({
                "ticker": ticker, "kind": kind,
                "start": entry.get("start"), "end": entry["end"],
                "filed": entry["filed"], "val": float(entry["val"]),
            })
    return records


def download_us_fundamentals(tickers: list[str], sleep_s: float = 0.15) -> pd.DataFrame:
    """按 SEC 限速逐 CIK 拉取，只留所需记录。

    断点续传：每 25 个标的原子落盘一次；零数据标的写哨兵行（kind="none"）
    避免重查。重跑即从上次检查点继续。
    """
    cik = ticker_cik_map()
    existing = pd.read_feather(FUNDAMENTALS_FILE) if FUNDAMENTALS_FILE.exists() \
        else pd.DataFrame(columns=["ticker", "kind", "start", "end", "filed", "val"])
    done = set(existing["ticker"])
    pending = [t for t in tickers if t not in done]
    if done:
        print(f"  断点续传：已有 {len(done)} 个标的", flush=True)

    def checkpoint(frame: pd.DataFrame) -> None:
        staging = FUNDAMENTALS_FILE.with_suffix(".staging.feather")
        frame.to_feather(staging)
        staging.replace(FUNDAMENTALS_FILE)

    buffer, missing = [], []
    for i, ticker in enumerate(pending, 1):
        rows = []
        if ticker in cik:
            try:
                facts = _fetch_json(FACTS_URL.format(cik=cik[ticker]))
                rows = extract_records(facts, ticker)
            except Exception as error:
                print(f"  {ticker}: 拉取失败 {error}", flush=True)
        if not rows:
            missing.append(ticker)
            rows = [{"ticker": ticker, "kind": "none", "start": None,
                     "end": None, "filed": None, "val": float("nan")}]
        buffer.extend(rows)
        if i % 25 == 0 or i == len(pending):
            existing = pd.concat([existing, pd.DataFrame(buffer)], ignore_index=True)
            buffer = []
            checkpoint(existing)
            print(f"  进度 {i}/{len(pending)}（本轮缺失 {len(missing)}，已检查点）",
                  flush=True)
        time.sleep(sleep_s)
    got = existing[existing["kind"] != "none"]
    print(f"落地 {FUNDAMENTALS_FILE}：{len(got)} 条记录，"
          f"{got['ticker'].nunique()} 标的；无数据哨兵 "
          f"{existing['ticker'].nunique() - got['ticker'].nunique()} 个")
    return existing


def _duration_days(row) -> float:
    if not row["start"]:
        return float("nan")
    return (pd.Timestamp(row["end"]) - pd.Timestamp(row["start"])).days


def roe_events(records: pd.DataFrame) -> list[tuple[pd.Timestamp, float]]:
    """单标的记录 → 按申报日排序的 (filed, ROE_TTM) 事件流（点时游走）。

    每个申报事件后：季度 NI 池更新（年度值在其三个季度已知时推导 Q4），
    有 ≥4 个相邻季度即计算 TTM，除以最近权益时点值。
    """
    records = records.copy()
    records["dur"] = records.apply(_duration_days, axis=1)
    records = records.sort_values("filed")

    quarterly: dict[str, float] = {}      # end → 季度 NI
    annuals: list[dict] = []              # 待推导 Q4 的年度条目
    equity: dict[str, float] = {}         # end → 权益
    events = []
    for _, row in records.iterrows():
        if row["kind"] == "eq":
            equity[row["end"]] = row["val"]
        elif QUARTER_DAYS[0] <= row["dur"] <= QUARTER_DAYS[1]:
            quarterly.setdefault(row["end"], row["val"])
        elif ANNUAL_DAYS[0] <= row["dur"] <= ANNUAL_DAYS[1]:
            annuals.append(dict(row))
        # 年度条目：其窗口内已有 3 个季度 → 推导第 4 季（通常是 Q4）
        for annual in annuals:
            inside = {e: v for e, v in quarterly.items()
                      if annual["start"] < e < annual["end"]}
            if len(inside) == 3 and annual["end"] not in quarterly:
                quarterly[annual["end"]] = annual["val"] - sum(inside.values())
        if len(quarterly) < 4 or not equity:
            continue
        ends = sorted(quarterly)
        last4 = ends[-4:]
        # 4 个季度必须相邻（跨度 ≤ 400 天），防长期停报后的拼接
        if (pd.Timestamp(last4[-1]) - pd.Timestamp(last4[0])).days > 320:
            continue
        ttm = sum(quarterly[e] for e in last4)
        latest_equity = equity[max(equity)]
        if latest_equity and latest_equity > 0:
            events.append((pd.Timestamp(row["filed"]), ttm / latest_equity))
    # 同一申报日的多条记录（NI+权益同日到达）只留最终状态
    deduped = {filed: value for filed, value in events}
    return sorted(deduped.items())


def build_roe_panel(daily_index: pd.DatetimeIndex,
                    records: pd.DataFrame) -> pd.DataFrame:
    """全部标的 → 日频 PIT ROE 面板（filed 日起生效，ffill 限 130 交易日）。"""
    columns = {}
    for ticker, group in records.groupby("ticker"):
        events = roe_events(group)
        if not events:
            continue
        series = pd.Series({filed: value for filed, value in events}).sort_index()
        series = series[~series.index.duplicated(keep="last")]
        # 申报日若非交易日 → 顺延到下一交易日生效
        aligned = series.reindex(
            series.index.union(daily_index)).ffill().reindex(daily_index)
        # 重新应用 ffill 上限：距最近事件超限 → NaN
        last_event = pd.Series(series.index, index=series.index).reindex(
            series.index.union(daily_index)).ffill().reindex(daily_index)
        age_ok = (daily_index - pd.DatetimeIndex(last_event)) <= timedelta(
            days=FFILL_LIMIT_DAYS * 7 // 5)
        columns[ticker] = aligned.where(age_ok)
    return pd.DataFrame(columns, index=daily_index)


def load_roe_panel(daily_index: pd.DatetimeIndex) -> pd.DataFrame:
    if not FUNDAMENTALS_FILE.exists():
        raise FileNotFoundError(f"{FUNDAMENTALS_FILE} 缺失：先运行 make us-fundamentals")
    return build_roe_panel(daily_index, pd.read_feather(FUNDAMENTALS_FILE))


def main() -> int:
    close = pd.read_feather(US_DATA_DIR / "close.feather")
    tickers = [c for c in close.columns if c != close.columns[0]]
    print(f"下载 {len(tickers)} 个标的的 companyfacts（限速 {1 / 0.15:.0f}/s 以内）…")
    download_us_fundamentals(tickers)
    return 0


if __name__ == "__main__":
    sys.exit(main())
