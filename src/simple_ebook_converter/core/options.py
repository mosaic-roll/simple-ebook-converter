"""选项表：命令行参数与 GUI 表单的唯一真源。

表里只写「前端要什么」——选项名、中文标签、说明、分组、旗标形态；**取值类型和缺省值
一律从 `Config` 取**，所以新增一个转换参数不必在这里再抄一遍类型与默认值：

- `name` 就是 `Config` 的字段名，取值类型按字段注解（`str`/`int`/`bool`/`Path`）推出；
- `negative` 的选项命令行写 `--no-<name>`，界面按正面说法显示，两个前端收上来的值
  都已经是 `Config` 的正面语义，`build_config()` 因此不必认识 `--no-xxx`；
- 不进 `Config` 的只有三类（`in_config=False`）：`--volume/--chapter/--section/--level`
  决定 `levels`，`--replace-json/--replace-file` 决定 `replacements`。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, get_args, get_type_hints

from .config import ALIGN_CHOICES, DEFAULTS, Config
from .encoding import ENCODING_CHOICES
from .levels import build_levels
from .replace import rules_from_source
from .toc import FORMATS


def _config_kinds() -> dict[str, type]:
    """`Config` 字段名 → 取值类型。`Path | None` 取 `Path`；只认 str/int/bool/Path。"""
    kinds: dict[str, type] = {}
    for name, hint in get_type_hints(Config).items():
        kind = next((arg for arg in get_args(hint) if isinstance(arg, type)), hint)
        if kind in (str, int, bool, Path):
            kinds[name] = kind
    return kinds


CONFIG_KINDS = _config_kinds()


@dataclass(frozen=True)
class Option:
    """一个可配置项，值的语义与 `Config` 字段一致。"""

    name: str
    label: str
    help: str
    group: str
    short: str = ""
    #: 长旗标词干（不含 `--`）。留空按 `name` 推；个别旗标名与字段名不同时显式写，
    #: 例如 `volume_titles` → `--no-volume`、`toc_in_spine` → `--no-toc`（沿用既有 CLI 表面）。
    flag: str = ""
    #: 只对 `in_config=False` 的选项有意义：它们的类型不在 `Config` 里
    value_type: type = str
    negative: bool = False
    in_config: bool = True
    #: 输出路径：不要求已存在
    output: bool = False
    #: 可重复（`--level`）
    multiple: bool = False
    #: 预设层级 2/3/4（非 0 表示这条选项只决定 `levels`）
    level: int = 0
    choices: tuple[str, ...] = ()

    @property
    def kind(self) -> type:
        """取值类型：`Config` 字段按注解，其余看 `value_type`。"""
        return CONFIG_KINDS.get(self.name) or self.value_type

    @property
    def long_flag(self) -> str:
        """长旗标的词干（不含 `--`）：显式 `flag` 优先，否则按 `name` 推。"""
        return self.flag or ("no-" if self.negative else "") + self.name.replace("_", "-")

    @property
    def flags(self) -> tuple[str, ...]:
        long_flag = f"--{self.long_flag}"
        return (f"-{self.short}", long_flag) if self.short else (long_flag,)


OPTIONS: tuple[Option, ...] = (
    # ---- 输入 ----
    Option("input", "输入文件", "输入 txt（也可直接作为位置参数）", "输入", short="i"),
    Option(
        "encoding", "编码",
        f"输入编码，auto 为自动检测；也可填 Python codec 名"
        f"（常用：{'/'.join(ENCODING_CHOICES[1:])}）",
        "输入", short="e",
    ),
    # ---- 输出 ----
    Option("out", "输出文件", "输出文件，缺 .epub 后缀自动补，默认取输入名", "输出", short="o", output=True),
    Option("overwrite", "覆盖已有文件", "输出文件已存在时是否覆盖（默认覆盖）", "输出", negative=True),
    Option("dump_css", "导出 CSS", "把当前生效的 CSS 写到这个文件（不必读输入）", "输出", output=True),
    # ---- 书籍信息 ----
    Option("title", "书名", "留空则从文件名猜《书名》作者：作者", "书籍信息"),
    Option("author", "作者", "留空则从文件名猜；仍留空则不写入元数据", "书籍信息"),
    Option("date", "出版日期", "如 2024-05-13，留空则省略 dc:date（规范允许缺省）", "书籍信息"),
    Option("language", "语言", "语言代码", "书籍信息"),
    Option("cover", "封面图", "留空则先找输入同目录的 cover.*，再退回文字封面页", "书籍信息"),
    Option("text_cover", "文字封面页", "没有封面图时是否生成只含书名/作者的封面页（默认生成）", "书籍信息", negative=True),
    # ---- 章节识别 ----
    Option("volume", "卷标题正则", "h2 + class=volume；留空表示不识别卷标题", "章节识别", in_config=False, level=2),
    Option("chapter", "章标题正则", "h3 + class=chapter；留空表示不识别章标题", "章节识别", in_config=False, level=3),
    Option("section", "节标题正则", "h4 + class=section；默认留空（不启用）", "章节识别", in_config=False, level=4),
    Option(
        "volume_titles", "无卷模式", "卷行是否作为标题（卷正则仍会覆盖内置规则）",
        "章节识别", negative=True, flag="no-volume",
    ),
    Option(
        "level", "额外层级", "额外层级规则，可重复；格式 级别:正则[:类名]，级别 1~6",
        "章节识别", in_config=False, multiple=True,
    ),
    Option("max_title_len", "标题最长字数", "超过这个字数的行即使命中正则也当正文", "章节识别"),
    Option("preface_title", "前言标题", "首个标题之前那些无标题段落归到这一节", "章节识别"),
    # ---- 清理与替换 ----
    Option("clean", "清理文本", "去掉段首段尾空格并删除空行（默认清理）", "清理与替换", negative=True),
    Option(
        "replace_json", "替换规则", "一段 JSON 替换规则（有序列表），与 --replace-file 二选一",
        "清理与替换", in_config=False,
    ),
    Option(
        "replace_file", "替换规则文件", "从 JSON 文件读取替换规则，与 --replace-json 二选一",
        "清理与替换", in_config=False, value_type=Path,
    ),
    # ---- 排版 ----
    Option("indent", "段落缩进", "段落缩进字数，0 为不缩进", "排版"),
    Option("line_height", "行高", "行高，如 1.5", "排版"),
    Option("para_spacing", "段间距", "段间距，带单位，如 1em / 12px", "排版"),
    Option("chapter_align", "章对齐", "章标题对齐方式", "排版", choices=ALIGN_CHOICES),
    Option("volume_align", "卷对齐", "卷标题对齐方式", "排版", choices=ALIGN_CHOICES),
    Option("font", "正文字体", "嵌入到书里的正文字体（ttf/otf/woff/woff2）", "排版"),
    Option("css_file", "外部 CSS 文件", "追加到内置样式之后，可以覆盖内置规则", "排版"),
    # ---- 目录 ----
    Option(
        "toc_in_spine", "书页含目录",
        "目录页是否进正文流（nav 文档无论如何都生成，供阅读器导航面板使用）",
        "目录", negative=True, flag="no-toc",
    ),
    Option("toc_depth", "目录深度", "目录包含到第几级，1~6", "目录"),
    Option("toc_only", "只输出目录", "只输出目录，不生成 EPUB", "目录"),
    Option("toc_format", "目录格式", "只输出目录时的格式：text | json", "目录", choices=FORMATS),
)


def option_groups() -> list[tuple[str, tuple[Option, ...]]]:
    """按 `OPTIONS` 的先后顺序分组，供 CLI 的 `--help` 与 GUI 的分页使用。"""
    groups: dict[str, list[Option]] = {}
    for opt in OPTIONS:
        groups.setdefault(opt.group, []).append(opt)
    return [(name, tuple(items)) for name, items in groups.items()]


def option_default(opt: Option) -> Any:
    """选项的缺省值：Config 字段取 `DEFAULTS`，其余按形态给空值。"""
    if opt.level:
        return next(rule.pattern for rule in DEFAULTS.levels if rule.level == opt.level)
    if opt.in_config:
        return getattr(DEFAULTS, opt.name)
    return () if opt.multiple else ""


# ---------- 原始值 → Config ----------


def build_config(values: Mapping[str, Any]) -> Config:
    """把前端收集到的原始值翻译成 `Config`，出错抛 `ValueError`（消息可直接展示）。

    值的语义与 `Config` 字段一致：反面选项（`--no-clean`）收上来时已经是 `False`。
    留空一律表示「用缺省值」，取值范围由 `Config.validate()` 负责。
    """
    raw = {opt.name: _convert(opt, values.get(opt.name)) for opt in OPTIONS}
    return Config(
        levels=build_levels(_presets(values), raw["level"]),
        replacements=rules_from_source(_text(raw["replace_json"]), raw["replace_file"]),
        **{opt.name: raw[opt.name] for opt in OPTIONS if opt.in_config},
    )


def _convert(opt: Option, value: Any) -> Any:
    """一个选项的原始值 → 收进 `Config`（或 `levels` / `replacements`）的值。"""
    if value is None:
        return option_default(opt)
    if opt.multiple:
        return _lines(value)
    if opt.kind is bool:
        return bool(value)
    if opt.kind is int:
        return _integer(opt, value)
    if opt.kind is Path:
        return _path(opt, value)
    text = _text(value)
    return option_default(opt) if text is None else text


def _text(value: Any) -> str | None:
    """字符串选项的值；未给或只填了空白都视同未给。"""
    text = "" if value is None else str(value).strip()
    return text or None


def _lines(value: Any) -> tuple[str, ...]:
    """多值选项（`--level`）：GUI 给多行文本，CLI 给元组，都收成去掉空行的元组。"""
    items = value.splitlines() if isinstance(value, str) else value or ()
    return tuple(str(item).strip() for item in items if str(item).strip())


def _integer(opt: Option, value: Any) -> int:
    text = _text(value)
    if text is None:
        return int(option_default(opt))
    try:
        return int(text)
    except ValueError:
        raise ValueError(f"{opt.label}需为整数，收到：{value!r}") from None


def _path(opt: Option, value: Any) -> Path | None:
    """路径选项：输出路径不必存在；输入文件、封面、字体、CSS、规则文件必须存在。"""
    text = _text(value)
    if text is None:
        return None
    path = Path(text)
    if not opt.output and not path.is_file():
        raise ValueError(f"{opt.label}不存在：{path}")
    return path


def _presets(values: Mapping[str, Any]) -> dict[str, str]:
    """卷/章/节三条预设正则：未给用内置值，给了空串表示不识别该层级。"""
    return {
        opt.name: option_default(opt) if values.get(opt.name) is None else str(values[opt.name])
        for opt in OPTIONS
        if opt.level
    }
