from __future__ import annotations

from .config import Node


def node_to_dict(node: Node) -> dict:
    return {
        "title": node.title,
        "level": node.level,
        "cls": node.cls,
        "children": [node_to_dict(c) for c in node.children],
    }


def to_json(tree: list[Node], depth: int = 6) -> list[dict]:
    out = []
    for node in tree:
        entry = node_to_dict(node)
        if depth > 0:
            entry["children"] = [
                c for c in entry["children"] if c["level"] <= depth
            ]
        out.append(entry)
    return out


def to_text(tree: list[Node], depth: int = 6) -> str:
    lines: list[str] = []

    def walk(nodes: list[Node]) -> None:
        for node in nodes:
            lines.append("  " * max(0, node.level - 1) + node.title)
            walk([c for c in node.children if c.level <= depth])

    walk(tree)
    return "\n".join(lines)