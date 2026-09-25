from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .replace import Rule

DEFAULT_VOLUME_RE = r"^第[0-9一二三四五六七八九十零〇百千两 ]+[卷部篇]"
DEFAULT_CHAPTER_RE = r"^第[0-9一二三四五六七八九十零〇百千两 ]+[章节回]"


@dataclass
class LevelRule:
    """一个标题层级（1~6 对应 h1~h6）。"""

    level: int
    pattern: str
    cls: str = ""
    enabled: bool = True

    @property
    def active(self) -> bool:
        return self.enabled and bool(self.pattern)


@dataclass
class Node:
    title: str
    level: int
    cls: str = ""
    paragraphs: list[str] = field(default_factory=list)
    children: list["Node"] = field(default_factory=list)
    anchor: str = ""
    raw_title: str = ""


def default_levels() -> list[LevelRule]:
    return [
        LevelRule(2, DEFAULT_VOLUME_RE, "volume"),
        LevelRule(3, DEFAULT_CHAPTER_RE, "chapter"),
        LevelRule(4, "", "section"),
    ]


@dataclass
class Config:
    input: Path | None = None
    output: Path | None = None
    encoding: str = "auto"
    overwrite: bool = True

    title: str | None = None
    author: str = ""
    date: str | None = None
    language: str = "zh"
    cover: Path | None = None

    levels: list[LevelRule] = field(default_factory=default_levels)
    max_title_len: int = 35
    preface_title: str = "前言"
    no_volume: bool = False

    replacements: list[Rule] = field(default_factory=list)
    no_clean: bool = False

    no_toc: bool = False
    toc_depth: int = 6

    indent: int = 2
    line_height: str = "1.5"
    para_spacing: str = "1em"
    chapter_align: str = "center"
    volume_align: str = "right"
    font: Path | None = None
    css_file: Path | None = None

    toc_file: str = "-"
    toc_format: str = "text"
    dump_css: Path | None = None