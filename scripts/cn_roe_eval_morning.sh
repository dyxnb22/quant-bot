#!/usr/bin/env bash
# 安装每天 06:30 的 A 股 ROE 自动评估：财报数据覆盖率达标即出 22 号报告并自卸载；
# 数据未齐（覆盖率守卫拒绝）则次日 06:30 再试。
# 取消：launchctl bootout gui/$(id -u)/com.quantbot.cnroeeval
set -euo pipefail
cd "$(dirname "$0")/.."

LABEL="com.quantbot.cnroeeval"
PLIST="$HOME/Library/LaunchAgents/${LABEL}.plist"
PROJECT_DIR="$(pwd)"

launchctl bootout "gui/$(id -u)/${LABEL}" 2>/dev/null || true
mkdir -p user_data/logs
cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>${LABEL}</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string><string>-c</string>
        <string>cd "${PROJECT_DIR}" &amp;&amp; .venv/bin/python -u -m quantlab.factor_eval --market cn --factors roe_pit --report-to docs/results/22-cn-roe.md &amp;&amp; launchctl bootout "gui/$(id -u)/${LABEL}"</string>
    </array>
    <key>WorkingDirectory</key><string>${PROJECT_DIR}</string>
    <key>StartCalendarInterval</key>
    <dict><key>Hour</key><integer>6</integer><key>Minute</key><integer>30</integer></dict>
    <key>StandardOutPath</key><string>${PROJECT_DIR}/user_data/logs/cn_roe_eval.log</string>
    <key>StandardErrorPath</key><string>${PROJECT_DIR}/user_data/logs/cn_roe_eval.log</string>
</dict>
</plist>
EOF
chmod 600 "$PLIST"
launchctl bootstrap "gui/$(id -u)" "$PLIST"
echo "ROE 自动评估已安装（${LABEL}，每天 06:30 尝试，数据齐即出 22 号报告并自卸载，日志 user_data/logs/cn_roe_eval.log）"
