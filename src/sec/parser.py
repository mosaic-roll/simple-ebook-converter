from __future__ import annotations

import re
from dataclasses import dataclass, field

from .config import LevelRule, Node


@dataclass
class ParseStats:
    level_counts: dict[int, int] = field(default_factory=dict)
    max_level: int = 0
    has_preface: bool = False
    total_lines: int = 0
    title_lines: int = 0
    warnings: list[str] = field(default_factory=list)


class NoEnabledRulesError(Exception):
    pass


def _append(stack: list[Node], preface: list[str], line: str) -> None:
    if stack:
        stack[-1].paragraphs.append(line)
    else:
        preface.append(line)


def parse(
    lines: list[str],
    levels: list[LevelRule],
    max_title_len: int = 35,
    preface_title: str = "前言",
    fallback_title: str = "未命名",
    no_volume: bool = False,
) -> tuple[list[Node], ParseStats]:
    """按标题规则把行切分为章节树。

    返回 (顶层节点列表, 统计信息)。preface 有内容时位于列表最前。
    """
    rules = [l for l in levels if l.active and not (no_volume and l.cls == "volume")]
    rules.sort(key=lambda l: l.level)
    if not rules:
        raise NoEnabledRulesError("没有启用的标题规则")

    compiled = [(r, re.compile(r.pattern)) for r in rules]
    stats = ParseStats(total_lines=len(lines))
    preface_paras: list[str] = []
    stack: list[Node] = []
    tree: list[Node] = []

    for line in lines:
        text = line.strip()
        hit: LevelRule | None = None
        if text and len(text) <= max_title_len:
            for rule, pat in compiled:
                if pat.match(text):
                    hit = rule
                    break
        if hit is None:
            _append(stack, preface_paras, line)
            continue

        while stack and stack[-1].level >= hit.level:
            stack.pop()
        parent = stack[-1] if stack else None
        node = Node(title=text, level=hit.level, cls=hit.cls or f"level{hit.level}")
        if parent is None:
            tree.append(node)
        else:
            parent.children.append(node)
        stack.append(node)
        stats.title_lines += 1
        stats.level_counts[hit.level] = stats.level_counts.get(hit.level, 0) + 1
        stats.max_level = max(stats.max_level, hit.level)

    has_titles = bool(tree)
    if not has_titles and preface_paras:
        tree = [
            Node(title=fallback_title, level=2, cls="chapter", paragraphs=preface_paras)
        ]
        preface_paras = []
    if has_titles and preface_paras:
        stats.has_preface = True
        tree.insert(0, Node(title=preface_title, level=0, cls="preface", paragraphs=preface_paras))

    _assign_anchors(tree)
    return tree, stats


def _assign_anchors(tree: list[Node]) -> None:
    counter = 0
    for node in _walk(tree):
        if node.level == 0:
            node.anchor = "preface"
            continue
        counter += 1
        node.anchor = f"p{counter:04d}"


def _walk(nodes: list[Node]):
    for node in nodes:
        yield node
        yield from _walk(node.children)