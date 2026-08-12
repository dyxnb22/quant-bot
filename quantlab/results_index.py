"""生成 docs/results/ 索引（README.md）：编号报告 + 登记册入口。"""

import sys

from quantlab.strategy_loader import PROJECT_DIR

RESULTS_DIR = PROJECT_DIR / "docs" / "results"


def first_heading(path) -> str:
    for line in path.read_text().splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return path.stem


def main() -> int:
    entries = []
    for path in sorted(RESULTS_DIR.glob("*.md")):
        if path.name == "README.md":
            continue
        entries.append(f"| [{path.stem}]({path.name}) | {first_heading(path)} |")
    lines = [
        "# 研究报告索引（自动生成：make results-index）",
        "",
        "| 文件 | 标题 |",
        "|---|---|",
        *entries,
    ]
    (RESULTS_DIR / "README.md").write_text("\n".join(lines) + "\n")
    print(f"索引: {RESULTS_DIR / 'README.md'}（{len(entries)} 篇）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
