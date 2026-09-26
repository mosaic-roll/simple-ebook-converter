"""章节树的目录输出：缩进文本给人看，JSON 给 GUI 预览与机器读。"""

from __future__ import annotations

from .config import DEFAULT_TOC_DEPTH, Node


def to_json(tree: list[Node], depth: int = DEFAULT_TOC_DEPTH) -> list[dict]:
    """章节树转 JSON 列表，逐层按 depth 裁剪（语义与 `to_text` 一致）。

    每项含 `title`（替换后）、`raw_title`（原文）、`level`、`class_name`、`children`。
    """
    return [_entry(node, depth) for node in tree]


def to_text(tree: list[Node], depth: int = DEFAULT_TOC_DEPTH) -> str:
    """章节树转缩进文本，一行一个标题。"""
    lines: list[str] = []

    def emit(nodes: list[Node]) -> None:
        for node in nodes:
            lines.append("  " * max(0, node.level - 1) + node.title)
            emit([c for c in node.children if c.level <= depth])

    emit(tree)
    return "\n".join(lines)


def _entry(node: Node, depth: int) -> dict:
    children = [] if depth <= 0 else [c for c in node.children if c.level <= depth]
    return {
        "title": node.title,
        "raw_title": node.raw_title,
        "level": node.level,
        "class_name": node.class_name,
        "children": [_entry(c, depth) for c in children],
    }
