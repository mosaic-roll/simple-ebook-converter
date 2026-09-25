from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .replace import Rule

_CN_NUM = "[0-9０-９一二三四五六七八九十百千零〇両两兩萬万 ]"  # 简/繁/日 常用数字（不含大写数字）

_VOLUME_FRAGMENTS = [
    rf"^第{_CN_NUM}+[卷部巻編]",  # 中文 第X卷/第X部（不用"篇"）｜日文 第X巻/第X編
]

_CHAPTER_FRAGMENTS = [
    rf"^第{_CN_NUM}+[章节回集幕話節]",  # 中文 章/节/回/集/幕｜繁体 節｜日文 話
    r"^[Cc]hapter.{1,20}$",  # 英文 Chapter
    r"^[Ss]ection.{1,20}$",  # 英文 Section
    r"^[Pp]age.{1,20}$",  # 英文 Page
    r"^\d{1,4}$",  # 纯数字标题
    r"^\d+、$",  # 编号列表如 "1、"
    r"^引子$|^楔子$|^序章$",  # 开篇
    r"^最終章.{0,20}$",  # 终章（繁体/日文）
    r"^番外.{0,20}$",  # 番外
    r"^完本感言.{0,4}$",  # 完本感言
]

DEFAULT_VOLUME_RE = "|".join(_VOLUME_FRAGMENTS)
DEFAULT_CHAPTER_RE = "|".join(_CHAPTER_FRAGMENTS)


@dataclass
class LevelRule:
    """一个标题层级（1~6 对应 h1~h6）。"""

    level: int
    pattern: str
    class_name: str = ""
    enabled: bool = True

    @property
    def active(self) -> bool:
        return self.enabled and bool(self.pattern)


@dataclass
class Node:
    title: str
    level: int
    class_name: str = ""
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