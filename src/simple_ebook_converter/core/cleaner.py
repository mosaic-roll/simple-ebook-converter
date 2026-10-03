"""默认清理：去掉段首段尾空格、删除空行。`--no-clean` 整体关掉。

`escape()` 暂住这里：它是纯文本工具（HTML 转义），不是清理逻辑的一部分，原先定义在
`builder` 里，而 `pipeline` 为了处理标题得从那儿借——一个组 EPUB 的模块当纯文本工具的
中转站，位置不对。`builder` 与 `pipeline` 都从这里取。

别让这里变成杂物间：再有类似的纯文本 helper，先想想是不是该单独开一个 `text` 模块。
"""

from __future__ import annotations

import html

#: 算「行首段尾空格」的字符：半角空格、制表符、全角空格
_BLANKS = " \t　"


def clean_line(line: str) -> str:
    return line.strip(_BLANKS)


def clean_lines(lines: list[str]) -> list[str]:
    """清理一个节点的段落，清空后为空的行直接不要。"""
    return [cleaned for line in lines if (cleaned := clean_line(line))]


def escape(text: str) -> str:
    """HTML 转义。`None` 当空串——标题、class 名都可能缺。"""
    return html.escape(text or "", quote=True)
