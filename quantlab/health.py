"""健康巡检：launchd 服务/进程/API/日志新鲜度，异常时 macOS 本地通知。"""

import argparse
import base64
import json
import os
import subprocess
import sys
import time
import urllib.request
from datetime import datetime

from quantlab.strategy_loader import PROJECT_DIR

LOG_FILE = PROJECT_DIR / "user_data" / "logs" / "freqtrade.log"
API_BASE = "http://127.0.0.1:8080/api/v1"
BOT_LABEL = "com.quantbot.dryrun"
LOG_FRESH_SECONDS = 600  # 心跳 60s，10 分钟无写入即异常

# 本机 API 检查必须绕过系统代理（HTTP_PROXY 指向本地代理时会把 127.0.0.1 也路由进去）
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def load_env() -> dict:
    env = {}
    for line in (PROJECT_DIR / ".env").read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            env[key.strip()] = value.strip()
    return env


def check_service() -> bool:
    result = subprocess.run(
        ["launchctl", "print", f"gui/{os.getuid()}/{BOT_LABEL}"],
        capture_output=True)
    return result.returncode == 0


def check_process() -> bool:
    return subprocess.run(["pgrep", "-f", "freqtrade trade"],
                          capture_output=True).returncode == 0


def check_api_running(env: dict) -> bool:
    with _OPENER.open(f"{API_BASE}/ping", timeout=5) as response:
        if json.load(response).get("status") != "pong":
            return False
    token = base64.b64encode(
        f"{env['FT_API_USERNAME']}:{env['FT_API_PASSWORD']}".encode()).decode()
    request = urllib.request.Request(
        f"{API_BASE}/show_config", headers={"Authorization": f"Basic {token}"})
    with _OPENER.open(request, timeout=5) as response:
        return json.load(response).get("state") == "running"


def check_log_fresh() -> bool:
    return LOG_FILE.exists() and time.time() - LOG_FILE.stat().st_mtime <= LOG_FRESH_SECONDS


def notify(message: str) -> None:
    subprocess.run(
        ["osascript", "-e",
         f'display notification "{message}" with title "quant-bot 巡检告警"'],
        capture_output=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="quant-bot 健康巡检")
    parser.add_argument("--notify", action="store_true", help="异常时发送 macOS 本地通知")
    args = parser.parse_args()

    failures = []
    checks = [("launchd 服务", check_service), ("进程", check_process),
              ("日志新鲜度", check_log_fresh)]
    for name, check in checks:
        try:
            ok = check()
        except Exception:
            ok = False
        if not ok:
            failures.append(name)
    try:
        if not check_api_running(load_env()):
            failures.append("API 状态")
    except Exception:
        failures.append("API 可达性")

    timestamp = datetime.now().strftime("%F %T")
    if failures:
        message = "、".join(failures) + " 异常"
        print(f"[{timestamp}] FAIL: {message}")
        if args.notify:
            notify(message)
        return 1
    print(f"[{timestamp}] OK: 服务/进程/API/日志 全部正常")
    return 0


if __name__ == "__main__":
    sys.exit(main())
