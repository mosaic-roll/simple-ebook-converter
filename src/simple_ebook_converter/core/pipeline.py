"""一次转换的完整流程：读输入、扫目录、变换、产出文件。

程序是无状态的：`resolve()` 补全参数后返回**新的** `Config`，`read_book()` 把结果装进
`Book`；产出方式由 `cfg` 上的 `toc_only` / `dump_css` 决定，所以这里没有「产出类型」
参数，也没有需要前端记住的调用顺序。

变换分两个阶段：`scan_toc()` 从原始行扫出目录树（原始标题 + 标题行号），`process()`
再对树做清理与替换。目录树文件（`cfg.toc_file`）就是两阶段之间的契约——正常流程在
内存里直接走完，`--toc-file` 则让第一阶段的结果可被人工编辑后从文件读回。
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, replace
from pathlib import Path

from .builder import build_css, build_epub, builtin_css, escape
from .cleaner import clean_lines
from .config import Config
from .encoding import EncodingError, read_lines
from .mediatypes import find_cover
from .meta import resolve_metadata
from .parser import Node, ParseStats, parse, walk
from .replace import Replacer, Rule, replacers_by_stage
from .toc import load_toc, render, tree_from_json


@dataclass(frozen=True)
class Book:
    """读进来并切分好的一本书。`cfg` 是补全过封面与书名/作者的那一份。"""

    cfg: Config
    tree: list[Node]
    stats: ParseStats
    encoding: str


def resolve(cfg: Config) -> Config:
    """补全封面与书名/作者，返回新的 `Config`（不改传入的那一个）。

    顺序不能调换：封面自动发现要在 `validate()` 之前（否则 validate 只看得到 `None`），
    元数据猜测要在切分之前（一条标题都没命中时要用书名当章节名）。
    """
    cover = cfg.cover
    if cover is None and cfg.input is not None:
        cover = find_cover(cfg.input)
    title, author = cfg.title, cfg.author
    if cfg.input is not None:
        title, author = resolve_metadata(cfg.input, title, author)
    resolved = replace(cfg, cover=cover, title=title, author=author)
    resolved.validate()
    return resolved


def scan_toc(lines: list[str], cfg: Config) -> tuple[list[Node], ParseStats]:
    """阶段一：从原始行扫出目录树（原始标题 + 标题行号），不做清理与替换。

    `cfg.toc_file` 给了就跳过正则解析，按目录树文件构树（可经界面编辑），
    卷/章/节正则与 `max_title_len` 在这一形态下都不参与。
    """
    if cfg.toc_file is not None:
        tree = tree_from_json(load_toc(cfg.toc_file), lines)
        return tree, _stats_from_tree(tree, len(lines))
    return parse(
        lines,
        cfg.levels,
        max_title_len=cfg.max_title_len,
        preface_title=cfg.preface_title,
        fallback_title=cfg.book_title,
    )


def _stats_from_tree(tree: list[Node], total_lines: int) -> ParseStats:
    """目录树文件没有切分过程，统计信息从树本身数出来。"""
    stats = ParseStats(total_lines=total_lines)
    for node in walk(tree):
        if node.level == 0:
            stats.has_preface = True
            continue
        stats.level_counts[node.level] = stats.level_counts.get(node.level, 0) + 1
        stats.max_level = max(stats.max_level, node.level)
    return stats


def process(lines: list[str], cfg: Config) -> tuple[list[Node], ParseStats]:
    """把原始行变成章节树：扫目录（阶段一）→ 清理 → 替换标题（阶段二）。

    替换只作用于标题：`raw` 规则改原始标题，结果写进 `node.title`（目录/元数据/正文页
    都用它）；随后转义，`html` 规则在转义结果上再替换一次，写进 `node.title_html`
    供书页标题原样输出。只动 `lines` 与新节点。
    """
    tree, stats = scan_toc(lines, cfg)
    raw_replacer, html_replacer = replacers_by_stage(cfg.replacements)
    for node in walk(tree):
        if cfg.clean:
            node.paragraphs = clean_lines(node.paragraphs)
        result = _transform_title(node, raw_replacer, html_replacer)
        node.title = result.title
        node.title_html = result.title_html
    return tree, stats


@dataclass(frozen=True)
class TitleResult:
    """一个标题过完两阶段替换后的结果，供界面预览目录。"""

    level: int
    raw_title: str
    #: `raw` 阶段替换后的纯文本，目录与元数据用这个
    title: str
    #: 转义 + `html` 阶段替换后的书页标题
    title_html: str
    #: `html` 阶段有过命中（哪怕替换文本与原文相同）；界面据此把**整行**标蓝
    html_hit: bool


def _transform_title(node: Node, raw: Replacer, html: Replacer) -> TitleResult:
    """一个标题过完整条链：raw 替换 → 转义 → html 替换。

    `process()` 与 `preview_titles()` 共用这一条。两个替换器由调用方先经
    `replacers_by_stage()` 分好（循环 N 条标题只分流一次），故不对外。
    """
    title = raw.text(node.title)
    title_html, hit = html.apply(escape(title))
    return TitleResult(node.level, node.raw_title, title, title_html, hit)


def preview_titles(tree: list[Node], replacements: Iterable[Rule]) -> list[TitleResult]:
    """整棵目录树 → 每个标题的替换结果，按文档序扁平返回（与 `walk` 同序）。

    界面单独调它预览（传入阶段一扫出来的树，规则改动后重调即可），纯函数不动传入的
    树。`html_hit` 为真表示被 html 规则动过，界面把整行染蓝并显示 `title_html`；
    没命中就显示未转义的 `title`——那时 `title_html` 只是转义结果。
    """
    raw_replacer, html_replacer = replacers_by_stage(replacements)
    return [_transform_title(node, raw_replacer, html_replacer) for node in walk(tree)]


def read_book(cfg: Config) -> Book:
    """读输入文件并切分。文件读不了、解不开或没有正文时抛 `ValueError`。"""
    if cfg.input is None:
        raise ValueError("缺少输入文件")
    resolved = resolve(cfg)
    lines, used = read_input(resolved)
    tree, stats = process(lines, resolved)
    if not any(node.paragraphs for node in walk(tree)):
        raise ValueError(f"文件里没有可生成的内容：{resolved.input.name}")
    return Book(resolved, tree, stats, used)


def read_input(cfg: Config) -> tuple[list[str], str]:
    """读输入文件并探测编码，读不了或解不开转可读的 ValueError。

    `read_book()`（完整组装）与 GUI 预览（只跑阶段一）共用这一步；调用方需先保证
    `cfg.input` 不为 `None`。与 `encoding.decode` 的分工：那边只解字节，这里管整个
    读文件。
    """
    try:
        return read_lines(cfg.input, cfg.encoding)
    except EncodingError as e:
        raise ValueError(str(e)) from e
    except OSError as e:
        raise ValueError(f"无法读取输入文件：{e}") from e


def toc_text(book: Book) -> str:
    """目录正文，按 `cfg.toc_format` 与 `cfg.toc_depth` 渲染。"""
    return render(book.tree, book.cfg.toc_depth, book.cfg.toc_format)


def write_toc(book: Book) -> Path:
    """把目录写到 `cfg.out`。"""
    return write_text(_target(book.cfg.out), toc_text(book) + "\n", book.cfg.overwrite)


def write_epub(book: Book) -> Path:
    """组装并写出 EPUB，路径取 `cfg.out`，留空则与输入同名。返回落盘路径。"""
    target = _epub_path(book.cfg)
    _guard_overwrite(target, book.cfg.overwrite)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        build_epub(book.cfg, book.tree, build_css(book.cfg), target)
    except (OSError, ValueError) as e:
        raise ValueError(f"无法生成 EPUB：{e}") from e
    return target


def write_css(cfg: Config) -> Path:
    """把内置 CSS 模板写到 `cfg.dump_css`。只用排版参数，不必读输入。

    导出的是 `builtin_css()`（不受 `--css-file` / `--css-append` 影响，方便当样式表起点）。
    格式校验（字体、封面）照样走 `Config.validate()`：参数错在哪，哪种产出方式都该报。
    """
    if not cfg.dump_css:
        raise ValueError("缺少 CSS 输出路径")
    cfg.validate()
    return write_text(_target(cfg.dump_css), builtin_css(cfg), cfg.overwrite)


def write_text(path: Path, text: str, overwrite: bool = True) -> Path:
    """写文本产物：目录、CSS、界面上导出的规则 JSON。"""
    _guard_overwrite(path, overwrite)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    except OSError as e:
        raise ValueError(f"无法写入 {path}：{e}") from e
    return path


def _epub_path(cfg: Config) -> Path:
    """EPUB 落盘路径：`out` 留空取输入名，缺 `.epub` 后缀就补上。"""
    if cfg.out is None:
        return Path(cfg.input).with_suffix(".epub")
    path = _target(cfg.out)
    return (
        path if path.suffix.lower() == ".epub" else path.with_name(path.name + ".epub")
    )


def _target(out: str | Path) -> Path:
    path = Path(str(out))
    if not path.name:
        raise ValueError("缺少输出路径")
    return path


def _guard_overwrite(path: Path, overwrite: bool) -> None:
    if not overwrite and path.exists():
        raise ValueError(f"输出文件已存在：{path}（当前设置为不覆盖）")
