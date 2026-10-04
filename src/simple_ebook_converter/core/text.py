"""文本处理：清理（去段首段尾空格、删空行）与 HTML 转义。`--no-clean` 整体关掉清理。"""

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