#!/usr/bin/env bash
# 停止并卸载 launchd 服务（否则 KeepAlive 会把进程拉起来）。
set -euo pipefail

LABEL="com.quantbot.dryrun"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"

if launchctl print "gui/$(id -u)/${LABEL}" >/dev/null 2>&1; then
    launchctl bootout "gui/$(id -u)/${LABEL}"
    # bootout 异步生效，等待服务真正消失，避免与随后的启动产生竞态
    for _ in $(seq 1 20); do
        launchctl print "gui/$(id -u)/${LABEL}" >/dev/null 2>&1 || break
        sleep 1
    done
    echo "bot 服务已停止并卸载（launchd: ${LABEL}）"
else
    echo "bot 服务未在运行"
fi
rm -f "$PLIST"
