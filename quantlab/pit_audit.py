"""点时可信度审计：公告日/申报日的规则一致性检查——数据源信任不再默认。

整条 PIT 链建立在"pubDate/filed 是真实可用日"之上（第三轮审计第 5 项）。
无法访问交易所原始公告存档时，用规则审计兜底：
- 硬违规（任何 >0 都动摇 PIT 保证）：公告日早于报告期结束（信息未来泄漏的方向）
- 软警示：公告滞后异常（迟于监管窗口/中位数异常）、同报告期多版本（更正公告占比）

产物：docs/results/23-pit-audit.md（每次财报数据刷新后重跑）。
"""

import sys
from datetime import datetime

import pandas as pd

from quantlab.strategy_loader import PROJECT_DIR

REPORT = PROJECT_DIR / "docs" / "results" / "23-pit-audit.md"
CN_LATE_DAYS = 120   # A 股监管窗口：季报 1 个月/年报 4 个月，>120 天记异常
US_LATE_DAYS = 90    # 10-Q 40-45 天 / 10-K 60-90 天，>90 天记异常


def audit_cn(records: pd.DataFrame) -> dict:
    """A 股财报记录审计（ticker/stat_date/pub_date/roe）。"""
    rows = records.dropna(subset=["pub_date", "stat_date"]).copy()
    lag = (rows["pub_date"] - rows["stat_date"]).dt.days
    duplicates = rows.duplicated(["ticker", "stat_date"], keep=False)
    return {
        "records": len(rows),
        "violations": int((lag < 0).sum()),          # 公告早于期末 = 硬违规
        "same_day": int((lag == 0).sum()),           # 期末当日公告，可疑
        "late": int((lag > CN_LATE_DAYS).sum()),
        "lag_median": float(lag.median()) if len(lag) else float("nan"),
        "lag_p95": float(lag.quantile(0.95)) if len(lag) else float("nan"),
        "corrections": int(duplicates.sum()),
    }


def audit_us(records: pd.DataFrame) -> dict:
    """EDGAR 记录审计（kind=ni/eq，end/filed）。

    滞后按每个报告期的**首次**申报计算：年报/季报会把往年同期数作为对比值
    重复申报（同 end、更晚 filed），那是正常结构而非迟披露；
    面板构建（roe_events）同理只认首次出现的值。硬违规检查覆盖全部行。
    """
    rows = records[records["kind"].isin(["ni", "eq"])].dropna(
        subset=["end", "filed"]).copy()
    rows["filed_dt"] = pd.to_datetime(rows["filed"])
    rows["end_dt"] = pd.to_datetime(rows["end"])
    all_lag = (rows["filed_dt"] - rows["end_dt"]).dt.days
    first = rows.groupby(["ticker", "kind", "end_dt"])["filed_dt"].min()
    first_lag = (first - first.index.get_level_values("end_dt")).dt.days
    return {
        "records": len(rows),
        "violations": int((all_lag < 0).sum()),
        "same_day": int((first_lag == 0).sum()),
        "late": int((first_lag > US_LATE_DAYS).sum()),
        "lag_median": float(first_lag.median()) if len(first_lag) else float("nan"),
        "lag_p95": float(first_lag.quantile(0.95)) if len(first_lag) else float("nan"),
        "corrections": 0,  # 10-K/A 等更正申报不在最小记录集内，如实标注
    }


def render(sections: list[tuple[str, dict, int]]) -> str:
    lines = [
        "# 点时可信度审计（pubDate / filed 规则检查）",
        "",
        f"- 日期: {datetime.now():%F %T} | 触发: 财报数据刷新后例行",
        "- 判据：公告/申报日早于报告期末 = **硬违规**（0 容忍）；滞后异常与更正占比 = 软警示",
        "",
        "| 数据域 | 记录数 | 硬违规 | 期末当日 | 迟披露 | 滞后中位(天) | 滞后 p95 | 同期多版本 | 判定 |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for name, audit, late_limit in sections:
        ok = audit["violations"] == 0
        lines.append(
            f"| {name} | {audit['records']} | {audit['violations']} "
            f"| {audit['same_day']} | {audit['late']}（>{late_limit}d） "
            f"| {audit['lag_median']:.0f} | {audit['lag_p95']:.0f} "
            f"| {audit['corrections']} | {'PASS' if ok else '**FAIL**'} |")
    lines += [
        "",
        "解读：",
        "- 硬违规 >0 时该数据域的全部点时结论必须重审（公告日早于期末意味着信息集穿越）。",
        "- 同期多版本（更正公告）由面板构建规则处理（取公告日最新一条），占比高则提示",
        "  数据源可能用更正值回填原公告日——本审计无法直接检出该情形，如实声明为残余风险。",
        "- 期末当日公告在 A 股极罕见（业绩快报除外），占比异常时怀疑数据源日期字段混淆。",
    ]
    return "\n".join(lines)


def main() -> int:
    from quantlab.cn_data import UNIVERSES
    from quantlab.cn_fundamentals import fundamentals_path
    from quantlab.us_fundamentals import FUNDAMENTALS_FILE as US_FILE

    sections = []
    for key in ("hs300", "zz500"):
        path = fundamentals_path(UNIVERSES[key]["dir"])
        if path.exists():
            audit = audit_cn(pd.read_feather(path))
            sections.append((f"A股 {key}（baostock pubDate）", audit, CN_LATE_DAYS))
    if US_FILE.exists():
        sections.append(("美股 S&P500（EDGAR filed）",
                         audit_us(pd.read_feather(US_FILE)), US_LATE_DAYS))
    if not sections:
        print("无财报数据可审计")
        return 1

    from quantlab.provenance import stamp
    report = render(sections) + f"\n\n---\n溯源: {stamp()}\n"
    REPORT.write_text(report)
    print(report)
    print(f"报告: {REPORT}")
    return 0 if all(a["violations"] == 0 for _, a, _ in sections) else 1


if __name__ == "__main__":
    sys.exit(main())
