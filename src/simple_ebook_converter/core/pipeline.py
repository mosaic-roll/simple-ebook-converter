from __future__ import annotations

from pathlib import Path

from .cleaner import clean_lines
from .config import Config, Node
from .mediatypes import find_cover
from .meta import resolve_metadata
from .parser import ParseStats, parse, walk
from .replace import apply, apply_lines, compile_rules, split_by_scope

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
    """统一处理管线：补封面 → 校验 → 补元数据 → 切分 → 清理 → 替换。

    这是 core 唯一的总入口，两个前端都只调它，因此下面这些策略只需实现一次，
    不用在 CLI / GUI 各写一遍：

    - 没给封面时按输入文件同目录的 `cover.*` 自动找一张，结果**写回 `cfg`**；
      必须发生在 `cfg.validate()` 之前，否则 validate 只看得到 `None`；
    - `cfg.validate()` 接着拦下取值范围、日期与资源格式错误；
    - `resolve_metadata()` 按 `cfg.input` 的文件名猜书名/作者（显式值优先），
      **结果写回 `cfg`**，供之后的 `build_epub()` 读取，所以要在 process 之后
      才去用 `cfg.title` / `cfg.author`；
    - 没有任何标题命中时，整篇归到 `fallback_title()` 选出的一章；
    - 标题替换后存在 `node.title`，原始标题保留在 `node.raw_title`；
    - 替换按 `Rule.scope` 分流：标题规则只进 `node.title`，正文规则只进
      `node.paragraphs`，`scope="all"` 两边都进；正则在整批文本上只编译一次。
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
        fallback_title=fallback_title(cfg),
        no_volume=cfg.no_volume,
    )
    if not cfg.no_clean:
        for node in walk(tree):
            node.paragraphs = clean_lines(node.paragraphs)
    title_rules, body_rules = split_by_scope(cfg.replacements)
    if title_rules:
        compiled = compile_rules(title_rules)
        for node in walk(tree):
            node.title = apply(node.title, title_rules, compiled)
    if body_rules:
        compiled = compile_rules(body_rules)
        for node in walk(tree):
            node.paragraphs = apply_lines(node.paragraphs, body_rules, compiled)
    return tree, stats
