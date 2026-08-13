"""每日一键巡检（make daily）：读实时数据核对系统状态，结果落两处文档。

- 日检日志 `docs/research/daily-log.md`：每次运行追加一节（检查表 + 关键数字）
- 运行台账 `docs/research/run-registry.md`：追加一行（何时启动、结果、产物在哪）；
  台账开头的「脚本与产物地图」静态维护，列出所有脚本的启动方式与数据去向。

设计约束：只读观察，不做任何交易/参数动作；单项失败不中断其余检查。
"""

import argparse
import subprocess
import sys
from datetime import datetime

from quantlab.strategy_loader import PROJECT_DIR

DAILY_LOG = PROJECT_DIR / "docs" / "research" / "daily-log.md"
RUN_REGISTRY = PROJECT_DIR / "docs" / "research" / "run-registry.md"
RECON_MIN_SAMPLE = 30
G5_REQUIRED = 12

# 一次性/间歇 launchd 任务：在册期间必须被日检盯住（防多晚续传静默失败）
# exit 75 = 限流检查点退出（预期内，等下次定时续传）
TRANSIENT_JOBS = {
    "com.quantbot.cnfundamentals": ("A股财报下载", "user_data/logs/cn_fundamentals.log"),
    "com.quantbot.cnroeeval": ("ROE自动评估", "user_data/logs/cn_roe_eval.log"),
    "com.quantbot.cndownload": ("A股行情深夜下载", "user_data/logs/cn_download.log"),
}
EXPECTED_EXIT_CODES = ("0", "75")

DAILY_LOG_HEADER = """# 日检日志（make daily 自动追加）

每天启动一次 `make daily`：增量更新币市数据 → 巡检模拟盘与数据面板 → 追加一节记录。
字段含义与各脚本的产物位置见 `docs/research/run-registry.md`。

---
"""


def _check_bot_health() -> tuple[bool, str]:
    from quantlab.health import (check_api_running, check_log_fresh,
                                 check_process, check_service, load_env)
    parts = []
    ok = True
    for name, check in (("launchd", check_service), ("进程", check_process),
                        ("日志心跳", check_log_fresh)):
        try:
            good = check()
        except Exception:
            good = False
        ok = ok and good
        parts.append(f"{name}{'✓' if good else '✗'}")
    try:
        api = check_api_running(load_env())
    except Exception:
        api = False
    ok = ok and api
    parts.append(f"API{'✓' if api else '✗'}")
    return ok, " ".join(parts)


def _check_paper_account() -> tuple[bool, str]:
    from quantlab.daily_brief import _api_get
    from quantlab.health import load_env
    try:
        env = load_env()
        profit = _api_get("/profit", env)
        open_trades = _api_get("/status", env)
    except Exception as error:
        return False, f"API 读取失败: {error}"
    closed = profit.get("closed_trade_count", 0)
    detail = (f"平仓 {closed} 笔 | 已实现 {profit.get('profit_closed_coin', 0):+.2f} USDT | "
              f"胜率 {profit.get('winrate', 0) * 100:.0f}% | "
              f"最大回撤 {profit.get('max_drawdown', 0) * 100:.2f}% | "
              f"持仓 {len(open_trades)} 笔 | 对账样本 {closed}/{RECON_MIN_SAMPLE}")
    return True, detail


def _check_data_quality() -> tuple[bool, str]:
    result = subprocess.run(
        [str(PROJECT_DIR / ".venv" / "bin" / "python"), "-m", "quantlab.data_quality"],
        capture_output=True, text=True, cwd=PROJECT_DIR)
    lines = [ln for ln in result.stdout.splitlines() if ln.strip()]
    fails = [ln for ln in lines if ln.startswith("[FAIL")]
    summary = (f"{len(lines)} 项全部通过" if result.returncode == 0
               else "；".join(fails[:3]) or "失败（详见 make data-check）")
    return result.returncode == 0, summary


def _check_forward_ledger() -> tuple[bool, str]:
    from quantlab.deployment_gate import FREEZE_DATE, RULES
    from quantlab.forward_ledger import forward_months
    freeze_iso = f"{FREEZE_DATE:%Y-%m-%d}T00:00:00+00:00"
    parts = [f"{rule} {forward_months(freeze_iso, rule=rule)}/{G5_REQUIRED}"
             for rule in RULES]
    return True, "G5 前向进度：" + "，".join(parts)


def parse_launchctl(text: str) -> dict[str, tuple[str, str]]:
    """launchctl list 输出 → {label: (pid, last_exit_code)}；pid 为 '-' 表示未在运行。"""
    jobs = {}
    for line in text.splitlines():
        parts = line.split()
        if len(parts) == 3 and parts[2].startswith("com.quantbot."):
            jobs[parts[2]] = (parts[0], parts[1])
    return jobs


def _log_progress(log_path) -> str:
    """日志尾部最近一条进度/结果行（供台账速读）。"""
    if not log_path.exists():
        return ""
    for line in reversed(log_path.read_text().splitlines()[-60:]):
        if any(key in line for key in ("已落盘", "限流", "报告:", "覆盖率")):
            return line.strip()[:80]
    return ""


def _check_transient_jobs() -> tuple[bool, str]:
    result = subprocess.run(["launchctl", "list"], capture_output=True, text=True)
    jobs = parse_launchctl(result.stdout)
    ok, parts = True, []
    for label, (name, log) in TRANSIENT_JOBS.items():
        if label not in jobs:
            continue  # 未安装，或已完成并自卸载
        pid, code = jobs[label]
        running = pid != "-"
        good = running or code in EXPECTED_EXIT_CODES
        ok = ok and good
        state = "运行中" if running else f"待定时（上次退出码 {code}）"
        progress = _log_progress(PROJECT_DIR / log)
        parts.append(f"{name}: {state}" + (f"，{progress}" if progress else ""))
    if not parts:
        return True, "无在册临时任务（均已完成并自卸载）"
    return ok, " | ".join(parts)


def _update_crypto_data() -> tuple[bool, str]:
    result = subprocess.run(["./scripts/download_data.sh"], capture_output=True,
                            text=True, cwd=PROJECT_DIR, timeout=900)
    return result.returncode == 0, ("增量更新完成" if result.returncode == 0
                                    else f"下载失败（退出码 {result.returncode}）")


def run_checks(update_data: bool) -> list[dict]:
    steps = []
    if update_data:
        steps.append(("币市数据增量更新", _update_crypto_data))
    steps += [
        ("模拟盘健康（服务/进程/心跳/API）", _check_bot_health),
        ("模拟盘账面（实时 API）", _check_paper_account),
        ("数据质量（币市 K 线 + 股市面板）", _check_data_quality),
        ("前向账本（三候选 G5 进度）", _check_forward_ledger),
        ("临时任务（深夜下载/自动评估）", _check_transient_jobs),
    ]
    rows = []
    for name, step in steps:
        try:
            ok, detail = step()
        except Exception as error:
            ok, detail = False, f"执行异常: {error}"
        rows.append({"name": name, "ok": ok, "detail": detail})
        print(f"[{'OK ' if ok else 'FAIL'}] {name}: {detail}", flush=True)
    return rows


def append_daily_log(rows: list[dict], stamp_text: str) -> str:
    now = datetime.now()
    anchor = f"{now:%Y-%m-%d %H:%M}"
    passed = sum(r["ok"] for r in rows)
    lines = [f"## {anchor}", "",
             "| 检查 | 结果 | 详情 |", "|---|---|---|"]
    for r in rows:
        lines.append(f"| {r['name']} | {'✓' if r['ok'] else '✗ FAIL'} | {r['detail']} |")
    lines += ["", f"结论：{passed}/{len(rows)} 通过。溯源: {stamp_text}", ""]
    if not DAILY_LOG.exists():
        DAILY_LOG.write_text(DAILY_LOG_HEADER)
    with DAILY_LOG.open("a") as fh:
        fh.write("\n".join(lines) + "\n")
    return anchor


def append_run_registry(anchor: str, rows: list[dict]) -> None:
    passed = sum(r["ok"] for r in rows)
    row = (f"| {anchor} | make daily | {passed}/{len(rows)} 通过 "
           f"| `docs/research/daily-log.md` § {anchor} |\n")
    with RUN_REGISTRY.open("a") as fh:
        fh.write(row)


def main() -> int:
    parser = argparse.ArgumentParser(description="每日一键巡检（只读观察）")
    parser.add_argument("--no-data-update", action="store_true",
                        help="跳过币市数据增量更新（离线或赶时间时用）")
    args = parser.parse_args()

    from quantlab.provenance import stamp
    rows = run_checks(update_data=not args.no_data_update)
    anchor = append_daily_log(rows, stamp())
    if not RUN_REGISTRY.exists():
        print(f"警告：运行台账缺失（{RUN_REGISTRY}），跳过台账登记", flush=True)
    else:
        append_run_registry(anchor, rows)
    passed = sum(r["ok"] for r in rows)
    print(f"\n日检完成：{passed}/{len(rows)} 通过")
    print(f"日志: {DAILY_LOG}")
    print(f"台账: {RUN_REGISTRY}")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    sys.exit(main())
