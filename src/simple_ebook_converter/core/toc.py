"""目录的渲染与往返：缩进文本、扁平 JSON 列表，按格式选一种的 `render()`。

JSON 是 `--toc-only --toc-format json` 导出与 `--toc-file` 回喂之间的中间产物：按文档序
一行一个条目，只存原始标题（`raw_title`）、层级（`level`）与**标题行号**（`line`）——层级由
`level` 决定，嵌套不落盘，正文范围由相邻**保留**条目派生。标题的清理替换推迟到组装阶段。
`to_json` / `tree_from_json` 互为逆操作，中间可以插一步人工编辑（改标题、删除线标记、
合并章节）。`deleted` 条目不生成标题节点：其行号被完全跳过，标题行与直属段落自然并入
前一个保留条目的正文；文档序最前的若干条目被删时，这些散落行归到前言。
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
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as e:
        raise ValueError(f"无法读取目录树文件：{e}") from e
    except json.JSONDecodeError as e:
        raise ValueError(f"目录树不是合法 JSON：{e}") from e
    if not isinstance(data, list):
        raise ValueError("目录树必须是 JSON 列表")  # noqa: TRY004  # 用户数据校验统一抛 ValueError
    return data


def tree_from_json(
    data: list,
    lines: list[str],
    preface_title: str = DEFAULTS.preface_title,
) -> list[Node]:
    """扁平条目列表 + 原始行 → 章节树。`tree_from_json` 的逆操作是 `to_json`。

    `data` 是 Python 结构（`to_json` 的产物，或 GUI 目录面板维护的同形列表），
    **不是 JSON 文本**——文本形态由 `load_toc()` 先解析成结构再传进来。

    条目按行号顺序给出，层级由 `level` 栈式重建（与 `line` 无关）。`deleted`
    条目**不生成标题节点**：它没有对应的 `Node`，其行号被完全跳过——正文范围
    由相邻**保留**条目的 `line` 派生，所以被删条目的标题行与直属段落自然并入
    前一个保留条目的正文。文档序最前的若干条目被删时前面没有可并的条目，
    这些散落行归到前言；一条未删条目都没有时整篇作为前言。
    """
    # 两阶段：先构建 Node（只含元数据，paragraphs 为空），再按 kept 列表派生正文范围。
    # 节点对象与正文切片解耦，这样 deleted 过滤只需在构建阶段跳过，
    # 不用在切片阶段额外处理。
    kept: list[Node] = []
    for i, e in enumerate(data, start=1):
        fields = check_entry(e, f"第 {i} 个条目", lines)
        if fields is None:
            continue
        kept.append(Node(**fields))

    if not kept:
        # 所有条目都被删——整篇作为前言
        tree: list[Node] = [
            Node(
                preface_title,
                0,
                "chapter",
                paragraphs=list(lines),
                raw_title=preface_title,
                line=1,
            )
        ]
        assign_anchors(tree)
        return tree

    for node, nxt in zip(kept, [*kept[1:], None]):
        # 正文范围：本条目 line 之后到下一个**保留**条目的 line 之前；末项到文件尾。
        # 被删条目的行号被跨过，它们的内容自动并进前一个保留条目的正文范围。
        body_end = nxt.line - 1 if nxt else len(lines)
        body_start = node.line if node.level == 0 else node.line + 1
        node.paragraphs = (
            lines[body_start - 1 : body_end] if body_end >= body_start else []
        )

    builder = TreeBuilder()
    for node in kept:
        builder.add(node)
    tree = builder.tree

    first = kept[0]
    # 首个保留条目的 line 之前还有行：文档序最前的若干条目被删，这些散落行
    # 归到前言。level 0 条目本身的 line 就是正文首行，它前面没有"标题行"可跳，
    # 所以这一支不触发。
    if first.level > 0 and first.line > 1:
        tree.insert(
            0,
            Node(
                preface_title,
                0,
                "chapter",
                paragraphs=lines[0 : first.line - 1],
                raw_title=preface_title,
                line=1,
            ),
        )

    # level 0 固定用 anchor="preface"；多于一个会生成重名 xhtml，EPUB 损坏。
    level0 = [n for n in tree if n.level == 0]
    if len(level0) > 1:
        raise ValueError(
            f"目录树里只能有一个 level 0 条目（前言），收到 {len(level0)} 个"
        )
    assign_anchors(tree)
    return tree


def check_entry(
    entry: dict, where: str, lines: list[str] | None = None
) -> dict | None:
    """校验一个扁平条目，返回建 `Node` 要的字段；`deleted` 条目返回 `None`。

    `tree_from_json` 与 GUI 的目录面板导入共用这一份规则，避免各写一遍后漂移。

    `lines` 给定时额外校验行号不越界。GUI 导入拿不到正文（用户还没选文件），传 `None`：
    那时只能查行号是不是正整数，上界留给生成时的 `tree_from_json` 兜。

    `deleted` 条目不建节点、不参与正文范围计算，也就不查行号——但仍要确认它是布尔值，
    免得把 `"yes"` 之类误当 False。
    """
    if not isinstance(entry, dict):
        raise ValueError(f"{where}不是 JSON 对象")  # noqa: TRY004
    deleted = entry.get("deleted", False)
    if not isinstance(deleted, bool):
        raise ValueError(f"{where}的 deleted 只能是 true/false：{deleted!r}")  # noqa: TRY004  # 用户数据校验统一抛 ValueError
    if deleted:
        return None
    title = entry.get("raw_title")
    level = entry.get("level")
    line = entry.get("line")
    class_name = entry.get("class_name", "")
    if not isinstance(title, str) or not title.strip():
        raise ValueError(f"{where}缺少标题（raw_title）")
    if not isinstance(level, int) or isinstance(level, bool) or not 0 <= level <= 6:
        raise ValueError(f"{where}的层级不合法：{level!r}")
    if not isinstance(class_name, str):
        raise ValueError(f"{where}的 class_name 不合法：{class_name!r}")  # noqa: TRY004  # 同上
    # level 0 的标题是合成的，class 跟扫描路径一致按章级渲染，不看文件里的值。
    if level == 0:
        class_name = "chapter"
    if not isinstance(line, int) or isinstance(line, bool):
        raise ValueError(f"{where}的行号不合法：{line!r}（应为整数行号）")  # noqa: TRY004  # 用户数据校验统一抛 ValueError
    if lines is not None and not 1 <= line <= len(lines):
        raise ValueError(f"{where}的行号超出输入范围：{line}（输入共 {len(lines)} 行）")
    return {
        "title": title.strip(),
        "level": level,
        "class_name": class_name,
        "raw_title": title.strip(),
        "line": line,
    }


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
        entry["deleted"] = True  # false 时不写这个键，导出的 JSON 干净些
    return entry
