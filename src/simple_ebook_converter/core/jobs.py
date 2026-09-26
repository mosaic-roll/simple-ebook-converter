"""前端能跑的活：读文件、生成 EPUB、导出目录、写盘。

`process()` 只管「行 → 章节树」，这里负责读文件、决定输出到哪、落盘，并把失败翻成
一句能直接展示的话（`ValueError`）。两个前端都只调这里，不自己拼流程。
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

#: 输出路径写这个值表示标准输出（只对文本产物有意义）
STDOUT = "-"


@dataclass(frozen=True)
class Book:
    """读进来的一本书。`cfg` 已经被 `process()` 补全：封面、书名、作者都已定。"""

    cfg: Config
    tree: list[Node]
    stats: ParseStats
    encoding: str


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


def preview(cfg: Config) -> list[dict]:
    """按当前设置解析目录树（GUI 的目录预览）。"""
    book = load(cfg)
    return to_json(book.tree, cfg.toc_depth)


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


def toc_target(out: str | Path | None) -> Path | None:
    """目录输出路径；留空或写 `-` 表示输出到标准输出（返回 None）。"""
    if out is None or str(out) in ("", STDOUT):
        return None
    return Path(out)


def epub_path(cfg: Config, out: str | Path | None = None) -> Path:
    """EPUB 落盘路径：留空取输入名，缺 `.epub` 后缀就补上。"""
    if out is None or str(out) == "":
        if cfg.input is None:
            raise ValueError("缺少输入文件")
        return Path(cfg.input).with_suffix(".epub")
    if str(out) == STDOUT:
        raise ValueError("EPUB 是二进制文件，不能输出到标准输出，请指定文件路径")
    path = Path(out)
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


def summary(book: Book) -> str:
    """给终端看的一行处理结果。"""
    levels = "、".join(f"h{level}×{count}" for level, count in sorted(book.stats.level_counts.items()))
    return (
        f"编码：{book.encoding}；标题：{levels or '无'}；"
        f"前言：{'有' if book.stats.has_preface else '无'}"
    )
