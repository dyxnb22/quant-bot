#!/usr/bin/env bash
# 安装 launchd 定时巡检：每 15 分钟运行一次 quantlab.health --notify。
set -euo pipefail
cd "$(dirname "$0")/.."

LABEL="com.quantbot.healthcheck"
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
        <string>${PROJECT_DIR}/.venv/bin/python</string>
        <string>-m</string><string>quantlab.health</string><string>--notify</string>
    </array>
    <key>WorkingDirectory</key><string>${PROJECT_DIR}</string>
    <key>StartInterval</key><integer>900</integer>
    <key>RunAtLoad</key><true/>
    <key>StandardOutPath</key><string>${PROJECT_DIR}/user_data/logs/health.log</string>
    <key>StandardErrorPath</key><string>${PROJECT_DIR}/user_data/logs/health.log</string>
</dict>
</plist>
EOF
chmod 600 "$PLIST"
launchctl bootstrap "gui/$(id -u)" "$PLIST"
echo "巡检任务已安装（launchd: ${LABEL}，每 15 分钟一次，日志 user_data/logs/health.log）"
