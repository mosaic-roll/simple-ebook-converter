"""选项表：命令行参数、默认值、类型、帮助文本的唯一真源。

一条 `Option` 同时描述了「前端要收集什么」和「它对应 Config 的哪个字段」，
`build_config()` 按这张表把前端的原始值翻译成 `Config`。因此：

- 加一个选项只改这一处，CLI 的 `--help`、GUI 的表单初值与提示语都自动跟上；
- 默认值只在 `Config` 里写一次（`option_default()` 从 Config 派生）；
- 两个前端只做「收集值 → 交给我」，不各自实现一遍转换规则。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import ALIGN_CHOICES, Config, LevelRule
from .encoding import ENCODING_CHOICES
from .levels import build_levels
from .replace import Rule, rules_from_source

#: `--toc-only` 的输出格式
TOC_FORMATS = ("text", "json")

# 取值类型，决定 GUI 用什么控件、CLI 用什么 click 参数类型
TEXT = "text"
INT = "int"
BOOL = "bool"
PATH = "path"
CHOICE = "choice"
MULTI = "multi"


@dataclass(frozen=True)
class Option:
    """一个可配置项。

    `field` 指向 `Config` 的字段名；`field` 为 None 表示这个值不进 Config
    （例如输出路径、只影响某一种输出模式的开关）。`invert` 表示它是该字段的反面
    （`--no-clean` 对应 `Config.clean`）。
    """

    name: str
    kind: str
    label: str
    help: str
    group: str
    short: str = ""
    field: str | None = None
    invert: bool = False
    level: int | None = None
    choices: tuple[str, ...] = ()
    exists: bool = False
    default: Any = ""

    @property
    def flags(self) -> tuple[str, ...]:
        long = "--" + self.name.replace("_", "-")
        return (f"-{self.short}", long) if self.short else (long,)


OPTIONS: tuple[Option, ...] = (
    # ---- 输入 ----
    Option(
        "input", PATH, "输入文件",
        "输入 txt（也可直接作为位置参数）",
        "输入", short="i", exists=True,
    ),
    Option(
        "encoding", TEXT, "编码",
        f"输入编码，auto 为自动检测；也可填 Python codec 名（常用：{'/'.join(ENCODING_CHOICES[1:])}）",
        "输入", short="e", field="encoding",
    ),
    # ---- 输出 ----
    Option(
        "out", PATH, "输出文件",
        "输出文件，缺 .epub 后缀自动补，默认取输入名",
        "输出", short="o",
    ),
    Option(
        "no_overwrite", BOOL, "覆盖已有文件",
        "输出文件已存在时是否覆盖（默认覆盖）",
        "输出", field="overwrite", invert=True,
    ),
    Option(
        "dump_css", PATH, "导出 CSS",
        "把当前生效的 CSS 写到这个文件",
        "输出",
    ),
    # ---- 书籍信息 ----
    Option(
        "title", TEXT, "书名",
        "留空则从文件名猜《书名》作者：作者",
        "书籍信息", field="title",
    ),
    Option(
        "author", TEXT, "作者",
        "留空则从文件名猜；仍留空则不写入元数据",
        "书籍信息", field="author",
    ),
    Option(
        "date", TEXT, "出版日期",
        "如 2024-05-13，留空则省略 dc:date（规范允许缺省）",
        "书籍信息", field="date",
    ),
    Option(
        "language", TEXT, "语言",
        "语言代码",
        "书籍信息", field="language",
    ),
    Option(
        "cover", PATH, "封面图",
        "留空则先找输入同目录的 cover.*，再退回文字封面页",
        "书籍信息", field="cover", exists=True,
    ),
    Option(
        "no_text_cover", BOOL, "文字封面页",
        "没有封面图时是否生成只含书名/作者的封面页（默认生成）",
        "书籍信息", field="text_cover", invert=True,
    ),
    # ---- 章节识别 ----
    Option(
        "volume", TEXT, "卷标题正则",
        "h2 + class=volume；留空表示不识别卷标题",
        "章节识别", level=2,
    ),
    Option(
        "chapter", TEXT, "章标题正则",
        "h3 + class=chapter；留空表示不识别章标题",
        "章节识别", level=3,
    ),
    Option(
        "section", TEXT, "节标题正则",
        "h4 + class=section；默认留空（不启用）",
        "章节识别", level=4,
    ),
    Option(
        "no_volume", BOOL, "无卷模式",
        "卷行是否作为标题（卷正则仍会覆盖内置规则）",
        "章节识别", field="volume_titles", invert=True,
    ),
    Option(
        "level", MULTI, "额外层级",
        "额外层级规则，可重复；格式 级别:正则[:类名]，级别 1~6",
        "章节识别", default=(),
    ),
    Option(
        "max_title_len", INT, "标题最长字数",
        "超过这个字数的行即使命中正则也当正文",
        "章节识别", field="max_title_len",
    ),
    Option(
        "preface_title", TEXT, "前言标题",
        "首个标题之前那些无标题段落归到这一节",
        "章节识别", field="preface_title",
    ),
    # ---- 清理与替换 ----
    Option(
        "no_clean", BOOL, "清理文本",
        "去掉段首段尾空格并删除空行（默认清理）",
        "清理与替换", field="clean", invert=True,
    ),
    Option(
        "replace_json", TEXT, "替换规则",
        "一段 JSON 替换规则（有序列表），与 --replace-file 二选一",
        "清理与替换",
    ),
    Option(
        "replace_file", PATH, "替换规则文件",
        "从 JSON 文件读取替换规则，与 --replace-json 二选一",
        "清理与替换",
    ),
    # ---- 排版 ----
    Option(
        "indent", INT, "段落缩进",
        "段落缩进字数，0 为不缩进",
        "排版", field="indent",
    ),
    Option(
        "line_height", TEXT, "行高",
        "行高，如 1.5",
        "排版", field="line_height",
    ),
    Option(
        "para_spacing", TEXT, "段间距",
        "段间距，带单位，如 1em / 12px",
        "排版", field="para_spacing",
    ),
    Option(
        "chapter_align", CHOICE, "章对齐",
        "章标题对齐方式",
        "排版", field="chapter_align", choices=ALIGN_CHOICES,
    ),
    Option(
        "volume_align", CHOICE, "卷对齐",
        "卷标题对齐方式",
        "排版", field="volume_align", choices=ALIGN_CHOICES,
    ),
    Option(
        "font", PATH, "正文字体",
        "嵌入到书里的正文字体（ttf/otf/woff/woff2）",
        "排版", field="font", exists=True,
    ),
    Option(
        "css_file", PATH, "外部 CSS 文件",
        "追加到内置样式之后，可以覆盖内置规则",
        "排版", field="css_file", exists=True,
    ),
    # ---- 目录 ----
    Option(
        "no_toc", BOOL, "书页含目录",
        "目录页是否进正文流（nav 文档无论如何都生成，供阅读器导航面板使用）",
        "目录", field="toc_in_spine", invert=True,
    ),
    Option(
        "toc_depth", INT, "目录深度",
        "目录包含到第几级，1~6",
        "目录", field="toc_depth",
    ),
    Option(
        "toc_only", BOOL, "只输出目录",
        "只输出目录，不生成 EPUB",
        "目录",
    ),
    Option(
        "toc_format", CHOICE, "目录格式",
        "只输出目录时的格式：text | json",
        "目录", choices=TOC_FORMATS, default="text",
    ),
)


def option_groups() -> list[tuple[str, tuple[Option, ...]]]:
    """按 `OPTIONS` 的先后顺序分组，供 CLI 的 `--help` 与 GUI 的分页使用。"""
    groups: dict[str, list[Option]] = {}
    for opt in OPTIONS:
        groups.setdefault(opt.group, []).append(opt)
    return [(name, tuple(items)) for name, items in groups.items()]


def option_default(opt: Option) -> Any:
    """选项默认值：能对上 `Config` 的从 Config 派生，其余取选项自带的 `default`。"""
    if opt.kind == BOOL:
        return False
    if opt.level is not None:
        return next(r.pattern for r in Config().levels if r.level == opt.level)
    if opt.field:
        return getattr(Config(), opt.field)
    return opt.default


def option_defaults() -> dict[str, Any]:
    """全部选项的默认值，键是选项名。

    两个前端都是逐项取 `option_default()`（要按选项类型挑控件/参数），这份整表
    适合只想拿到「全部缺省值」的调用方。
    """
    return {opt.name: option_default(opt) for opt in OPTIONS}


# ---------- 原始值 → Config ----------


def build_config(values: Mapping[str, Any]) -> Config:
    """把前端收集到的原始值翻译成 `Config`，出错抛 `ValueError`（消息可直接展示）。

    怎么转全写在选项表上：`field` 说这个值进 `Config` 的哪个字段，`invert` 说它是
    该字段的反面（`--no-clean` → `Config.clean`），`kind` 说按什么类型转。所以
    `Config` 的字段名只在选项表里出现一次，这里不再按选项名分支。

    留空一律表示「用 `Config` 的默认值」，取值范围由 `Config.validate()` 负责。
    表里 `field` 为空的选项不进 `Config`：输入文件和三个层级正则需要另外组装，
    其余只决定某一种产出方式，不影响转换参数。
    """
    return Config(
        input=_input_path(values),
        levels=_levels(values),
        replacements=_replacements(values),
        **_fields(values),
    )


def _fields(values: Mapping[str, Any]) -> dict[str, Any]:
    """按选项表逐项转成 `Config` 的字段值。"""
    fields: dict[str, Any] = {}
    for opt in OPTIONS:
        if not opt.field:
            continue
        value = values.get(opt.name)
        fields[opt.field] = not bool(value) if opt.invert else _convert(opt, value)
    return fields


def _convert(opt: Option, value: Any) -> Any:
    """单个选项的原始值 → `Config` 字段值。"""
    if opt.kind == INT:
        return _integer(opt, value)
    if opt.kind == PATH:
        return _path(opt, value)
    if opt.kind == BOOL:
        return bool(value)
    text = _text(value)
    return option_default(opt) if text is None else text


def _text(value: Any) -> str | None:
    """字符串选项的值；未给或只填了空白都视同未给。"""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _integer(opt: Option, value: Any) -> int:
    text = _text(value)
    if text is None:
        return int(option_default(opt))
    try:
        return int(text)
    except ValueError:
        raise ValueError(f"{opt.label}需为整数，收到：{value!r}") from None


def _path(opt: Option, value: Any) -> Path | None:
    text = _text(value)
    if text is None:
        return None
    path = Path(text)
    if opt.exists:
        _require_file(path, opt.label)
    return path


def _input_path(values: Mapping[str, Any]) -> Path:
    source = _text(values.get("input"))
    if source is None:
        raise ValueError("缺少输入文件")
    path = Path(source)
    _require_file(path, "输入文件")
    return path


def _require_file(path: Path, label: str) -> None:
    if not path.is_file():
        raise ValueError(f"{label}不存在：{path}")


def _levels(values: Mapping[str, Any]) -> list[LevelRule]:
    """卷/章/节三个预设 + 额外层级。预设留空表示不识别该层级，未给才是内置值。"""
    presets = {
        opt.name: option_default(opt) if values.get(opt.name) is None else str(values[opt.name])
        for opt in OPTIONS
        if opt.level is not None
    }
    return build_levels(presets, _specs(values.get("level")))


def _specs(value: Any) -> list[str]:
    """额外层级规格。GUI 给多行文本，CLI 给一个元组，两种都收。"""
    if not value:
        return []
    if isinstance(value, str):
        return [line.strip() for line in value.splitlines() if line.strip()]
    return [str(item).strip() for item in value if str(item).strip()]


def _replacements(values: Mapping[str, Any]) -> list[Rule]:
    """替换规则只有 JSON 一个内部入口：`--replace-json` 文本或 `--replace-file` 文件。

    GUI 的替换规则表格是界面上的写法，先由 `gui.app` 转成 JSON 文本再走这里，
    所以 core 不需要认识表格行。
    """
    return rules_from_source(_text(values.get("replace_json")), _text(values.get("replace_file")))
