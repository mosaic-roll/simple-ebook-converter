"""目录的渲染与往返：缩进文本、扁平 JSON 列表，按格式选一种的 `render()`。

JSON 是 GUI 预览与 `--toc-file` 共用的中间产物：按文档序一行一个条目，只存原始
标题（`raw_title`）、层级（`level`）与完整行号范围（`lines`，含子孙）——层级由
`level` 决定，嵌套不落盘。标题的清理替换推迟到组装阶段。`to_json` / `tree_from_json`
互为逆操作，中间可以插一步人工编辑（改标题、删除线标记、合并章节）。
"""

from __future__ import annotations

import json
from pathlib import Path

from .config import DEFAULTS, Node
from .parser import assign_anchors, walk

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
    """转扁平 JSON 列表供 GUI 预览或 `--toc-format json`。文档序一行一个条目，含
    `raw_title`（原始标题行）、`level`、`class_name`、`lines`（[起, 止]，1-based
    闭区间，完整覆盖含子孙）；超过 `depth` 的层级不导出。
    """
    return [_entry(node) for node in walk(tree) if node.level <= depth]


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
    """`to_json` 的逆操作：扁平条目列表 + 原始行 → 章节树。

    条目按行号顺序给出，层级由 `level` 栈式重建（与 `lines` 无关）；直属正文取
    「标题行之后到下一个条目标题之前」。标题用 json 现值，切完照常过清理与替换。
    `deleted` 条目不生成标题：直属正文并入文档序上一个未删除条目（最前方没有
    归宿的丢弃），其未删除的子条目自动挂到更上层的未删除祖先。
    """
    nodes = [_node_from_entry(e, lines, f"第 {i} 个条目") for i, e in enumerate(data, start=1)]
    for node, nxt in zip(nodes, [*nodes[1:], None]):
        # Direct body runs to the next heading (whatever its level), bounded by own span.
        body_end = min(node.lines[1], nxt.lines[0] - 1) if nxt else node.lines[1]
        start = node.lines[0] if node.level == 0 else node.lines[0] + 1
        node.paragraphs = lines[start - 1 : body_end] if body_end >= start else []
    tree = _rebuild(nodes)
    assign_anchors(tree)
    return tree


def _rebuild(nodes: list[Node]) -> list[Node]:
    """栈式重建层级并溶解 deleted 条目：文档序单遍。"""
    tree: list[Node] = []
    stack: list[Node] = []
    last: Node | None = None  # closest kept entry in document order
    for node in nodes:
        if node.deleted:
            if last is not None:
                last.paragraphs.extend(node.paragraphs)
            continue
        while stack and stack[-1].level >= node.level:
            stack.pop()
        (stack[-1].children if stack else tree).append(node)
        if node.level > 0:  # the preface (level 0) holds only its own paragraphs
            stack.append(node)
        last = node
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


def _entry(node: Node) -> dict:
    entry = {
        "raw_title": node.raw_title,
        "level": node.level,
        "class_name": node.class_name,
        "lines": list(node.lines),
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
    return Node(
        title.strip(),
        level,
        str(entry.get("class_name") or f"level{level}"),
        raw_title=title.strip(),
        lines=(start, end),
        deleted=deleted,
    )
