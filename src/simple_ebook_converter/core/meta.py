"""从文件名猜书名与作者：`《书名》（校对版全本）作者：某人.txt` → 书名、某人。"""

from __future__ import annotations

import re
from pathlib import Path

_TITLE_RE = re.compile(r"《([^》]+)》")
_AUTHOR_RE = re.compile(r"作者\s*[:：]\s*([^\s（(]+)")


def guess_metadata(stem: str) -> tuple[str | None, str | None]:
    """只看文件名（不含扩展名），猜不到就返回 (None, None)。"""
    title = _TITLE_RE.search(stem)
    author = _AUTHOR_RE.search(stem)
    return (
        title.group(1).strip() if title else None,
        author.group(1).strip() if author else None,
    )


def resolve_metadata(
    source: str | Path,
    title: str | None = None,
    author: str = "",
) -> tuple[str, str]:
    """定书名与作者：显式值优先（空白视同未给），否则从文件名猜。

    书名猜不到时退回输入文件名本身，好让「一条标题都没命中时整篇作为一章」有个
    可用的章节名；作者猜不到就是空字符串，调用方据此不写 `dc:creator`。
    """
    stem = Path(source).stem
    guessed_title, guessed_author = guess_metadata(stem)
    return (
        (title or "").strip() or guessed_title or stem,
        (author or "").strip() or guessed_author or "",
    )
