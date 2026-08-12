"""跨进程文件锁：数据写入者（下载）与消费者（清单/Gate）互斥，防混合版本读取。

flock 为建议锁，覆盖本项目全部数据访问入口即可（launchd 任务与手动命令共用）。
"""

import fcntl
import os
import time
from contextlib import contextmanager

from quantlab.strategy_loader import PROJECT_DIR

LOCK_DIR = PROJECT_DIR / "user_data"


@contextmanager
def file_lock(name: str = "cn_data", timeout: float = 900.0, poll: float = 2.0):
    LOCK_DIR.mkdir(parents=True, exist_ok=True)
    path = LOCK_DIR / f"{name}.lock"
    handle = open(path, "w")
    deadline = time.time() + timeout
    try:
        while True:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.time() > deadline:
                    raise TimeoutError(
                        f"获取锁超时: {path}（其他任务持有中，稍后重试）") from None
                time.sleep(poll)
        handle.seek(0)
        handle.write(str(os.getpid()))
        handle.truncate()
        handle.flush()
        yield
    finally:
        try:
            fcntl.flock(handle, fcntl.LOCK_UN)
        finally:
            handle.close()
