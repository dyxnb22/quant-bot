#!/usr/bin/env bash
# 安装 launchd 每日值班日报：每天 09:00 生成（依赖 .env 中的 DEEPSEEK_API_KEY）。
set -euo pipefail
cd "$(dirname "$0")/.."

LABEL="com.quantbot.dailybrief"
PLIST="$HOME/Library/LaunchAgents/${LABEL}.plist"
PROJECT_DIR="$(pwd)"

launchctl bootout "gui/$(id -u)/${LABEL}" 2>/dev/null || true
mkdir -p user_data/logs/daily_brief
cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>${LABEL}</string>
    <key>ProgramArguments</key>
    <array>
        <string>${PROJECT_DIR}/.venv/bin/python</string>
        <string>-m</string><string>quantlab.daily_brief</string>
    </array>
    <key>WorkingDirectory</key><string>${PROJECT_DIR}</string>
    <key>StartCalendarInterval</key>
    <dict><key>Hour</key><integer>9</integer><key>Minute</key><integer>0</integer></dict>
    <key>StandardOutPath</key><string>${PROJECT_DIR}/user_data/logs/daily_brief/launchd.log</string>
    <key>StandardErrorPath</key><string>${PROJECT_DIR}/user_data/logs/daily_brief/launchd.log</string>
</dict>
</plist>
EOF
chmod 600 "$PLIST"
launchctl bootstrap "gui/$(id -u)" "$PLIST"
echo "日报任务已安装（launchd: ${LABEL}，每天 09:00，产物 user_data/logs/daily_brief/）"
