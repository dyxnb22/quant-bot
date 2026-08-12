#!/usr/bin/env bash
# 以 launchd 用户服务方式启动 dry-run 模拟盘：常驻、崩溃自动重启、登录自启。
set -euo pipefail
cd "$(dirname "$0")/.."

LABEL="com.quantbot.dryrun"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
PROJECT_DIR="$(pwd)"

if launchctl print "gui/$(id -u)/${LABEL}" >/dev/null 2>&1; then
    echo "bot 服务已在运行（launchd: ${LABEL}）"
    exit 0
fi

chmod 600 .env 2>/dev/null || true
if rg -q '=change_me' .env 2>/dev/null; then
    echo "拒绝启动：.env 存在默认凭据 change_me，请先生成随机凭据。" >&2
    exit 1
fi

echo "启动前风险审计..."
if ! .venv/bin/python -m quantlab.risk_policy; then
    echo "审计未通过，拒绝启动。请修复违规项后重试。" >&2
    exit 1
fi

mkdir -p "$HOME/Library/LaunchAgents" user_data/logs
cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>$LABEL</string>
    <key>ProgramArguments</key>
    <array>
        <string>$PROJECT_DIR/scripts/bot_run.sh</string>
    </array>
    <key>WorkingDirectory</key><string>$PROJECT_DIR</string>
    <key>RunAtLoad</key><true/>
    <key>KeepAlive</key><true/>
    <key>StandardOutPath</key><string>$PROJECT_DIR/user_data/logs/launchd.out.log</string>
    <key>StandardErrorPath</key><string>$PROJECT_DIR/user_data/logs/launchd.err.log</string>
</dict>
</plist>
EOF
chmod 600 "$PLIST"

launchctl bootstrap "gui/$(id -u)" "$PLIST"
echo "bot 服务已启动（launchd: ${LABEL}，崩溃自动重启，登录自启）"
echo "日志: user_data/logs/freqtrade.log"
echo "UI:   http://127.0.0.1:8080 (账号见 .env)"
