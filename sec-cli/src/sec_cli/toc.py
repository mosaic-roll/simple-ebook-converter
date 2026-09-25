from __future__ import annotations

from .config import Node


def _to_dict(node: Node, depth: int) -> dict:
    entry = {
        "title": node.title,
        "raw_title": node.raw_title,
        "level": node.level,
        "class_name": node.class_name,
    }
    if depth <= 0:
        entry["children"] = []
    else:
        entry["children"] = [_to_dict(c, depth) for c in node.children if c.level <= depth]
    return entry


def to_json(tree: list[Node], depth: int = 6) -> list[dict]:
    """章节树转 JSON，逐层按 depth 裁剪（与 to_text 语义一致）。"""
    return [_to_dict(node, depth) for node in tree]


def to_text(tree: list[Node], depth: int = 6) -> str:
    lines: list[str] = []

    def walk(nodes: list[Node]) -> None:
        for node in nodes:
            lines.append("  " * max(0, node.level - 1) + node.title)
            walk([c for c in node.children if c.level <= depth])

    walk(tree)
    return "\n".join(lines)