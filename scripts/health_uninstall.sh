#!/usr/bin/env bash
set -euo pipefail

LABEL="com.quantbot.healthcheck"
PLIST="$HOME/Library/LaunchAgents/${LABEL}.plist"

if launchctl print "gui/$(id -u)/${LABEL}" >/dev/null 2>&1; then
    launchctl bootout "gui/$(id -u)/${LABEL}"
    for _ in $(seq 1 20); do
        launchctl print "gui/$(id -u)/${LABEL}" >/dev/null 2>&1 || break
        sleep 1
    done
    echo "巡检任务已卸载（launchd: ${LABEL}）"
else
    echo "巡检任务未在运行"
fi
rm -f "$PLIST"
