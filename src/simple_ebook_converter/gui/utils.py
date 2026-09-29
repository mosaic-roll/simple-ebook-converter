"""跨平台工具：与 core 无关的纯本地动作。"""

from __future__ import annotations

import os
import subprocess
import sys


def open_with_default_app(path: str) -> None:
    """用系统默认程序打开文件；路径为空或不存在时抛 `FileNotFoundError`。"""
    if not path or not os.path.exists(path):
        raise FileNotFoundError(path)
    if sys.platform == "win32":
        os.startfile(path)  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.run(["open", path], check=False)
    else:
        subprocess.run(["xdg-open", path], check=False)
