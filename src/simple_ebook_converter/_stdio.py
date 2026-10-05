"""输出编码兜底。

Windows 上 `sys.stdout` / `sys.stderr` 默认用系统 ANSI 代码页：简体中文系统是
cp936 能正常输出中文，但英文系统是 cp1252、西欧系统是 cp1252 一类，编码不了
本项目大量使用的中文提示，`print` 会抛
`UnicodeEncodeError: 'charmap' codec can't encode characters`。

CLI 受影响最直接：Click 在格式化 usage、报错信息时也要输出中文，一旦抛
UnicodeEncodeError，连错误提示本身都显示不出来，用户只看到一段截断的 usage，
退出码 1，非常难排查。

这里只改容错策略、不改编码：ASCII 输出完全不受影响，中文在 cp936 等能编码的
环境下照常显示，在 cp1252 下转义成 `\\uXXXX` 而不是让整个程序崩掉。
"""

from __future__ import annotations

import sys
from typing import IO


def make_output_encoding_safe() -> None:
    """给 stdout/stderr 设上容错策略；对不支持的流静默跳过。

    被打包成 `--noconsole` 的图形界面版里这两个流是 `None`，跳过即可；
    测试框架替换后的流可能没有 `reconfigure`，同样跳过。
    """
    for stream in (sys.stdout, sys.stderr):
        _set_errors(stream, "backslashreplace")


def _set_errors(stream: IO[str] | None, errors: str) -> None:
    if stream is None:
        return
    try:
        stream.reconfigure(errors=errors)
    except (AttributeError, ValueError, OSError):
        # 不是 TextIOWrapper，或流已关闭；维持原状即可，不影响主流程
        pass
