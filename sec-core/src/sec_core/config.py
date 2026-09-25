from __future__ import annotations

from dataclasses import dataclass, field, fields
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
    r"^最终章.{0,20}$|^最終章.{0,20}$",  # 终章（简/繁/日）
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


#: `config_defaults()` 里把 levels 拆成单条正则的字段（前端每条一个输入框）
LEVEL_FIELDS = {2: "volume", 3: "chapter", 4: "section"}


def config_defaults() -> dict[str, object]:
    """从 `Config()` 派生全部默认值，供 CLI / GUI 填表用（唯一真源，不重复硬编码）。

    额外给出 `volume`/`chapter`/`section` 三个由 `levels` 拆出的正则字符串，
    以及取反后的 `no_overwrite`（`Config.overwrite` 的反面，勾选框语义）。
    """
    cfg = Config()
    by_level = {r.level: r.pattern for r in cfg.levels}
    defaults: dict[str, object] = {
        "overwrite": cfg.overwrite,
        "max_title_len": cfg.max_title_len,
        "preface_title": cfg.preface_title,
        "no_volume": cfg.no_volume,
        "no_clean": cfg.no_clean,
        "no_toc": cfg.no_toc,
        "toc_depth": cfg.toc_depth,
        "indent": cfg.indent,
        "line_height": cfg.line_height,
        "para_spacing": cfg.para_spacing,
        "chapter_align": cfg.chapter_align,
        "volume_align": cfg.volume_align,
    }
    defaults.update({name: by_level.get(level, "") for level, name in LEVEL_FIELDS.items()})
    for field in fields(Config):
        if field.name in ("levels", "overwrite"):
            continue
        value = getattr(cfg, field.name)
        defaults[field.name] = "" if value is None else value
    defaults["no_overwrite"] = not cfg.overwrite
    return defaults
