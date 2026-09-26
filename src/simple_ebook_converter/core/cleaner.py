"""默认清理：去掉段首段尾空格、删除空行。`--no-clean` 整体关掉。"""

from __future__ import annotations

#: 算「行首段尾空格」的字符：半角空格、制表符、全角空格
_BLANKS = " \t\u3000"


def clean_line(line: str) -> str:
    return line.strip(_BLANKS)


def clean_lines(lines: list[str]) -> list[str]:
    """清理一个节点的段落，清空后为空的行直接不要。"""
    return [cleaned for line in lines if (cleaned := clean_line(line))]
