"""按标题正则把原始行切分成章节树。

切分在清理之前进行，标题检测用的是原始行，这样空行与缩进等信息不会先被抹掉；
标题行本身保存时去掉首尾空白。
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass, field

from .config import DEFAULTS, LevelRule


@dataclass
class Node:
    """一个标题节点。`title` 是替换后的标题，`raw_title` 始终保留原文。

    `lines` 是节点在输入里的完整覆盖范围：1-based 闭区间 [标题行, 本章最后一行]，
    含全部子孙节点的行（子节点的范围落在父节点范围内）；直属正文不含子节点，
    组装时按「标题行之后、第一个子标题之前」切出。前言（level 0）的标题不在
    原文中，范围即正文。供目录树往返（`toc.to_json` / `toc.tree_from_json`）
    与预览定位用。
    """

    title: str
    level: int
    class_name: str = ""
    paragraphs: list[str] = field(default_factory=list)
    children: list["Node"] = field(default_factory=list)
    anchor: str = ""
    raw_title: str = ""
    #: 书页标题的 HTML 片段（转义 + html 阶段替换后的结果），由 `pipeline.process()` 填；
    #: 目录/元数据仍用纯文本的 `title`。
    title_html: str = ""
    lines: tuple[int, int] = (0, 0)
    #: Struck out in the GUI (`"deleted": true` in a `--toc-file` JSON); `toc.tree_from_json`
    #: dissolves such nodes into their neighbors. Never set by parse().
    deleted: bool = False


class TreeBuilder:
    """文档序逐个 `add()` 节点，按 level 栈式挂成树。

    `parse()`（正则扫描）与 `toc.tree_from_json()`（扁平条目回喂）共用这一套挂树
    逻辑；`last` 是文档序上最近挂入的节点，扫描时收正文、溶解删除线时并正文都用它。
    """

    def __init__(self) -> None:
        self.tree: list[Node] = []
        self._stack: list[Node] = []
        self.last: Node | None = None

    def add(self, node: Node) -> None:
        while self._stack and self._stack[-1].level >= node.level:
            self._stack.pop()
        (self._stack[-1].children if self._stack else self.tree).append(node)
        if node.level > 0:  # the preface (level 0) holds only its own paragraphs
            self._stack.append(node)
        self.last = node


@dataclass
class ParseStats:
    level_counts: dict[int, int] = field(default_factory=dict)
    max_level: int = 0
    has_preface: bool = False
    total_lines: int = 0


class NoEnabledRulesError(ValueError):
    """一条标题规则都没启用，无法切分。"""


def parse(
    lines: list[str],
    levels: list[LevelRule],
    *,
    fallback_title: str,
    max_title_len: int = DEFAULTS.max_title_len,
    preface_title: str = DEFAULTS.preface_title,
) -> tuple[list[Node], ParseStats]:
    """把行切分为章节树，返回 (顶层节点列表, 统计信息)。

    逐行找标题：先按级别从低到高试，同一级按 `levels` 的顺序试（前端把卷/章/节三条排
    在最前，用户写的额外层级按书写顺序跟在后面），第一条命中的规则说了算，同一行的其余
    规则不再试。超长的行（> `max_title_len`）直接按正文处理，不参与匹配。

    正文段落跟随最近的标题；首个标题之前的段落归到 `preface_title`；一条标题都没
    命中时整篇作为一章，标题用 `fallback_title`。不启用某层级就是把它的正则留空。
    每个节点同时记下它在输入里的行范围（`Node.lines`），供目录树往返与预览定位。
    """
    # 排序键只有级别，而排序是稳定的 → 同级保持 `levels` 的顺序，即上面的优先级
    rules = sorted((r for r in levels if r.active), key=lambda r: r.level)
    if not rules:
        raise NoEnabledRulesError("没有启用的标题规则：卷/章/节至少要有一个非空正则")
    compiled = [(r, re.compile(r.pattern)) for r in rules]

    stats = ParseStats(total_lines=len(lines))
    builder = TreeBuilder()
    preface: list[tuple[int, str]] = []

    for lineno, line in enumerate(lines, start=1):
        title = line.strip()
        # 超长行不可能是标题，直接归正文，连正则都不试
        rule = _match(title, compiled) if title and len(title) <= max_title_len else None
        if rule is None:
            if builder.last is not None:
                node = builder.last
                node.paragraphs.append(line)
                node.lines = (node.lines[0], lineno)
            else:
                preface.append((lineno, line))
            continue
        builder.add(
            Node(
                title,
                rule.level,
                rule.class_name,
                raw_title=title,
                lines=(lineno, lineno),
            )
        )
        stats.level_counts[rule.level] = stats.level_counts.get(rule.level, 0) + 1
        stats.max_level = max(stats.max_level, rule.level)

    _wrap_preface(builder.tree, preface, preface_title, fallback_title, stats)
    _full_spans(builder.tree)
    assign_anchors(builder.tree)
    return builder.tree, stats


def _full_spans(nodes: list[Node]) -> None:
    """Widen each node's span to cover all its descendants, so `Node.lines` is the
    full extent of the section it stands for (children live inside their parent).
    """
    for node in nodes:
        _full_spans(node.children)
        if node.children:
            end = max(node.lines[1], *(c.lines[1] for c in node.children))
            node.lines = (node.lines[0], end)


def _match(
    title: str, compiled: list[tuple[LevelRule, re.Pattern[str]]]
) -> LevelRule | None:
    """按顺序试规则，返回第一条命中的。调用方保证 `title` 非空且不超长。"""
    for rule, pattern in compiled:
        if pattern.match(title):
            return rule
    return None


def _wrap_preface(
    tree: list[Node],
    preface: list[tuple[int, str]],
    preface_title: str,
    fallback_title: str,
    stats: ParseStats,
) -> None:
    if not preface:
        return
    paragraphs = [line for _, line in preface]
    span = (preface[0][0], preface[-1][0])  # preface covers lines 1..first title
    if tree:
        stats.has_preface = True
        tree.insert(
            0,
            Node(
                preface_title,
                0,
                "preface",
                paragraphs=paragraphs,
                raw_title=preface_title,
                lines=span,
            ),
        )
    else:
        tree.append(
            Node(
                fallback_title,
                2,
                "chapter",
                paragraphs=paragraphs,
                raw_title=fallback_title,
                lines=span,
            )
        )


def walk(nodes: list[Node]) -> Iterator[Node]:
    """先序遍历章节树。"""
    for node in nodes:
        yield node
        yield from walk(node.children)


def assign_anchors(tree: list[Node]) -> None:
    """给每个节点分配书内文件名（`p0001` 递增，前言固定 `preface`）。"""
    index = 0
    for node in walk(tree):
        if node.level == 0:
            node.anchor = "preface"
            continue
        index += 1
        node.anchor = f"p{index:04d}"
