from __future__ import annotations

from .cleaner import clean_lines
from .config import Config, Node
from .parser import ParseStats, parse, walk
from .replace import apply, apply_lines, compile_rules


def process(lines: list[str], cfg: Config, fallback_title: str) -> tuple[list[Node], ParseStats]:
    """统一处理管线：校验 → 切分 → 清理 → 替换（标题与正文）。

    标题替换后存在 node.title，原始标题保留在 node.raw_title。
    正则只编译一次，避免对每章反复编译。
    """
    cfg.validate()
    tree, stats = parse(
        lines,
        cfg.levels,
        max_title_len=cfg.max_title_len,
        preface_title=cfg.preface_title,
        fallback_title=fallback_title,
        no_volume=cfg.no_volume,
    )
    if not cfg.no_clean:
        for node in walk(tree):
            node.paragraphs = clean_lines(node.paragraphs)
    if cfg.replacements:
        compiled = compile_rules(cfg.replacements)
        for node in walk(tree):
            node.title = apply(node.title, cfg.replacements, compiled)
            node.paragraphs = apply_lines(node.paragraphs, cfg.replacements, compiled)
    return tree, stats