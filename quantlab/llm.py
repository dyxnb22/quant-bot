"""DeepSeek LLM 客户端（OpenAI 兼容接口，零第三方依赖）。

外部 API 走系统代理（与本机 API 检查相反，这里需要代理）。
key 只从环境变量或 .env 读取，绝不入库。
"""

import json
import os
import urllib.request

from quantlab.strategy_loader import PROJECT_DIR

API_URL = "https://api.deepseek.com/chat/completions"
DEFAULT_MODEL = "deepseek-chat"


def _api_key() -> str:
    key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not key:
        env_file = PROJECT_DIR / ".env"
        if env_file.exists():
            for line in env_file.read_text().splitlines():
                if line.strip().startswith("DEEPSEEK_API_KEY="):
                    key = line.split("=", 1)[1].strip()
    if not key:
        raise RuntimeError("缺少 DEEPSEEK_API_KEY（设置环境变量或写入 .env）")
    return key


def chat(system: str, user: str, model: str = DEFAULT_MODEL,
         temperature: float = 0.3, max_tokens: int = 2500, timeout: int = 180) -> str:
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    request = urllib.request.Request(
        API_URL,
        data=json.dumps(payload).encode(),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {_api_key()}",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        data = json.load(response)
    return data["choices"][0]["message"]["content"]
