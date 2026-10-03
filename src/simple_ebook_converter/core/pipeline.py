"""一次转换的完整流程：读输入、扫目录、变换、产出文件。

程序是无状态的：`resolve()` 补全参数后返回**新的** `Config`，`read_book()` 把结果装进
`Book`；产出方式由 `cfg` 上的 `toc_only` / `dump_css` 决定，所以这里没有「产出类型」
参数，也没有需要前端记住的调用顺序。

变换分两个阶段：`scan_toc()` 从原始行扫出目录树（原始标题 + 标题行号），`process()`
再对树做清理与替换。阶段之间传的是**内容**：目录条目由前端经 `sources` 预加载成
`Sources.toc_entries` 传进来，所以两个阶段一次文件都不读。

本模块不读 `Config` 上的资源路径（`toc_file` / `cover` / `font` / `css_file` /
`css_append`）——那是 `sources.load_sources()` 的事。唯一的例外是 `write_css()`：
导出模板只需要内嵌字体的**文件名**，不读字节。
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field, replace
from pathlib import Path

from .builder import build_epub, builtin_css
from .cleaner import clean_lines, escape
from .config import Config
from .encoding import EncodingError, read_lines
from .meta import resolve_metadata
from .parser import Node, ParseStats, parse, walk
from .replace import Replacer, Rule, replacers_by_stage
from .sources import Sources
from .toc import render, tree_from_json
from .validation import validate_config


@dataclass(frozen=True)
class Book:
    """读进来并切分好的一本书。

    `cfg` 是补全过书名/作者的那一份；`sources` 是前端预加载的资源内容，产出阶段
    （`write_epub()`）从中取 CSS、字体与封面。
    """

    cfg: Config
    tree: list[Node]
    stats: ParseStats
    encoding: str
    #: 前端预加载的资源内容；默认为空 `Sources()`（无外部 CSS、无字体、无封面）
    sources: Sources = field(default_factory=Sources)


def resolve(cfg: Config) -> Config:
    """补全书名/作者，返回新的 `Config`（不改传入的那一个）。

    只做元数据两件事：封面处理由 `sources.cover_for()` / `load_sources()` 负责——
    它只认显式给出的路径，不碰文件系统做自动发现。元数据猜测要在切分之前
    （一条标题都没命中时要用书名当章节名）。
    """
    title, author = cfg.title, cfg.author
    if cfg.input is not None:
        title, author = resolve_metadata(cfg.input, title, author)
    resolved = replace(cfg, title=title, author=author)
    validate_config(resolved)
    return resolved


def scan_toc(
    lines: list[str],
    cfg: Config,
    entries: list[dict] | None = None,
) -> tuple[list[Node], ParseStats]:
    """阶段一：从原始行扫出目录树（原始标题 + 标题行号），不做清理与替换。

    `entries` 给了就跳过正则解析，按条目构树（可经界面编辑），卷/章/节正则与
    `max_title_len` 在这一形态下都不参与。条目来自 `Sources.toc_entries`：
    CLI 侧的 `--toc-file` 由 `load_sources()` 读成条目，GUI 侧是目录面板那份，
    所以这里**一次文件都不读**。
    """
    if entries is not None:
        tree = tree_from_json(entries, lines, cfg.preface_title)
        return tree, _stats_from_tree(tree, len(lines))
    return parse(
        lines,
        cfg.levels,
        max_title_len=cfg.max_title_len,
        preface_title=cfg.preface_title,
        fallback_title=cfg.book_title,
    )


def _stats_from_tree(tree: list[Node], total_lines: int) -> ParseStats:
    """目录条目没有切分过程，统计信息从树本身数出来。"""
    stats = ParseStats(total_lines=total_lines)
    for node in walk(tree):
        if node.level == 0:
            stats.has_preface = True
            continue
        stats.level_counts[node.level] = stats.level_counts.get(node.level, 0) + 1
        stats.max_level = max(stats.max_level, node.level)
    return stats


def process(
    lines: list[str],
    cfg: Config,
    entries: list[dict] | None = None,
) -> tuple[list[Node], ParseStats]:
    """把原始行变成章节树：扫目录（阶段一）→ 清理 → 替换标题（阶段二）。

    替换只作用于标题：`raw` 规则改原始标题，结果写进 `node.title`（目录/元数据/正文页
    都用它）；随后转义，`html` 规则在转义结果上再替换一次，写进 `node.title_html`
    供书页标题原样输出。只动 `lines` 与新节点。
    """
    tree, stats = scan_toc(lines, cfg, entries)
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

    raw 规则的语义是「匹配原文」，所以读 `node.raw_title` 而不是 `node.title`：
    即便传入的树已经 `process()` 过（`title` 是替换后的值），也只会对原文作用一次，
    不会把 raw 规则重复叠加。

    `process()` 与 `preview_titles()` 共用这一条。两个替换器由调用方先经
    `replacers_by_stage()` 分好（循环 N 条标题只分流一次），故不对外。
    """
    title = raw.text(node.raw_title)
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


def read_book(cfg: Config, sources: Sources | None = None) -> Book:
    """读输入文件并切分。文件读不了、解不开或没有正文时抛 `ValueError`。

    `sources` 是前端预加载的资源内容（CLI 传 `load_sources(cfg)`，GUI 从表单直接构造）；
    `None` 等价于空的 `Sources()`。产出阶段从 `Book.sources` 取 CSS / 字体 / 封面。
    """
    if cfg.input is None:
        raise ValueError("缺少输入文件")
    resolved = resolve(cfg)
    lines, used = read_input(resolved)
    return build_book(resolved, lines, used, sources or Sources())


def build_book(
    cfg: Config, lines: list[str], encoding: str, sources: Sources
) -> Book:
    """从已经读好的行组装 `Book`。不读文件，也不校验 `cfg`。

    `cfg` 应当是 `resolve()` 过的（`read_book()` 负责），这里只做切分和「有没有正文」
    这道检查——空正文是内容问题，在读文件那层分不出来。调用方直接喂内存里的行时
    （预览、测试）也走这条路。
    """
    tree, stats = process(lines, cfg, sources.toc_entries)
    if not any(node.paragraphs for node in walk(tree)):
        where = cfg.input.name if cfg.input else cfg.book_title
        raise ValueError(f"文件里没有可生成的内容：{where}")
    return Book(cfg, tree, stats, encoding, sources)


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
    """把目录写到 `cfg.out`。没给 `out` 就报错——想输出到终端由 CLI 自己调 `toc_text`。"""
    return write_text(_target(book.cfg.out), toc_text(book) + "\n", book.cfg.overwrite)


def write_epub(book: Book) -> Path:
    """组装并写出 EPUB，路径取 `cfg.out`，留空则与输入同名。返回落盘路径。

    组装在落盘之前跑完，所以失败时目标文件不会被创建或截断。「无法生成 EPUB」
    这个上下文只包住写入阶段——路径不可写、磁盘满这类错误才需要知道在往哪写。
    """
    target = _epub_path(book.cfg)
    _guard_overwrite(target, book.cfg.overwrite)
    data = build_epub(book.cfg, book.tree, book.sources)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    except OSError as e:
        raise ValueError(f"无法生成 EPUB：{e}") from e
    return target


def write_css(cfg: Config) -> Path:
    """把内置 CSS 模板写到 `cfg.dump_css`。只用排版参数，不必读输入。

    导出的是 `builtin_css()`（不受外部 CSS 影响，方便当样式表起点）。只需要内嵌字体的
    **文件名**——那是样式表里 `@font-face` 的 `src` 片段，用不到字体字节，
    所以这条路径上不加载任何资源。

    **刻意不调 `validate_config()`**：`--dump-css` 是排障入口，用户往往就是想拿一份样式表
    去对比，此时输入文件、字体、封面都可能根本不存在。校验拦在这里只会让人拿不到模板。
    真正生成那条路（`read_book()` → `resolve()`）才校验。
    """
    if not cfg.dump_css:
        raise ValueError("缺少 CSS 输出路径")
    font_name = Path(cfg.font).name if cfg.font else None
    return write_text(_target(cfg.dump_css), builtin_css(cfg, font_name), cfg.overwrite)


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


def _target(out: str | Path | None) -> Path:
    """把输出位置翻成 `Path`，明确拒绝「空」。

    形参收 `None` 是因为 `Config.out` 就是 `Path | None`。`Path(str(None))` 不会报错，
    它老老实实变成 `Path("None")`——名字非空，于是混过去，最后写出一个叫 `None` 的
    文件。这里显式拦下来，让"没给输出路径"停在边界上。
    """
    if out is None or (isinstance(out, str) and not out.strip()):
        raise ValueError("缺少输出路径")
    path = Path(out)
    if not path.name:
        raise ValueError("缺少输出路径")
    return path


def _guard_overwrite(path: Path, overwrite: bool) -> None:
    if not overwrite and path.exists():
        raise ValueError(f"输出文件已存在：{path}（当前设置为不覆盖）")
