"""报告溯源戳：commit + 数据指纹，保证任何报告可独立复现其输入。"""

import hashlib
import subprocess
from datetime import datetime

from quantlab.strategy_loader import PROJECT_DIR

DATA_ROOT = PROJECT_DIR / "user_data" / "data"


def stamp() -> str:
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], cwd=PROJECT_DIR,
            capture_output=True, text=True, timeout=10).stdout.strip() or "unknown"
    except Exception:
        commit = "unknown"
    digest = hashlib.sha1()
    for path in sorted(DATA_ROOT.rglob("*.feather")):
        digest.update(path.read_bytes())
    return (f"commit {commit} | 数据指纹 sha1:{digest.hexdigest()[:10]} "
            f"| {datetime.now():%F %T}")
