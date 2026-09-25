from __future__ import annotations

import re

_TITLE_RE = re.compile(r"《([^》]+)》")
_AUTHOR_RE = re.compile(r"作者\s*[:：]\s*([^\s（(]+)")


def guess_metadata(stem: str) -> tuple[str | None, str | None]:
    """从文件名猜书名与作者。

    示例：
      《希灵帝国》（校对版全本）作者：远瞳  -> ("希灵帝国", "远瞳")
      《希灵帝国》作者：远瞳                -> ("希灵帝国", "远瞳")
      novel.txt                           -> (None, None)

    CLI 与 GUI 共用此函数。
    """
    title = None
    if (m := _TITLE_RE.search(stem)) is not None:
        title = m.group(1).strip()
    author = None
    if (m := _AUTHOR_RE.search(stem)) is not None:
        author = m.group(1).strip()
    return title, author