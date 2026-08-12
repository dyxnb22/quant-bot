"""机器可读试验登记册：家族累计试验数（多重检验分母），只读接口。

计数变更只能通过编辑 docs/results/registry.json 并提交（git 历史即审计轨迹）；
运行时不提供任何调小/覆盖入口（P1-03 治理绕过修复）。
"""

import json

from quantlab.strategy_loader import PROJECT_DIR

REGISTRY_FILE = PROJECT_DIR / "docs" / "results" / "registry.json"


def family_trials(market: str) -> int:
    data = json.loads(REGISTRY_FILE.read_text())
    return int(data["families"][market]["n_trials"])
