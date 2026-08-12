#!/usr/bin/env bash
# 安装一次性深夜下载任务：今晚 02:30 续传 A 股数据（避开 baostock 日间限流窗口）。
# 完成后任务自动退出；如需取消：launchctl bootout gui/$(id -u)/com.quantbot.cndownload
set -euo pipefail
cd "$(dirname "$0")/.."

LABEL="com.quantbot.cndownload"
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
        <string>-u</string><string>-m</string><string>quantlab.cn_data</string>
        <string>--years</string><string>10</string>
    </array>
    <key>WorkingDirectory</key><string>${PROJECT_DIR}</string>
    <key>StartCalendarInterval</key>
    <dict><key>Hour</key><integer>2</integer><key>Minute</key><integer>30</integer></dict>
    <key>StandardOutPath</key><string>${PROJECT_DIR}/user_data/logs/cn_download.log</string>
    <key>StandardErrorPath</key><string>${PROJECT_DIR}/user_data/logs/cn_download.log</string>
</dict>
</plist>
EOF
chmod 600 "$PLIST"
launchctl bootstrap "gui/$(id -u)" "$PLIST"
echo "深夜下载任务已安装（${LABEL}，02:30 断点续传，日志 user_data/logs/cn_download.log）"
