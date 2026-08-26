"""读取仅供本机服务使用的 macOS 钥匙串密钥。"""

from __future__ import annotations

import getpass
import os
import subprocess
from typing import Optional


def read_secret(
    environment_variable: str,
    service: str,
    *,
    account: Optional[str] = None,
) -> str:
    """优先环境变量，缺失时从登录钥匙串读取。

    ``security -w`` 的标准输出就是密钥，因此这里绝不记录 stdout、
    stderr 或异常细节。调用者只会得到密钥本身或空字符串。
    """

    value = os.environ.get(environment_variable, "").strip()
    if value:
        return value

    try:
        result = subprocess.run(
            [
                "/usr/bin/security",
                "find-generic-password",
                "-a",
                account or getpass.getuser(),
                "-s",
                service,
                "-w",
            ],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""

    if result.returncode != 0:
        return ""
    return result.stdout.strip()
