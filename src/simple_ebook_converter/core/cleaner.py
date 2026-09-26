from __future__ import annotations

import re

_LEADING = re.compile(r"^[ \t\u3000]+")
_TRAILING = re.compile(r"[ \t\u3000]+$")


def clean_line(line: str) -> str:
    """去掉段首、段尾空白（含全角空格）。"""
    return _TRAILING.sub("", _LEADING.sub("", line))


def clean_lines(lines: list[str]) -> list[str]:
    """逐行清理并删除空行。"""
    out: list[str] = []
    for line in lines:
        cleaned = clean_line(line)
        if cleaned:
            out.append(cleaned)
    return out
