from __future__ import annotations

from .config import Node


def node_to_dict(node: Node) -> dict:
    return {
        "title": node.title,
        "raw_title": node.raw_title,
        "level": node.level,
        "cls": node.cls,
        "children": [node_to_dict(c) for c in node.children],
    }


def to_json(tree: list[Node], depth: int = 6) -> list[dict]:
    out = []
    for node in tree:
        entry = node_to_dict(node)
        if depth > 0:
            entry["children"] = [c for c in entry["children"] if c["level"] <= depth]
        out.append(entry)
    return out


def to_text(tree: list[Node], depth: int = 6, show_raw: bool = False) -> str:
    lines: list[str] = []

    def walk(nodes: list[Node]) -> None:
        for node in nodes:
            indent = "  " * max(0, node.level - 1)
            if show_raw and node.raw_title and node.raw_title != node.title:
                lines.append(f"{indent}{node.raw_title} → {node.title}")
            else:
                lines.append(indent + node.title)
            walk([c for c in node.children if c.level <= depth])

    walk(tree)
    return "\n".join(lines)