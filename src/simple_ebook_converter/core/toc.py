"""渲染目录：缩进文本、JSON 树（给 GUI 预览），以及按格式选一种的 `render()`。"""

from __future__ import annotations

import json

from .config import DEFAULTS, Node

#: `--toc-format` 的取值
FORMATS = ("text", "json")


def render(tree: list[Node], depth: int, fmt: str) -> str:
    """按格式渲染目录正文，供 `--toc-only` 输出。"""
    if fmt == "json":
        return json.dumps(to_json(tree, depth), ensure_ascii=False, indent=2)
    if fmt == "text":
        return to_text(tree, depth)
    raise ValueError(f"目录格式只能是 {'/'.join(FORMATS)}，收到：{fmt!r}")


def to_json(tree: list[Node], depth: int = DEFAULTS.toc_depth) -> list[dict]:
    """转 JSON 列表供 GUI 预览或 `--toc-format json`。每节点含 `title`（替换后）、
    `raw_title`（原始）、`level`、`class_name`、`children`，超过 `depth` 的层级不带回来。
    """
    return [_entry(node, depth) for node in tree]


def to_text(tree: list[Node], depth: int = DEFAULTS.toc_depth) -> str:
    """转缩进文本，一行一个标题。"""
    lines: list[str] = []

    def emit(nodes: list[Node]) -> None:
        for node in nodes:
            lines.append("  " * max(0, node.level - 1) + node.title)
            emit([c for c in node.children if c.level <= depth])

    emit(tree)
    return "\n".join(lines)


def _entry(node: Node, depth: int) -> dict:
    return {
        "title": node.title,
        "raw_title": node.raw_title,
        "level": node.level,
        "class_name": node.class_name,
        "children": [_entry(c, depth) for c in node.children if c.level <= depth],
    }
