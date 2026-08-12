"""Walk-forward 验证编排器：滚动『样本内优化 → 样本外检验』并汇总报告。

隔离原则：策略副本与参数都在运行专属目录（--strategy-path），
绝不触碰 user_data/strategies/ 下的生产文件——研究不得改变运行中 bot 的行为。
"""

import argparse
import shutil
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

from quantlab.backtest_io import read_backtest_metrics
from quantlab.risk_policy import audit_params
from quantlab.strategy_loader import DEFAULT_STRATEGY_DIR, PROJECT_DIR, load_effective_params
from quantlab.windows import build_windows

FT = PROJECT_DIR / ".venv" / "bin" / "freqtrade"
CONFIG = PROJECT_DIR / "config" / "config.json"
REPORT_TARGET = PROJECT_DIR / "docs" / "results" / "03-walk-forward.md"


def run_freqtrade(args: list[str]) -> None:
    result = subprocess.run([str(FT), *args], cwd=PROJECT_DIR,
                            capture_output=True, text=True)
    if result.returncode != 0:
        sys.stderr.write(result.stdout[-3000:] + result.stderr[-3000:])
        raise RuntimeError(f"freqtrade {args[0]} 失败（参数见上方输出）")


def run_window(index: int, window, strategy: str, strategy_dir: Path,
               out_dir: Path, epochs: int) -> dict:
    (strategy_dir / f"{strategy}.json").unlink(missing_ok=True)  # 每窗口从干净参数开始
    run_freqtrade([
        "hyperopt", "--config", str(CONFIG),
        "--strategy", strategy, "--strategy-path", str(strategy_dir),
        "--hyperopt-loss", "SharpeHyperOptLoss", "--spaces", "buy", "roi", "stoploss",
        "--timerange", window.is_timerange, "-e", str(epochs),
    ])
    params_file = strategy_dir / f"{strategy}.json"
    if params_file.exists():
        shutil.copy(params_file, out_dir / f"window_{index:02d}_params.json")
    else:
        # hyperopt 全部 epoch 零交易时不产出参数文件——用类默认参数继续（如实反映"该窗口无信号"）
        print("    （hyperopt 未产出参数：样本内零交易，沿用类默认参数）", flush=True)
    effective = load_effective_params(strategy, strategy_dir)
    row = {
        "window": index,
        "is_range": window.is_timerange,
        "oos_range": window.oos_timerange,
        "stoploss": effective["stoploss"],
        "compliant": not audit_params(strategy, effective),
    }
    for phase, timerange in (("is", window.is_timerange), ("oos", window.oos_timerange)):
        results_dir = out_dir / f"w{index:02d}_{phase}"
        results_dir.mkdir()
        run_freqtrade([
            "backtesting", "--config", str(CONFIG),
            "--strategy", strategy, "--strategy-path", str(strategy_dir),
            "--timerange", timerange,
            "--export", "trades", "--backtest-directory", str(results_dir),
        ])
        row[phase] = read_backtest_metrics(results_dir, strategy)
    return row


def render_report(strategy: str, run_id: str, epochs: int,
                  window_desc: str, rows: list[dict]) -> str:
    oos_profits = [r["oos"]["profit_total"] for r in rows]
    concat_return = 1.0
    for profit in oos_profits:
        concat_return *= 1 + profit
    concat_return -= 1
    positive = sum(1 for p in oos_profits if p > 0)
    decay = sum(r["oos"]["profit_total"] - r["is"]["profit_total"] for r in rows) / len(rows)
    compliant = sum(1 for r in rows if r["compliant"])

    lines = [
        "# Walk-Forward 验证报告",
        "",
        f"- 运行: `{run_id}` | 策略: {strategy} | 每窗口 hyperopt {epochs} epochs（SharpeHyperOptLoss）",
        f"- 窗口: {window_desc}，共 {len(rows)} 个",
        f"- 产物与逐窗口参数存档: `user_data/walk_forward/{run_id}/`",
        "",
        "| # | 样本内区间 | IS 收益 | OOS 收益 | OOS Sharpe | OOS 回撤 | OOS 市场 | 交易数 | 参数合规 |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r['window']} | {r['is_range']} | {r['is']['profit_total']:+.2%} "
            f"| {r['oos']['profit_total']:+.2%} | {r['oos']['sharpe']:.2f} "
            f"| {r['oos']['max_drawdown']:.2%} | {r['oos']['market_change']:+.2%} "
            f"| {r['oos']['trades']} | {'✓' if r['compliant'] else '✗ 越界'} |")
    lines += [
        "",
        "## 汇总",
        "",
        f"- **OOS 拼接收益（各段连乘）: {concat_return:+.2%}** —— 这是最接近『真实使用』的数字",
        f"- OOS 为正的窗口: {positive}/{len(rows)}",
        f"- IS→OOS 平均衰减: {decay:+.2%}（负值 = 样本外普遍差于样本内，即过拟合程度）",
        f"- 优化参数通过风险政策审计: {compliant}/{len(rows)}"
        "（越界窗口说明优化器再次尝试卖风险换收益，已被审计标记）",
        "",
        "## 读法",
        "",
        "1. 只有当 OOS 拼接收益为正、且多数窗口 OOS 为正时，参数化流程才算有泛化能力。",
        "2. IS 好看 + OOS 难看 = 过拟合；IS/OOS 都难看 = 策略本身无效。",
        "3. 任何单窗口的好结果都不构成上线依据。",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="walk-forward 验证")
    parser.add_argument("--strategy", default="EmaRsiStrategy")
    parser.add_argument("--start", default="2023-01-01")
    parser.add_argument("--end", default=date.today().isoformat())
    parser.add_argument("--is-months", type=int, default=12)
    parser.add_argument("--oos-months", type=int, default=3)
    parser.add_argument("--step-months", type=int, default=3)
    parser.add_argument("--epochs", type=int, default=30)
    parser.add_argument("--report-to", default=str(REPORT_TARGET),
                        help="汇总报告写入路径（避免覆盖历史报告）")
    args = parser.parse_args()

    windows = build_windows(date.fromisoformat(args.start), date.fromisoformat(args.end),
                            args.is_months, args.oos_months, args.step_months)
    if not windows:
        print("时间范围不足以构成任何窗口")
        return 1

    run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir = PROJECT_DIR / "user_data" / "walk_forward" / run_id
    strategy_dir = out_dir / "strategy"
    strategy_dir.mkdir(parents=True)
    # 复制全部策略源码（变体通过继承引用基类文件），参数 json 不复制——每窗口从干净参数开始
    for src in DEFAULT_STRATEGY_DIR.glob("*.py"):
        shutil.copy(src, strategy_dir)

    print(f"walk-forward: {len(windows)} 个窗口, 策略 {args.strategy}, run={run_id}")
    rows = []
    for index, window in enumerate(windows):
        print(f"[{index + 1}/{len(windows)}] IS {window.is_timerange} → OOS {window.oos_timerange} ...",
              flush=True)
        row = run_window(index, window, args.strategy, strategy_dir, out_dir, args.epochs)
        print(f"    IS {row['is']['profit_total']:+.2%} | OOS {row['oos']['profit_total']:+.2%}"
              f" | 合规 {'✓' if row['compliant'] else '✗'}", flush=True)
        rows.append(row)

    window_desc = (f"样本内 {args.is_months} 个月 → 样本外 {args.oos_months} 个月，"
                   f"步长 {args.step_months} 个月")
    report = render_report(args.strategy, run_id, args.epochs, window_desc, rows)
    (out_dir / "report.md").write_text(report)
    report_target = Path(args.report_to)
    report_target.parent.mkdir(parents=True, exist_ok=True)
    report_target.write_text(report)
    print(f"报告: {report_target} （存档: {out_dir / 'report.md'}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
