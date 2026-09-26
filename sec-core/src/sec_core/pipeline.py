from __future__ import annotations

from pathlib import Path

from .cleaner import clean_lines
from .config import Config, Node
from .meta import resolve_metadata
from .parser import ParseStats, parse, walk
from .replace import apply, apply_lines, compile_rules

_FALLBACK_TITLE = "未命名"


def fallback_title(cfg: Config) -> str:
    """一条标题都没命中时，整篇作为一章时该用的标题。

    显式书名 → 输入文件名 → 「未命名」。`process()` 会先补好 `cfg.title`，
    所以正常路径下走的是第一档。
    """
    if cfg.title:
        return cfg.title
    if cfg.input is not None:
        return Path(str(cfg.input)).stem
    return _FALLBACK_TITLE


def process(lines: list[str], cfg: Config) -> tuple[list[Node], ParseStats]:
    """统一处理管线：校验 → 补元数据 → 切分 → 清理 → 替换（标题与正文）。

    这是 core 唯一的总入口，两个前端都只调它，因此下面这些策略只需实现一次，
    不用在 CLI / GUI 各写一遍：

    - `cfg.validate()` 先拦下取值范围错误；
    - `resolve_metadata()` 按 `cfg.input` 的文件名猜书名/作者（显式值优先），
      **结果写回 `cfg`**，供之后的 `build_epub()` 读取，所以要在 process 之后
      才去用 `cfg.title` / `cfg.author`；
    - 没有任何标题命中时，整篇归到 `fallback_title()` 选出的一章；
    - 标题替换后存在 `node.title`，原始标题保留在 `node.raw_title`；
    - 替换用的正则在整批文本上只编译一次。
    """
    cfg.validate()
    if cfg.input is not None:
        cfg.title, cfg.author = resolve_metadata(cfg.input, cfg.title, cfg.author)
    tree, stats = parse(
        lines,
        cfg.levels,
        max_title_len=cfg.max_title_len,
        preface_title=cfg.preface_title,
        fallback_title=fallback_title(cfg),
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
