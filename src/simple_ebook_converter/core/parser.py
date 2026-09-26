"""按标题正则把原始行切分成章节树。

切分在清理之前进行，标题检测用的是原始行，这样空行与缩进等信息不会先被抹掉；
标题行本身保存时去掉首尾空白。
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass, field

from .config import (
    DEFAULT_MAX_TITLE_LEN,
    DEFAULT_PREFACE_TITLE,
    FALLBACK_TITLE,
    LevelRule,
    Node,
)


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
    max_title_len: int = DEFAULT_MAX_TITLE_LEN,
    preface_title: str = DEFAULT_PREFACE_TITLE,
    fallback_title: str = FALLBACK_TITLE,
    volume_titles: bool = True,
) -> tuple[list[Node], ParseStats]:
    """把行切分为章节树，返回 (顶层节点列表, 统计信息)。

    正文段落跟随最近的标题；首个标题之前的段落归到 `preface_title`；一条标题都没
    命中时整篇作为一章，标题用 `fallback_title`。
    """
    rules = sorted(
        (r for r in levels if r.active and (volume_titles or r.class_name != "volume")),
        key=lambda r: r.level,
    )
    if not rules:
        raise NoEnabledRulesError("没有启用的标题规则：卷/章/节至少要有一个非空正则")
    compiled = [(r, re.compile(r.pattern)) for r in rules]

    stats = ParseStats(total_lines=len(lines))
    tree: list[Node] = []
    stack: list[Node] = []
    preface: list[str] = []

    for line in lines:
        title = line.strip()
        rule = _match(title, compiled, max_title_len) if title else None
        if rule is None:
            (stack[-1].paragraphs if stack else preface).append(line)
            continue
        while stack and stack[-1].level >= rule.level:
            stack.pop()
        parent = stack[-1] if stack else None
        node = Node(title, rule.level, rule.class_name or f"level{rule.level}", raw_title=title)
        (parent.children if parent else tree).append(node)
        stack.append(node)
        stats.level_counts[rule.level] = stats.level_counts.get(rule.level, 0) + 1
        stats.max_level = max(stats.max_level, rule.level)

    _wrap_preface(tree, preface, preface_title, fallback_title, stats)
    _assign_anchors(tree)
    return tree, stats


def _match(
    title: str, compiled: list[tuple[LevelRule, re.Pattern[str]]], max_title_len: int
) -> LevelRule | None:
    """超长的行即使命中正则也当正文。"""
    if len(title) > max_title_len:
        return None
    for rule, pattern in compiled:
        if pattern.match(title):
            return rule
    return None


def _wrap_preface(
    tree: list[Node],
    preface: list[str],
    preface_title: str,
    fallback_title: str,
    stats: ParseStats,
) -> None:
    if not preface:
        return
    if tree:
        stats.has_preface = True
        tree.insert(0, Node(preface_title, 0, "preface", paragraphs=preface, raw_title=preface_title))
    else:
        tree.append(Node(fallback_title, 2, "chapter", paragraphs=preface, raw_title=fallback_title))


def walk(nodes: list[Node]) -> Iterator[Node]:
    """先序遍历章节树。"""
    for node in nodes:
        yield node
        yield from walk(node.children)


def _assign_anchors(tree: list[Node]) -> None:
    """给每个节点分配书内文件名（`p0001` 递增，前言固定 `preface`）。"""
    index = 0
    for node in walk(tree):
        if node.level == 0:
            node.anchor = "preface"
            continue
        index += 1
        node.anchor = f"p{index:04d}"
