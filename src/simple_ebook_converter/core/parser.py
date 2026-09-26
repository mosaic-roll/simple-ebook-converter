from __future__ import annotations

import re
from dataclasses import dataclass, field

from .config import LevelRule, Node, config_defaults

#: 直接调用 parse() 时不传这些参数就取 Config 的默认值，避免第三份字面量
_DEFAULTS = config_defaults()


@dataclass
class ParseStats:
    level_counts: dict[int, int] = field(default_factory=dict)
    max_level: int = 0
    has_preface: bool = False
    total_lines: int = 0
    title_lines: int = 0
    warnings: list[str] = field(default_factory=list)


class NoEnabledRulesError(ValueError):
    pass


def _append(stack: list[Node], preface: list[str], line: str) -> None:
    if stack:
        stack[-1].paragraphs.append(line)
    else:
        preface.append(line)


def parse(
    lines: list[str],
    levels: list[LevelRule],
    max_title_len: int = _DEFAULTS["max_title_len"],
    preface_title: str = _DEFAULTS["preface_title"],
    fallback_title: str = "未命名",
    no_volume: bool = False,
) -> tuple[list[Node], ParseStats]:
    """按标题规则把行切分为章节树。

    返回 (顶层节点列表, 统计信息)。preface 有内容时位于列表最前。
    """
    rules = [l for l in levels if l.active and not (no_volume and l.class_name == "volume")]
    rules.sort(key=lambda l: l.level)
    if not rules:
        raise NoEnabledRulesError("没有启用的标题规则：--volume/--chapter/--section 至少要有一个非空正则")

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
        node = Node(title=text, level=hit.level, class_name=hit.class_name or f"level{hit.level}", raw_title=text)
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
            Node(
                title=fallback_title,
                level=2,
                class_name="chapter",
                paragraphs=preface_paras,
                raw_title=fallback_title,
            )
        ]
        preface_paras = []
    if has_titles and preface_paras:
        stats.has_preface = True
        tree.insert(
            0,
            Node(
                title=preface_title,
                level=0,
                class_name="preface",
                paragraphs=preface_paras,
                raw_title=preface_title,
            ),
        )

    _assign_anchors(tree)
    return tree, stats


def _assign_anchors(tree: list[Node]) -> None:
    counter = 0
    for node in walk(tree):
        if node.level == 0:
            node.anchor = "preface"
            continue
        counter += 1
        node.anchor = f"p{counter:04d}"


def walk(nodes: list[Node]):
    """先序遍历章节树。"""
    for node in nodes:
        yield node
        yield from walk(node.children)
