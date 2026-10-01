"""目录的渲染与往返：缩进文本、扁平 JSON 列表，按格式选一种的 `render()`。

JSON 是 `--toc-only --toc-format json` 导出与 `--toc-file` 回喂之间的中间产物：按文档序
一行一个条目，只存原始标题（`raw_title`）、层级（`level`）与**标题行号**（`line`）——层级由
`level` 决定，嵌套不落盘，正文范围由相邻条目派生。标题的清理替换推迟到组装阶段。`to_json` /
`tree_from_json` 互为逆操作，中间可以插一步人工编辑（改标题、删除线标记、合并章节）。
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

from .config import DEFAULTS, FORMATS
from .parser import Node, TreeBuilder, assign_anchors


def _visible(
    nodes: list[Node], depth: int, indent: int = 0
) -> Iterator[tuple[Node, int]]:
    """按文档序遍历该进目录的节点，连同它相对顶层的缩进层数。

    `depth` 按绝对 level 卡；缩进按相对层数给——顶层不管自己是 h2 还是 h4 都不缩进，
    其后每深一层加一级。缩进只是给人看的，level 本身在 json 条目里，文本不必能还原
    回目录树。
    """
    for node in nodes:
        if node.level > depth:
            continue
        yield node, indent
        yield from _visible(node.children, depth, indent + 1)


def render(tree: list[Node], depth: int, fmt: str) -> str:
    """按格式渲染目录正文，供 `--toc-only` 输出。"""
    if fmt == "json":
        return json.dumps(to_json(tree, depth), ensure_ascii=False, indent=2)
    if fmt == "text":
        return to_text(tree, depth)
    raise ValueError(f"目录格式只能是 {'/'.join(FORMATS)}，收到：{fmt!r}")


def to_json(tree: list[Node], depth: int = DEFAULTS.toc_depth) -> list[dict]:
    """转扁平 JSON 列表，供 `--toc-only --toc-format json` 导出与 `tree_from_json`
    回喂。文档序一行一个条目，含 `raw_title`（原始标题行）、`level`、`class_name`、
    `line`（标题行号，1-based）；超过 `depth` 的层级不导出。
    界面要的是 `Node` 树本身，不经过这里。
    """
    return [_entry(node) for node, _ in _visible(tree, depth)]


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
    """扁平条目列表 + 原始行 → 章节树。`tree_from_json` 的逆操作是 `to_json`。

    `data` 是 Python 结构（`to_json` 的产物，或 GUI 目录面板维护的同形列表），
    **不是 JSON 文本**——文本形态由 `load_toc()` 先解析成结构再传进来。

    条目按行号顺序给出，层级由 `level` 栈式重建（与 `line` 无关）；直属正文取
    「本条目 `line` 之后到下一个条目的 `line` 之前」，末项到文件尾。标题用条目现值，
    切完照常过清理与替换。`deleted` 条目不生成标题：直属正文并入文档序上一个未删除
    条目（最前方没有归宿的丢弃），其未删除的子条目自动挂到更上层的未删除祖先。
    """
    nodes = [
        _node_from_entry(e, lines, f"第 {i} 个条目")
        for i, e in enumerate(data, start=1)
    ]
    for node, nxt in zip(nodes, [*nodes[1:], None]):
        # 正文：本标题行之后到下一项的标题行之前；末项到文件尾。
        # 前言/兜底（level 0）没有标题行，从自身 line 起就是正文。
        body_end = nxt.line - 1 if nxt else len(lines)
        body_start = node.line if node.level == 0 else node.line + 1
        node.paragraphs = (
            lines[body_start - 1 : body_end] if body_end >= body_start else []
        )
    tree = _rebuild(nodes)
    # level 0 在前言/兜底里固定用 anchor="preface"；多于一个会生成重名 xhtml，EPUB 损坏。
    level0 = [n for n in tree if n.level == 0]
    if len(level0) > 1:
        raise ValueError(
            f"目录树里只能有一个 level 0 条目（前言），收到 {len(level0)} 个"
        )
    assign_anchors(tree)
    return tree


def _rebuild(nodes: list[Node]) -> list[Node]:
    """重建层级并溶解 deleted 条目：文档序单遍。"""
    builder = TreeBuilder()
    for node in nodes:
        if node.deleted:
            # Body of a struck-out entry joins the closest kept one before it;
            # at the very front there is no such entry, so it is dropped.
            if builder.last is not None:
                builder.last.paragraphs.extend(node.paragraphs)
            continue
        builder.add(node)
    return builder.tree


def to_text(tree: list[Node], depth: int = DEFAULTS.toc_depth) -> str:
    """转缩进文本，一行一个标题，缩进按相对层数（见 `_visible`）。"""
    return "\n".join(
        f"{'  ' * indent}{node.title}" for node, indent in _visible(tree, depth)
    )


def _entry(node: Node) -> dict:
    entry = {
        "raw_title": node.raw_title,
        "level": node.level,
        "class_name": node.class_name,
        "line": node.line,
    }
    if node.deleted:
        entry["deleted"] = True  # omitted when false, to keep exports clean
    return entry


def _node_from_entry(entry: object, lines: list[str], where: str) -> Node:
    """一个 JSON 条目 → `Node`（直属正文随后统一切）；不合法时抛指出位置的 ValueError。"""
    if not isinstance(entry, dict):
        raise ValueError(f"{where}不是 JSON 对象")
    title = entry.get("raw_title")
    level = entry.get("level")
    line = entry.get("line")
    if not isinstance(title, str) or not title.strip():
        raise ValueError(f"{where}缺少标题（raw_title）")
    if not isinstance(level, int) or isinstance(level, bool) or not 0 <= level <= 6:
        raise ValueError(f"{where}的层级不合法：{level!r}")
    if not isinstance(line, int) or isinstance(line, bool):
        raise ValueError(f"{where}的行号不合法：{line!r}（应为整数行号）")
    if not 1 <= line <= len(lines):
        raise ValueError(f"{where}的行号超出输入范围：{line}（输入共 {len(lines)} 行）")
    deleted = entry.get("deleted", False)
    if not isinstance(deleted, bool):
        raise ValueError(f"{where}的 deleted 只能是 true/false：{deleted!r}")
    class_name = entry.get("class_name", "")
    if not isinstance(class_name, str):
        raise ValueError(f"{where}的 class_name 不合法：{class_name!r}")
    return Node(
        title.strip(),
        level,
        class_name,
        raw_title=title.strip(),
        line=line,
        deleted=deleted,
    )
