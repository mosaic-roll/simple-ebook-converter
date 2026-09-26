"""目录的渲染与往返：缩进文本、JSON 树，按格式选一种的 `render()`。

JSON 树是 GUI 预览与 `--toc-file` 共用的中间产物：只存原始标题（`raw_title`）与
直属行号范围（`lines`），标题的清理替换推迟到组装阶段。`to_json` / `tree_from_json`
互为逆操作，中间可以插一步人工编辑（改标题、删除线标记、合并章节）。
"""

from __future__ import annotations

import json
from pathlib import Path

from .config import DEFAULTS, Node
from .parser import assign_anchors

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
    """转 JSON 列表供 GUI 预览或 `--toc-format json`。每节点含 `raw_title`（原始标题行）、
    `level`、`class_name`、`lines`（[起, 止]，1-based 闭区间，含标题行）、`children`，
    超过 `depth` 的层级不带回来。
    """
    return [_entry(node, depth) for node in tree]


def load_toc(path: Path) -> list:
    """读目录树 JSON：解析并校验是列表，读不了或解不开一律转可读的 ValueError。"""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except OSError as e:
        raise ValueError(f"无法读取目录树文件：{e}") from e
    except json.JSONDecodeError as e:
        raise ValueError(f"目录树不是合法 JSON：{e}") from e
    if not isinstance(data, list):
        raise ValueError("目录树必须是 JSON 列表")
    return data


def tree_from_json(data: list, lines: list[str]) -> list[Node]:
    """`to_json` 的逆操作：目录树 JSON + 原始行 → 章节树。

    标题用 json 现值（界面编辑过就是编辑后的），正文按 `lines` 行范围从原始行切片，
    切完照常过清理与替换。行范围允许留空洞：没被任何节点覆盖的行不进书。
    标记 `deleted` 的节点不生成标题，正文并入前一个未删除的兄弟（没有则并入父节点，
    顶层最前方没有归宿的直接丢弃），未删除的子章节原地并入父节点。
    """
    tree: list[Node] = []
    for i, entry in enumerate(data, start=1):
        node = _node_from_entry(entry, lines, f"第 {i} 个节点")
        if node.deleted:
            # Top level has no parent to absorb the body: drop it, lift kept children.
            if tree:
                tree[-1].paragraphs.extend(node.paragraphs)
            tree.extend(node.children)
        else:
            tree.append(node)
    assign_anchors(tree)
    return tree


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
        "raw_title": node.raw_title,
        "level": node.level,
        "class_name": node.class_name,
        "lines": list(node.lines),
        "children": [_entry(c, depth) for c in node.children if c.level <= depth],
    }


def _node_from_entry(entry: object, lines: list[str], where: str) -> Node:
    """一个 JSON 节点 → `Node`；结构或行号不合法时抛指出位置的 ValueError。"""
    if not isinstance(entry, dict):
        raise ValueError(f"{where}不是 JSON 对象")
    title = entry.get("raw_title")
    level = entry.get("level")
    span = entry.get("lines")
    if not isinstance(title, str) or not title.strip():
        raise ValueError(f"{where}缺少标题（raw_title）")
    if not isinstance(level, int) or isinstance(level, bool) or not 0 <= level <= 6:
        raise ValueError(f"{where}的层级不合法：{level!r}")
    if (
        not isinstance(span, list)
        or len(span) != 2
        or not all(isinstance(n, int) and not isinstance(n, bool) for n in span)
    ):
        raise ValueError(f"{where}的行号不合法：{span!r}（应为 [起, 止]）")
    start, end = span
    if not 1 <= start <= end <= len(lines):
        raise ValueError(f"{where}的行号超出输入范围：{span}（输入共 {len(lines)} 行）")
    deleted = entry.get("deleted", False)
    if not isinstance(deleted, bool):
        raise ValueError(f"{where}的 deleted 只能是 true/false：{deleted!r}")
    children = entry.get("children", [])
    if not isinstance(children, list):
        raise ValueError(f"{where}的 children 不是列表")
    node = Node(
        title.strip(),
        level,
        str(entry.get("class_name") or f"level{level}"),
        raw_title=title.strip(),
        lines=(start, end),
        deleted=deleted,
    )
    node.children = [
        _node_from_entry(c, lines, f"{where} > 第 {j} 个子节点")
        for j, c in enumerate(children, start=1)
    ]
    node.paragraphs = _direct_body(node, lines)
    _dissolve_deleted(node)
    return node


def _direct_body(node: Node, lines: list[str]) -> list[str]:
    """直属正文：标题节点从标题行之后取到范围尽头；前言（level 0）的标题不在
    原文中，整段都是正文。有子节点时止于第一个子标题之前（与 parse() 一致）。
    """
    start, end = node.lines
    body_start = start if node.level == 0 else start + 1
    body_end = min(end, node.children[0].lines[0] - 1) if node.children else end
    return lines[body_start - 1 : body_end] if body_end >= body_start else []


def _dissolve_deleted(node: Node) -> None:
    """把标记删除的子节点并入 `node`：正文接在前一个未删除的兄弟之后（保持文档
    顺序，没有就接在 `node` 的直属正文后），未删除的子章节原地顶上。
    """
    kept: list[Node] = []
    for child in node.children:
        if not child.deleted:
            kept.append(child)
            continue
        target = kept[-1] if kept else node
        target.paragraphs.extend(child.paragraphs)
        kept.extend(child.children)  # its own deleted children were dissolved already
    node.children = kept
