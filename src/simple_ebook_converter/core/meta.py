from __future__ import annotations

import re
from pathlib import Path

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


def resolve_metadata(
    source: str | Path,
    title: str | None = None,
    author: str = "",
) -> tuple[str, str]:
    """定书名与作者：显式指定优先，否则从文件名猜。CLI 与 GUI 共用。

    `source` 可以是完整路径或裸文件名（取 stem 后猜测）。显式值会先 strip，
    空白视同未指定；猜不到时退回输入文件名本身，保证 `title` 至少可用于
    EPUB 元数据与「无标题时整篇作为一章」的兜底标题。

    示例：
      resolve_metadata("《希灵帝国》作者：远瞳.txt")      -> ("希灵帝国", "远瞳")
      resolve_metadata("novel.txt", title="手写")         -> ("手写", "")
      resolve_metadata("novel.txt", author="某人")        -> ("novel", "某人")
    """
    stem = Path(source).stem
    guessed_title, guessed_author = guess_metadata(stem)
    return (
        (title or "").strip() or guessed_title or stem,
        (author or "").strip() or guessed_author or "",
    )
