"""报告溯源戳：commit（含脏状态）+ 运行命令 + 数据指纹。

范围声明：本戳用于事后核对"报告是在哪个代码/数据状态下生成的"，
不构成完整可复现快照（依赖锁、原始输入归档见 manifest 与 requirements.lock）。
"""

import hashlib
import subprocess
import sys
from datetime import datetime

from quantlab.strategy_loader import PROJECT_DIR

DATA_ROOT = PROJECT_DIR / "user_data" / "data"


def stamp() -> str:
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], cwd=PROJECT_DIR,
            capture_output=True, text=True, timeout=10).stdout.strip() or "unknown"
        dirty = subprocess.run(
            ["git", "status", "--porcelain"], cwd=PROJECT_DIR,
            capture_output=True, text=True, timeout=10).stdout.strip()
        if dirty:
            commit += "+dirty"
    except Exception:
        commit = "unknown"
    digest = hashlib.sha1()
    for path in sorted(DATA_ROOT.rglob("*.feather")):
        digest.update(path.read_bytes())
    argv = " ".join(sys.argv[:6])
    return (f"commit {commit} | 数据指纹 sha1:{digest.hexdigest()[:10]} "
            f"| 命令 `{argv}` | {datetime.now():%F %T}")
