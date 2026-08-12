"""数据快照 manifest：记录各数据文件的行数/列数/哈希，保证研究输入可追溯。

用法：`make manifest`（cn-data-refresh 前自动执行一次，存档刷新前状态）。
产物在 user_data/data/（不入库），最新一份即当前数据指纹。
"""

import hashlib
import sys
from datetime import datetime

import pandas as pd

from quantlab.strategy_loader import PROJECT_DIR

DATA_ROOT = PROJECT_DIR / "user_data" / "data"


def file_fingerprint(path) -> dict:
    digest = hashlib.sha1(path.read_bytes()).hexdigest()[:10]
    frame = pd.read_feather(path)
    return {"file": str(path.relative_to(DATA_ROOT)), "rows": len(frame),
            "cols": frame.shape[1], "sha1": digest,
            "mtime": datetime.fromtimestamp(path.stat().st_mtime).strftime("%F %T")}


def main() -> int:
    records = [file_fingerprint(p) for p in sorted(DATA_ROOT.rglob("*.feather"))]
    if not records:
        print("无数据文件")
        return 0
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target = DATA_ROOT / f"MANIFEST-{stamp}.txt"
    lines = [f"{r['file']} | {r['rows']} 行 × {r['cols']} 列 | sha1:{r['sha1']} | {r['mtime']}"
             for r in records]
    target.write_text("\n".join(lines) + "\n")
    print(f"manifest: {target}（{len(records)} 个文件）")
    for line in lines:
        print(" ", line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
