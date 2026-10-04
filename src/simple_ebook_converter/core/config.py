"""转换参数 `Config`、内置标题正则。

这里是全部默认值的唯一真源：选项表（`options.py`）、`parse()` / `to_text()` 的默认
参数都从 `Config` 的字段默认值派生，别处不再写第二份字面量。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .encoding import AUTO_ENCODING
from .replace import Rule

# ══════════════════════════════════════════════════════════════
# 内置标题正则
# ══════════════════════════════════════════════════════════════

#: 简/繁/日 常用数字（不含大写数字）
_CN_DIGIT = "[0-9０-９一二三四五六七八九十百千零〇両两兩萬万]"

#: 编号核心与副标题之间的分隔符：空白、冒号、点号、顿号、逗号、破折号、中点
_SEP = r"[\s:：.．、,，\-—－·]"

#: 尾部约束：核心词后要么「分隔符 + 副标题」，要么行尾。
#: 不用 \b：中文汉字之间没有词边界。长度交给 Config.max_title_len 管。
_TAIL = rf"(?:{_SEP}.*|$)"


#: 卷标题：第X卷 / 第X部（中），第X巻 / 第X編（日）
DEFAULT_VOLUME_RE = (
    rf"^(?:"
    rf"第\s*{_CN_DIGIT}+\s*"  # 第X，数字两侧可带空白
    rf"|最[终終]|[终終]"  # 特殊：最终卷 / 终卷
    rf")"
    rf"[卷部巻編]{_TAIL}"
)


#: 章标题里「要求有分隔符才能带副标题」的核心词
#: 第一章 / 第 1 章 / 楔子
_CHAPTER_CORES = (
    rf"第\s*{_CN_DIGIT}+\s*[章节回集幕话話節]"
    rf"|引子|楔子|序章|序言|序|前言|尾声|后记|跋"
    rf"|[间間]章|幕[间間]"
    rf"|(?:最[终終]|[终終])[章回话話]"
)

#: 章标题
DEFAULT_CHAPTER_RE = (
    rf"^(?:{_CHAPTER_CORES}){_TAIL}"
    r"|^[Cc]hapter.*$"  # 英文：Chapter
    r"|^[Ss]ection.*$"  # Section
    r"|^\d+[、.．].*$"  # 阿拉伯数字编号：1. 标题
    rf"|^{_CN_DIGIT}+[、.．\s].*$"  # 中文数字编号：一、标题
    r"|^\d{1,4}$"  # 纯数字章节：12
    r"|^番外.*$"
    r"|^[后後]日[谈談].*$"  # 后日谈 / 後日談
    r"|^上架感言.*$"
    r"|^完本感言.*$"
)

#: 默认排除规则，不除外任何行（留空表示不开启）
DEFAULT_EXCLUDE_RE = ""

# ══════════════════════════════════════════════════════════════
# 选项取值集 & 层级预设
# ══════════════════════════════════════════════════════════════


#: 标题对齐方式，写进 CSS 的 `text-align`
ALIGN_CHOICES = ("left", "center", "right", "justify")

#: 目录输出格式：`--toc-format` 的取值，也是 `validation._CHECKS["toc_format"]` 认的集合。
#: 放在这里而不是 `toc`——`toc` 要 import 本模块，反向导入会成环。
FORMATS = ("text", "json")

#: 预设层级：级别 → (class 名, 中文名, 内置正则)。空正则 = 默认不启用。
LEVEL_PRESETS = (
    (2, "volume", "卷标题", DEFAULT_VOLUME_RE),
    (3, "chapter", "章标题", DEFAULT_CHAPTER_RE),
)

# 一条标题都没命中时整篇作为一章，标题取什么
_FALLBACK_TITLE = "未命名"


# ══════════════════════════════════════════════════════════════
# LevelRule：单条层级规则
# ══════════════════════════════════════════════════════════════


@dataclass
class LevelRule:
    """一个标题层级：级别 1~6 对应 h1~h6，正则为空即不启用。"""

    level: int
    pattern: str
    class_name: str = ""

    @property
    def active(self) -> bool:
        return bool(self.pattern)


def default_levels() -> list[LevelRule]:
    """内置的卷(h2) / 章(h3)两条层级。调用方拿到的是新列表，可随意改。"""
    return [
        LevelRule(level, pattern, name) for level, name, _, pattern in LEVEL_PRESETS
    ]


# ══════════════════════════════════════════════════════════════
# Config：一次转换的全部参数
# ══════════════════════════════════════════════════════════════


@dataclass
class Config:
    """一次转换的全部参数：输入什么样、书长什么样、产出什么文件。

    字段默认值 = 省略该参数时的行为。两个前端都只收值、调 `pipeline`，不各自拼流程；
    字段一律用正面表述（`overwrite` 而不是 `no_overwrite`），「关掉某功能」由前端表达为
    `--no-xxx` / 反向勾选框，收上来时已经是这里的正面语义。取值范围校验在
    `validation.validate_config()`。

    注意资源路径字段（`cover` / `font` / `css_file` / `css_append` / `toc_file`）：
    它们是**选项解析的落点**，唯一消费者是 `sources.load_sources()`，转换流程
    （`pipeline` / `builder`）一次都不看。GUI 从不填它们（恒为 `None`），它的资源走
    `Sources`。保留这些字段是为了 `options.build_config()` 有地方放 CLI 给的路径。
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
    #: 排除规则；行命中该正则时不作为标题。留空表示不排除任何行。
    exclude: str = DEFAULT_EXCLUDE_RE
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
    volume_align: str = "center"
    para_align: str = "justify"
    font: Path | None = None
    #: 整份替代内置样式（与 `css_append` 互斥）
    css_file: Path | None = None
    #: 追加到内置样式之后（与 `css_file` 互斥）
    css_append: Path | None = None

    # 目录
    #: 目录页是否进 spine（nav 文档无论如何都生成）
    toc_in_spine: bool = True
    toc_depth: int = 6
    #: 目录输出格式：`FORMATS` 之一（text | json）
    toc_format: str = "text"
    #: 目录树 JSON 文件（`toc.to_json` 的产物，可经界面编辑）。给了就跳过正则解析，
    #: 按行号从输入取正文，标题用文件现值
    toc_file: Path | None = None

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


#: 全默认的模板，只用来取参数默认值与选项初值，谁也不许改它
DEFAULTS = Config()
