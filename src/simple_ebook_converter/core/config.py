"""转换参数 `Config`、内置标题正则。

这里是全部缺省值的唯一真源：选项表（`options.py`）、`parse()` / `to_text()` 的缺省
参数都从 `Config` 的字段默认值派生，别处不再写第二份字面量。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .encoding import AUTO_ENCODING
from .mediatypes import cover_media_type, font_media_type
from .replace import Rule

# 简/繁/日 常用数字（不含大写数字）
_CN_NUM = "[0-9０-９一二三四五六七八九十百千零〇両两兩萬万 ]"

#: 卷标题：第X卷/第X部，日文 第X巻/第X編
DEFAULT_VOLUME_RE = rf"^第{_CN_NUM}+[卷部巻編]"

#: 章标题：先分片写再合并，便于单独增删某一类标题
_CHAPTER_FRAGMENTS = (
    rf"^第{_CN_NUM}+[章节回集幕話節]",  # 中文 章/节/回/集/幕｜繁体 節｜日文 話
    r"^[Cc]hapter.{1,20}$",  # 英文
    r"^[Ss]ection.{1,20}$",
    r"^[Pp]age.{1,20}$",
    r"^\d{1,4}$",  # 纯数字
    r"^\d+、$",  # 编号，如 "1、"
    r"^引子$|^楔子$|^序章$",  # 开篇
    r"^最终章.{0,20}$|^最終章.{0,20}$",  # 终章（简/繁/日）
    r"^番外.{0,20}$",
    r"^完本感言.{0,4}$",
)
DEFAULT_CHAPTER_RE = "|".join(_CHAPTER_FRAGMENTS)

#: 标题对齐方式，写进 CSS 的 `text-align`
ALIGN_CHOICES = ("left", "center", "right")

#: 预设层级：级别 → (class 名, 中文名, 内置正则)。空正则 = 默认不启用。
LEVEL_PRESETS = (
    (2, "volume", "卷标题", DEFAULT_VOLUME_RE),
    (3, "chapter", "章标题", DEFAULT_CHAPTER_RE),
    (4, "section", "节标题", ""),
)

# 一条标题都没命中时整篇作为一章，标题取什么
_FALLBACK_TITLE = "未命名"


@dataclass
class LevelRule:
    """一个标题层级：级别 1~6 对应 h1~h6，正则为空即不启用。"""

    level: int
    pattern: str
    class_name: str = ""

    @property
    def active(self) -> bool:
        return bool(self.pattern)


@dataclass
class Node:
    """一个标题节点。`title` 是替换后的标题，`raw_title` 始终保留原文。"""

    title: str
    level: int
    class_name: str = ""
    paragraphs: list[str] = field(default_factory=list)
    children: list["Node"] = field(default_factory=list)
    anchor: str = ""
    raw_title: str = ""


def default_levels() -> list[LevelRule]:
    """内置的卷/章/节三条层级。调用方拿到的是新列表，可随意改。"""
    return [LevelRule(level, pattern, name) for level, name, _, pattern in LEVEL_PRESETS]


@dataclass
class Config:
    """一次转换的全部参数：输入什么样、书长什么样、产出什么文件。

    字段默认值 = 省略该参数时的行为。两个前端都只收值、调 `pipeline`，不各自拼流程；
    字段一律用正面表述（`overwrite` 而不是 `no_overwrite`），「关掉某功能」由前端表达为
    `--no-xxx` / 反向勾选框，收上来时已经是这里的正面语义。取值范围校验在 `validate()`。
    """

    # 输入
    input: Path | None = None
    encoding: str = AUTO_ENCODING

    # 元数据
    title: str | None = None
    author: str = ""
    date: str | None = None
    language: str = "zh"
    cover: Path | None = None
    #: 没有封面图时是否生成只含书名/作者的封面页
    text_cover: bool = True

    # 章节识别
    levels: list[LevelRule] = field(default_factory=default_levels)
    #: 卷行是否算标题；False 时 `第X卷` 这类行当正文
    volume_titles: bool = True
    max_title_len: int = 35
    preface_title: str = "前言"

    # 文本处理
    clean: bool = True
    replacements: list[Rule] = field(default_factory=list)

    # 排版
    indent: int = 2
    line_height: str = "1.5"
    para_spacing: str = "1em"
    chapter_align: str = "center"
    volume_align: str = "right"
    font: Path | None = None
    css_file: Path | None = None

    # 目录
    #: 目录页是否进 spine（nav 文档无论如何都生成）
    toc_in_spine: bool = True
    toc_depth: int = 6
    #: 目录输出格式：text | json（见 `toc.FORMATS`）
    toc_format: str = "text"

    # 产出
    #: 输出路径。留空时 EPUB 取输入同名，目录由调用方决定（CLI 走 stdout）
    out: Path | None = None
    overwrite: bool = True
    #: 只输出目录，不生成 EPUB
    toc_only: bool = False
    #: 只把当前生效的 CSS 写到这个文件（给了就不必读输入）
    dump_css: Path | None = None

    @property
    def book_title(self) -> str:
        """书名：显式值 → 输入文件名 → 「未命名」。`resolve()` 会先把猜到的值填好。"""
        if self.title:
            return self.title
        return Path(self.input).stem if self.input else _FALLBACK_TITLE

    def validate(self) -> None:
        """校验取值范围，非法抛 `ValueError`（消息可直接展示给用户）。

        `resolve()` 会自动调用，正常走 CLI / GUI 都会校验；直接调 `build_epub()`
        的调用方应自己先过一遍。
        """
        if self.max_title_len < 1:
            raise ValueError(f"标题最大字数需为正整数，收到：{self.max_title_len}")
        if not 1 <= self.toc_depth <= 6:
            raise ValueError(f"目录深度需在 1~6 之间，收到：{self.toc_depth}")
        if self.indent < 0:
            raise ValueError(f"段落缩进字数不能为负，收到：{self.indent}")
        for name, label in (("chapter_align", "章对齐"), ("volume_align", "卷对齐")):
            value = getattr(self, name)
            if value not in ALIGN_CHOICES:
                raise ValueError(f"{label}只能是 {'/'.join(ALIGN_CHOICES)}，收到：{value}")
        if self.date:
            try:
                datetime.fromisoformat(self.date)
            except ValueError as e:
                raise ValueError(
                    f"日期格式错误：{self.date}（应为 YYYY-MM-DD 或 YYYY-MM-DD HH:MM[:SS]）"
                ) from e
        if self.font:
            font_media_type(Path(self.font))
        if self.cover:
            cover_media_type(Path(self.cover))


#: 全缺省的模板，只用来取参数默认值与选项初值，谁也不许改它
DEFAULTS = Config()
