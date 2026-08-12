#!/usr/bin/env bash
# 安装一次性深夜财报下载任务：今晚 02:30 下载季频 roeAvg（约 3.5 小时/宇宙，断点续传）。
# 先跑 hs300，成功后接着跑 zz500（若时间窗不够，zz500 次日续传）。
# 完成后任务自动退出；取消：launchctl bootout gui/$(id -u)/com.quantbot.cnfundamentals
set -euo pipefail
cd "$(dirname "$0")/.."

LABEL="com.quantbot.cnfundamentals"
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
        <string>cd "${PROJECT_DIR}" &amp;&amp; .venv/bin/python -u -m quantlab.cn_fundamentals --universe hs300 --years 10 &amp;&amp; .venv/bin/python -u -m quantlab.cn_fundamentals --universe zz500 --years 10 &amp;&amp; launchctl bootout "gui/$(id -u)/${LABEL}"</string>
    </array>
    <key>WorkingDirectory</key><string>${PROJECT_DIR}</string>
    <key>StartCalendarInterval</key>
    <dict><key>Hour</key><integer>2</integer><key>Minute</key><integer>30</integer></dict>
    <key>StandardOutPath</key><string>${PROJECT_DIR}/user_data/logs/cn_fundamentals.log</string>
    <key>StandardErrorPath</key><string>${PROJECT_DIR}/user_data/logs/cn_fundamentals.log</string>
</dict>
</plist>
EOF
chmod 600 "$PLIST"
launchctl bootstrap "gui/$(id -u)" "$PLIST"
echo "深夜财报下载已安装（${LABEL}，02:30 起 hs300→zz500，断点续传，成功自卸载，日志 user_data/logs/cn_fundamentals.log）"
