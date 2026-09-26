"""一次转换的完整流程：读输入、切分、产出文件。

程序是无状态的：`resolve()` 补全参数后返回**新的** `Config`，原始 `read_book()` 读文件、
切分、清理、替换，把结果装进 `Book`；产出方式由 `cfg` 上的 `toc_only` / `dump_css` 决定，
所以这里没有「产出类型」参数，也没有需要前端记住的调用顺序。
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

from .builder import build_css, build_epub
from .cleaner import clean_lines
from .config import Config, Node
from .encoding import EncodingError, read_lines
from .mediatypes import find_cover
from .meta import resolve_metadata
from .parser import ParseStats, parse, walk
from .replace import replacers_by_scope
from .toc import render


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


def process(lines: list[str], cfg: Config) -> tuple[list[Node], ParseStats]:
    """把原始行变成章节树：切分 → 清理 → 按作用范围替换。只动 `lines` 与新节点。"""
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


def read_book(cfg: Config) -> Book:
    """读输入文件并切分。文件读不了、解不开或没有正文时抛 `ValueError`。"""
    if cfg.input is None:
        raise ValueError("缺少输入文件")
    resolved = resolve(cfg)
    try:
        lines, used = read_lines(resolved.input, resolved.encoding)
    except EncodingError as e:
        raise ValueError(str(e)) from e
    except OSError as e:
        raise ValueError(f"无法读取输入文件：{e}") from e
    tree, stats = process(lines, resolved)
    if not any(node.paragraphs for node in walk(tree)):
        raise ValueError(f"文件里没有可生成的内容：{resolved.input.name}")
    return Book(resolved, tree, stats, used)


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
    """把当前生效的 CSS 写到 `cfg.dump_css`。只用排版参数，不必读输入。

    格式校验（字体、封面）照样走 `Config.validate()`：参数错在哪，哪种产出方式都该报。
    """
    if not cfg.dump_css:
        raise ValueError("缺少 CSS 输出路径")
    cfg.validate()
    return write_text(_target(cfg.dump_css), build_css(cfg), cfg.overwrite)


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
    return path if path.suffix.lower() == ".epub" else path.with_name(path.name + ".epub")


def _target(out: str | Path) -> Path:
    path = Path(str(out))
    if not path.name:
        raise ValueError("缺少输出路径")
    return path


def _guard_overwrite(path: Path, overwrite: bool) -> None:
    if not overwrite and path.exists():
        raise ValueError(f"输出文件已存在：{path}（当前设置为不覆盖）")
