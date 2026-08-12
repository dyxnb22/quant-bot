"""前向账本：append-only JSONL，冻结后前向证据的唯一来源（Gate G5 只读此账本）。

入库提交，git 历史即防篡改时间戳；回填历史月份会在 diff 中一目了然（P1-04 修复）。
"""

import json
from datetime import datetime, timezone

from quantlab.strategy_loader import PROJECT_DIR

LEDGER_FILE = PROJECT_DIR / "docs" / "research" / "cn-momentum" / "forward-ledger.jsonl"


def entries() -> list[dict]:
    if not LEDGER_FILE.exists():
        return []
    return [json.loads(line) for line in LEDGER_FILE.read_text().splitlines() if line.strip()]


def append_entry(month: str, tickers: list[str], note: str = "",
                 rule: str = "momentum") -> bool:
    """按 (月份, 规则) 追加（已存在则跳过，返回 False）。"""
    if any(e["month"] == month and e.get("rule", "momentum") == rule for e in entries()):
        return False
    LEDGER_FILE.parent.mkdir(parents=True, exist_ok=True)
    record = {"month": month, "rule": rule,
              "generated_at": datetime.now(timezone.utc).isoformat(),
              "n": len(tickers), "tickers": sorted(tickers), "note": note}
    with LEDGER_FILE.open("a") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    return True


def forward_months(freeze_iso: str, rule: str = "momentum") -> int:
    """冻结时刻之后、指定规则的账本条目数 = 该候选可主张的前向月度周期数。"""
    return sum(1 for e in entries()
               if e["generated_at"] > freeze_iso and e.get("rule", "momentum") == rule)
