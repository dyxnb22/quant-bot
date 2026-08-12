"""风险政策代码化：配置与策略生效参数必须通过审计才允许运行。

政策是项目的风险底线；hyperopt 等优化器只优化目标函数、没有风险观，
其产物必须经过本审计才能进入运行环境（bot_start.sh 强制执行）。
"""

import json
import sys
from dataclasses import dataclass
from pathlib import Path

from quantlab.strategy_loader import PROJECT_DIR, load_effective_params

STOPLOSS_DEEPEST = -0.20
STOPLOSS_SHALLOWEST = -0.005
MAX_OPEN_TRADES_LIMIT = 5
STAKE_RATIO_LIMIT = 0.10
ALLOWED_TIMEFRAMES = {"5m", "15m", "1h", "4h", "1d"}
REQUIRED_PROTECTIONS = {"MaxDrawdown", "StoplossGuard"}
AUDITED_STRATEGIES = ("EmaRsiStrategy", "RsiMeanRevertStrategy", "EmaRsiTrendStrategy")


@dataclass
class Violation:
    subject: str
    rule: str
    actual: object

    def __str__(self) -> str:
        return f"[{self.subject}] {self.rule}（实际值: {self.actual}）"


def audit_params(subject: str, params: dict) -> list[Violation]:
    violations = []
    stoploss = params.get("stoploss")
    if not isinstance(stoploss, (int, float)) or not (
        STOPLOSS_DEEPEST <= stoploss <= STOPLOSS_SHALLOWEST
    ):
        violations.append(Violation(
            subject, f"止损必须在 [{STOPLOSS_DEEPEST}, {STOPLOSS_SHALLOWEST}] 内", stoploss))
    roi = params.get("minimal_roi") or {}
    if "0" not in {str(k) for k in roi}:
        violations.append(Violation(subject, "minimal_roi 必须存在且含 '0' 档", roi))
    if params.get("timeframe") not in ALLOWED_TIMEFRAMES:
        violations.append(Violation(
            subject, f"timeframe 必须属于 {sorted(ALLOWED_TIMEFRAMES)}", params.get("timeframe")))
    missing = REQUIRED_PROTECTIONS - set(params.get("protections") or [])
    if missing:
        violations.append(Violation(
            subject, f"缺少必需 protections: {sorted(missing)}", params.get("protections")))
    return violations


def audit_config(config: dict) -> list[Violation]:
    violations = []
    if config.get("dry_run") is not True:
        violations.append(Violation("config", "dry_run 必须为 true", config.get("dry_run")))
    max_open = config.get("max_open_trades", 0)
    if not isinstance(max_open, int) or not (0 < max_open <= MAX_OPEN_TRADES_LIMIT):
        violations.append(Violation(
            "config", f"max_open_trades 必须在 (0, {MAX_OPEN_TRADES_LIMIT}] 内", max_open))
    stake = config.get("stake_amount")
    wallet = config.get("dry_run_wallet", 0)
    if not isinstance(stake, (int, float)) or stake > wallet * STAKE_RATIO_LIMIT:
        violations.append(Violation(
            "config", f"stake_amount 不得超过 dry_run_wallet 的 {STAKE_RATIO_LIMIT:.0%}", stake))
    return violations


def run_audit(config_path=None, strategies=AUDITED_STRATEGIES, strategy_dir=None):
    config_file = Path(config_path) if config_path else PROJECT_DIR / "config" / "config.json"
    violations = audit_config(json.loads(config_file.read_text()))
    for name in strategies:
        violations += audit_params(name, load_effective_params(name, strategy_dir))
    return violations


def main() -> int:
    violations = run_audit()
    if violations:
        print("风险审计未通过：")
        for violation in violations:
            print(f"  ✗ {violation}")
        return 1
    print("风险审计通过：config 与全部策略生效参数均在政策边界内")
    return 0


if __name__ == "__main__":
    sys.exit(main())
