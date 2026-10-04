"""选项表：命令行参数与 GUI 表单的唯一真源。

表里只写「前端要什么」——选项名、中文标签、说明、分组、旗标形态；其余一律从真源推出：

- `name` 就是 `Config` 的字段名，取值类型与默认值按字段注解取；名字不是 `Config`
  字段的选项不进 `Config`，值在前端收集后合成（`--volume/--chapter/--level`
  合成 `levels`，`--replace-rules` 合成 `replacements`，`--no-volume`
  表示无卷模式）；
- `negative` 的选项命令行写 `--no-<name>`，界面按正面说法显示，两个前端收上来的值
  都已经是 `Config` 的正面语义，`build_config()` 因此不必认识 `--no-xxx`；
- 卷/章是两条预设的 `--level` 规格（class 名 = 选项名），`--no-volume` 等同
  清空卷正则。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, get_args, get_type_hints

from .config import (
    ALIGN_CHOICES,
    DEFAULTS,
    FORMATS,
    LEVEL_PRESETS,
    Config,
    LevelRule,
)
from .encoding import ENCODING_CHOICES
from .levels import build_rules, is_valid_level
from .replace import Rule, rules_from_file
from .validation import field_error


def _config_kinds() -> dict[str, type]:
    """`Config` 字段名 → 取值类型。`Path | None` 取 `Path`；只认 str/int/bool/Path。"""
    kinds: dict[str, type] = {}
    for name, hint in get_type_hints(Config).items():
        kind = next((arg for arg in get_args(hint) if isinstance(arg, type)), hint)
        if kind in (str, int, bool, Path):
            kinds[name] = kind
    return kinds


CONFIG_KINDS = _config_kinds()

#: 预设层级：class 名（= 选项名）→ 级别。卷/章是两条预设的 `--level` 规格。
_LEVEL_BY_NAME = {name: level for level, name, _, _ in LEVEL_PRESETS}


@dataclass(frozen=True)
class Option:
    """一个可配置项，值的语义与 `Config` 字段一致。"""

    name: str
    label: str
    help: str
    group: str
    short: str = ""
    #: 长旗标词干（不含 `--`）。留空按 `name` 推；个别旗标名与字段名不同时显式写，
    #: 例如 `toc_in_spine` → `--no-toc-page`（目录照生成，只是不作为书页出现）。
    flag: str = ""
    #: 只对不进 `Config` 的选项有意义：它们的类型不在 `Config` 注解里
    value_type: type = str
    negative: bool = False
    #: 输出路径：不要求已存在
    output: bool = False
    #: 空串是一个**有意义的值**，不是「没给」。
    #:
    #: `cover` 用它：`--cover ""` 表示显式不要封面（与 GUI 清空封面框同义），而 `None`
    #: 才是没指定、该去自动发现。click 的 `Path(exists=True)` 会把空串当非法路径挡掉，
    #: 所以这种选项不能用 click.Path 收，交给 `build_config()` 判。
    allow_empty: bool = False
    #: 可重复（`--level`）
    multiple: bool = False
    choices: tuple[str, ...] = ()

    @property
    def kind(self) -> type:
        """取值类型：`Config` 字段按注解，其余看 `value_type`。"""
        return CONFIG_KINDS.get(self.name) or self.value_type

    @property
    def in_config(self) -> bool:
        """值是否直接进 `Config`：名字是 `Config` 字段即是，否则由 `build_config()` 合成。"""
        return self.name in CONFIG_KINDS

    @property
    def preset_level(self) -> int:
        """预设层级的级别数字（卷=2 / 章=3）；0 = 不是预设层级。

        叫 `preset_level` 而不是 `level`：读代码时 `opt.level` 像是「是不是层级选项」，
        实际是个数字。多值选项 `--level` 自己不在这里——它的值是一串规则，不是级别。
        """
        return _LEVEL_BY_NAME.get(self.name, 0)

    @property
    def long_flag(self) -> str:
        """长旗标的词干（不含 `--`）：显式 `flag` 优先，否则按 `name` 推。"""
        return self.flag or ("no-" if self.negative else "") + self.name.replace(
            "_", "-"
        )

    @property
    def flags(self) -> tuple[str, ...]:
        long_flag = f"--{self.long_flag}"
        return (f"-{self.short}", long_flag) if self.short else (long_flag,)


OPTIONS: tuple[Option, ...] = (
    # ---- 输入 ----
    Option("input", "输入文件", "输入 txt（也可直接作为位置参数）", "输入", short="i"),
    Option(
        "encoding",
        "编码",
        f"输入编码，auto 为自动检测；也可填 Python codec 名"
        f"（常用：{'/'.join(ENCODING_CHOICES[1:])}）",
        "输入",
        short="e",
    ),
    # ---- 输出 ----
    Option(
        "out",
        "输出文件",
        "输出文件，缺 .epub 后缀自动补，默认取输入名",
        "输出",
        short="o",
        output=True,
    ),
    Option(
        "overwrite",
        "覆盖已有文件",
        "输出文件已存在时是否覆盖（默认覆盖）",
        "输出",
        negative=True,
    ),
    Option(
        "dump_css",
        "导出 CSS",
        "把内置 CSS 模板写到这个文件（不必读输入，不受 --css-file/--css-append 影响）",
        "输出",
        output=True,
    ),
    # ---- 书籍信息 ----
    Option("title", "书名", "留空则从文件名「《书名》作者：作者」提取", "书籍信息"),
    Option("author", "作者", "留空则从文件名猜；仍留空则不写入元数据", "书籍信息"),
    Option("date", "出版日期", "如 1949-10-01，留空则不写入", "书籍信息"),
    Option("language", "语言", "语言代码", "书籍信息"),
    Option("description", "简介", "书籍简介，留空则不写入 `dc:description`", "书籍信息"),
Option(
        "cover",
        "封面图",
        "封面图片路径；省略则自动发现封面",
        "书籍信息",
        allow_empty=True,
    ),
    Option(
        "cover_discovery",
        "自动发现封面",
        "没给封面图时是否自动发现同目录的 cover.*（默认发现）",
        "书籍信息",
        negative=True,
    ),
    Option(
        "text_cover",
        "文字封面页",
        "没有封面图时是否生成只含书名/作者的封面页（默认生成）",
        "书籍信息",
        negative=True,
    ),
    # ---- 章节识别 ----
    Option(
        "volume", "卷标题正则", "h2 + class=volume；留空表示不识别卷标题", "章节识别"
    ),
    Option(
        "chapter", "章标题正则", "h3 + class=chapter；留空表示不识别章标题", "章节识别"
    ),
    Option(
        "no_volume",
        "无卷模式",
        "卷行不当标题，等同清空卷标题正则；显式给 --volume 时以正则为准",
        "章节识别",
        value_type=bool,
    ),
    Option(
        "level",
        "额外层级",
        "额外层级规则，可重复；格式 hN[.class]:正则（如 h1.part:^Part），与 CSS 选择器一致；"
        "同一级可给多条，先写的优先（内置卷/章还在它们前面）",
        "章节识别",
        multiple=True,
    ),
    Option(
        "max_title_len",
        "标题最长字数",
        "超过这个字数的行直接当正文，不参与匹配",
        "章节识别",
    ),
    Option(
        "exclude",
        "排除规则",
        "排除规则；行命中该正则时不作为标题",
        "章节识别",
    ),
    Option(
        "preface_title", "前言标题", "首个标题之前那些无标题段落归到这一节", "章节识别"
    ),
    # ---- 清理与替换 ----
    Option(
        "clean",
        "清理文本",
        "去掉段首段尾空格并删除空行（默认清理）",
        "清理与替换",
        negative=True,
    ),
    Option(
        "replace_rules",
        "替换规则文件",
        "从 JSON 文件读取替换规则（一个有序列表）；"
        "每条含 pattern / replace / stage（raw|html）/ enabled",
        "清理与替换",
        value_type=Path,
    ),
    # ---- 排版 ----
    Option("indent", "段落缩进", "段落缩进字数，0 为不缩进", "排版"),
    Option("line_height", "行高", "行高，如 1.5", "排版"),
    Option("para_spacing", "段间距", "段间距，带单位，如 1em / 12px", "排版"),
    Option("chapter_align", "章对齐", "章标题对齐方式", "排版", choices=ALIGN_CHOICES),
    Option("volume_align", "卷对齐", "卷标题对齐方式", "排版", choices=ALIGN_CHOICES),
    Option("para_align", "正文对齐", "正文默认对齐方式", "排版", choices=ALIGN_CHOICES),
    Option("font", "正文字体", "嵌入到书里的正文字体（ttf/otf/woff/woff2）", "排版"),
    Option(
        "css_file",
        "外部 CSS 文件",
        "替代内置样式：给了它就用这一份（先用 --dump-css 导一份内置模板作起点）",
        "排版",
    ),
    Option(
        "css_append",
        "附加 CSS 文件",
        "追加在内置样式之后，用于少量覆盖（与 --css-file 互斥）",
        "排版",
    ),
    # ---- 目录 ----
    Option(
        "toc_in_spine",
        "书页含目录",
        "目录页是否进正文流（阅读器导航目录不受影响，始终生成）",
        "目录",
        negative=True,
        flag="no-toc-page",
    ),
    Option("toc_depth", "目录深度", "目录包含到第几级，1~6", "目录"),
    Option(
        "toc_file",
        "目录树文件",
        "从 JSON 目录树生成：跳过正则解析，按行号从输入取正文；"
        "标题用文件里的值，仍会做清理与替换（--toc-only --toc-format json 导出的目录可编辑后再传入）",
        "目录",
    ),
    Option("toc_only", "只输出目录", "只输出目录，不生成 EPUB", "目录"),
    Option(
        "toc_format",
        "目录格式",
        "只输出目录时的格式：text | json",
        "目录",
        choices=FORMATS,
    ),
)


def option_groups() -> list[tuple[str, tuple[Option, ...]]]:
    """按 `OPTIONS` 的先后顺序分组，供 CLI 的 `--help` 与 GUI 的分页使用。"""
    groups: dict[str, list[Option]] = {}
    for opt in OPTIONS:
        groups.setdefault(opt.group, []).append(opt)
    return [(name, tuple(items)) for name, items in groups.items()]


def option_default(opt: Option) -> Any:
    """选项的默认值：Config 字段取 `DEFAULTS`，其余按形态给空值。"""
    if opt.preset_level:
        return next(
            rule.pattern for rule in DEFAULTS.levels if rule.level == opt.preset_level
        )
    if opt.in_config:
        return getattr(DEFAULTS, opt.name)
    return () if opt.multiple else (False if opt.kind is bool else "")


def option_label(name: str) -> str:
    """按名字取选项的中文标签，给 GUI 摆控件用。

    GUI 的控件标签一律从这张表出（见 `defaults.default_text` 的同类约定），不手抄——
    抄的那份总会和 `--help` 对不上。
    """
    return _option(name).label


# ---------- 原始值 → Config ----------


def _option(name: str) -> Option:
    """按名字取选项表里的一条（同名选项唯一）。"""
    return next(opt for opt in OPTIONS if opt.name == name)


def build_config(
    values: Mapping[str, Any],
    *,
    replacements: list[Rule] | None = None,
) -> Config:
    """把前端收集到的原始值翻译成 `Config`，出错抛 `ValueError`（消息可直接展示）。

    值的语义与 `Config` 字段一致：反面选项（`--no-clean`）收上来时已经是 `False`。
    留空一律表示「用默认值」，取值范围由 `validation.validate_config()` 负责。

    `replacements` 留给 GUI：它的替换规则来自表格卡片，不经文件。给了就直接收下，
    不再走 `--replace-rules` 那条路——否则 GUI 只能先造 `Config` 再事后改字段。
    `None`（CLI 的情形）表示按 `--replace-rules` 读文件。
    """
    values = dict(values)
    if values.pop("no_volume", None) and values.get("volume") is None:
        values["volume"] = ""  # --no-volume only wins when --volume is not given
    # `--cover ""` 与 GUI 把封面框清空是同一个意思：显式说不要封面。`_path()` 会把空串
    # 归一成 `None`（那是 `Config.cover` 的类型要求），不在这儿记一笔的话，「显式不要」
    # 就被抹成了「没给」，自动发现又去同目录翻一张 cover.png 出来——正好是用户清空框
    # 想避免的那件事。所以在这里直接把发现关掉，结果与 `cover_for("")` 一致。
    #
    # 空路径**压过**发现开关，跟 GUI 一样：`cover_for("")` 是在看 `discovery` 之前就返回
    # None 的，命令行不能有第二种解释。只认「给了但为空」（`values["cover"] is not None`
    # 且归一后为空），「没给」不碰。
    if values.get("cover") is not None and _text(values["cover"]) is None:
        values["cover_discovery"] = False
    if replacements is None:
        replacements = rules_from_file(
            _path(_option("replace_rules"), values.get("replace_rules"))
        )
    return Config(
        levels=_level_rules(values),
        replacements=replacements,
        **{
            opt.name: _convert(opt, values.get(opt.name))
            for opt in OPTIONS
            if opt.in_config
        },
    )


def is_valid(name: str, value: Any) -> bool:
    """某个选项的原始值能不能收进 `Config`。

    给 GUI 存盘前用：手上有的是**单个字段的原始文本**，需要的是「这一个值合不合法」，
    而 `validate_config()` 一次验整份配置。所以这条必须跟生成那条路**用同一套规则**，
    不能另写一份——否则两边会漂移。

    两层，不重叠：`_convert()` 管「能不能转成对的类型」（`"abc"` 转不成 int），
    `validation.field_error()` 管「转成类型之后取值合不合法」（`-1` 是 int 但缩进不能为负）。
    加新选项不需要在这里登记，`OPTIONS` 与 `validation._CHECKS` 各自是真源。
    """
    opt = _option(name)
    if opt.preset_level:
        # 卷/章收进 `Config.levels` 而不是独立字段，正则合法性由 levels 判。
        # `None` 是「没指定」——`_level_rules()` 会填内置正则，与 `build_config()` 一致。
        level = opt.preset_level
        if value is None:
            return is_valid_level(LevelRule(level, option_default(opt), opt.name))
        return is_valid_level(LevelRule(level, value, opt.name))
    if not opt.in_config:
        return True
    try:
        typed = _convert(opt, value)
    except ValueError:
        return False
    return field_error(name, typed) is None


def _level_rules(values: Mapping[str, Any]) -> list[LevelRule]:
    """卷/章两条预设 + 前端给的额外层级（如 h4 小节）→ 校验排序后的 `Config.levels`。

    预设未给用内置正则，显式空串表示不识别该层级；class 名就是选项名。预设两条排在
    额外层级前面——这就是同级的优先级（`parse()` 照此试）。

    `values["level"]` 里已经是 `LevelRule`：GUI 从三个输入框直接构造，CLI 把
    `--level hN[.class]:正则` 交给 `parse_level_spec()` 拆好再传进来。core 不再
    经手那个字符串——它是命令行参数格式，不是内部表示。
    """
    presets = [
        LevelRule(
            opt.preset_level,
            option_default(opt) if values.get(opt.name) is None else values[opt.name],
            opt.name,
        )
        for opt in OPTIONS
        if opt.preset_level
    ]
    return build_rules([*presets, *(values.get("level") or ())])


def _convert(opt: Option, value: Any) -> Any:
    """一个选项的原始值 → 收进 `Config` 的值。

    只服务于「一个选项对应一个 `Config` 字段」的选项。`--level` 不是 `Config` 字段，
    它的值经 `_level_rules()` 合成 `Config.levels`（一个列表），不走这条单值转换。
    """
    if value is None:
        return option_default(opt)
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
