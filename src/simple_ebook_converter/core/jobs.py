"""一次转换的完整流程：读文件、切分、产出文件。

`pipeline.process()` 只管「行 → 章节树」，这里负责读输入、决定产出什么、写盘，
并把失败翻成一句能直接展示的话（`ValueError`）。两个前端只调这里，不自己拼流程。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .builder import build_css, build_epub
from .config import Config, Node
from .encoding import EncodingError, read_lines
from .options import TOC_FORMATS
from .parser import ParseStats, walk
from .pipeline import process
from .toc import to_json, to_text

#: `run()` 的三种产出方式
EPUB = "epub"
TOC = "toc"
CSS = "css"


@dataclass(frozen=True)
class Book:
    """读进来的一本书。`cfg` 已经被 `process()` 补全：封面、书名、作者都已定。"""

    cfg: Config
    tree: list[Node]
    stats: ParseStats
    encoding: str


@dataclass(frozen=True)
class Result:
    """一次产出的结果。

    `path` 为 None 表示产物没有落盘（目录交给调用方自己处理），`text` 是目录正文。
    """

    book: Book
    kind: str
    path: Path | None = None
    text: str = ""


def run(
    cfg: Config,
    kind: str = EPUB,
    out: str | Path | None = None,
    toc_format: str = "text",
) -> Result:
    """跑一次转换，返回产物。

    三种产出方式：生成 EPUB（默认）、只输出目录、只导出 CSS。EPUB 的 `out` 留空
    就落到输入同名；目录的 `out` 留空表示不落盘，`Result.path` 为 None、`text`
    是目录正文，由调用方决定打印还是写文件。
    """
    book = load(cfg)
    if kind == EPUB:
        return Result(book, kind, generate(book, out))
    if kind == TOC:
        text = render_toc(book, toc_format)
        target = None if out in (None, "") else Path(str(out))
        if target is not None:
            write_text(target, text + "\n", overwrite=cfg.overwrite)
        return Result(book, kind, target, text)
    if kind == CSS:
        if not out:
            raise ValueError("缺少 CSS 输出路径")
        target = Path(str(out))
        write_text(target, build_css(cfg), overwrite=cfg.overwrite)
        return Result(book, kind, target)
    raise ValueError(f"未知的产出方式：{kind!r}（只能是 {EPUB} / {TOC} / {CSS}）")


def load(cfg: Config) -> Book:
    """读输入文件并切分。文件读不了、解不开或没有正文时抛 `ValueError`。"""
    if cfg.input is None:
        raise ValueError("缺少输入文件")
    try:
        lines, used = read_lines(cfg.input, cfg.encoding)
    except EncodingError as e:
        raise ValueError(str(e)) from e
    except OSError as e:
        raise ValueError(f"无法读取输入文件：{e}") from e
    tree, stats = process(lines, cfg)
    if not any(node.paragraphs for node in walk(tree)):
        raise ValueError(f"文件里没有可生成的内容：{Path(cfg.input).name}")
    return Book(cfg, tree, stats, used)


def generate(book: Book, out: str | Path | None = None) -> Path:
    """组装并写出 EPUB，返回落盘路径。"""
    target = epub_path(book.cfg, out)
    guard_overwrite(target, book.cfg.overwrite)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        build_epub(book.cfg, book.tree, build_css(book.cfg), target)
    except (OSError, ValueError) as e:
        raise ValueError(f"无法生成 EPUB：{e}") from e
    return target


def render_toc(book: Book, fmt: str = "text") -> str:
    """按格式渲染目录：缩进文本或 JSON。"""
    tree, depth = book.tree, book.cfg.toc_depth
    if fmt == "json":
        return json.dumps(to_json(tree, depth), ensure_ascii=False, indent=2)
    if fmt == "text":
        return to_text(tree, depth)
    raise ValueError(f"目录格式只能是 {'/'.join(TOC_FORMATS)}，收到：{fmt!r}")


def epub_path(cfg: Config, out: str | Path | None = None) -> Path:
    """EPUB 落盘路径：留空取输入名，缺 `.epub` 后缀就补上。"""
    if out is None or str(out) == "":
        if cfg.input is None:
            raise ValueError("缺少输入文件")
        return Path(cfg.input).with_suffix(".epub")
    path = Path(str(out))
    return path if path.suffix.lower() == ".epub" else path.with_name(path.name + ".epub")


def write_text(path: Path, text: str, overwrite: bool = True) -> Path:
    """写文本产物（目录、CSS）。"""
    guard_overwrite(path, overwrite)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    except OSError as e:
        raise ValueError(f"无法写入 {path}：{e}") from e
    return path


def guard_overwrite(path: Path, overwrite: bool) -> None:
    if not overwrite and path.exists():
        raise ValueError(f"输出文件已存在：{path}（当前设置为不覆盖）")
