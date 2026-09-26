"""唯一处理管线：封面自动发现 → 校验 → 元数据 → 切分 → 清理 → 替换。"""

from __future__ import annotations

from pathlib import Path

from .cleaner import clean_lines
from .config import Config, Node
from .mediatypes import find_cover
from .meta import resolve_metadata
from .parser import ParseStats, parse, walk
from .replace import replacers_by_scope


def process(lines: list[str], cfg: Config) -> tuple[list[Node], ParseStats]:
    """把原始行变成章节树，并把猜出来的封面与书名/作者写回 `cfg`。

    顺序不能调换：封面自动发现要在 `validate()` 之前（否则 validate 只看得到
    `None`），元数据猜测要在切分之前（一条标题都没命中时要用书名当章节名）。因此
    调用方要在 `process()` 之后才去读 `cfg.cover` / `cfg.title` / `cfg.author`。
    """
    if cfg.cover is None and cfg.input is not None:
        cfg.cover = find_cover(Path(cfg.input))
    cfg.validate()
    if cfg.input is not None:
        cfg.title, cfg.author = resolve_metadata(cfg.input, cfg.title, cfg.author)
    tree, stats = parse(
        lines,
        cfg.levels,
        max_title_len=cfg.max_title_len,
        preface_title=cfg.preface_title,
        fallback_title=cfg.book_title,
        volume_titles=cfg.volume_titles,
    )
    titles, bodies = replacers_by_scope(cfg.replacements)
    for node in walk(tree):
        if cfg.clean:
            node.paragraphs = clean_lines(node.paragraphs)
        node.title = titles.text(node.title)
        node.paragraphs = bodies.lines(node.paragraphs)
    return tree, stats
