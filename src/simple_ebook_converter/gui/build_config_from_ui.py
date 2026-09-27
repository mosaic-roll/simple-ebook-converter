"""界面字段 → `Config`。**纯数据转换，不 import tkinter。**

这是 `core.options.build_config()` 的唯一调用方，也是 GUI 与 CLI 对齐的地方。
单独拆成一个不依赖 Tk 的模块，是因为它需要被直接测：`tests/gui/` 里两个测试文件
都只 import 这个模块，不需要起窗口。

## `values` 的键名（最容易错的地方）

本模块产出的 `values` 字典交给 `build_config()`，而**它只读它认识的键**：

    Config(
        levels=build_levels(_level_specs(values)),
        replacements=rules_from_source(values.get("replace_json"), ...),
        **{opt.name: _convert(opt, values.get(opt.name)) for opt in OPTIONS if opt.in_config},
    )

多写一个不认识的键（例如把 `toc_in_spine` 写成 `no_toc`）**不报错、不警告，那个
设置就是静默丢了**。所以：

* 输入键名是 `core.options.OPTIONS` 里的 `opt.name`，**不是** `Config` 的字段名 ——
  `levels` 是 `Config` 的字段（由 core 合成），输入键却是单数的 `level`；
* 三个层级「不识别」的表达是**显式空串 `""`**，不是省略该键（省略 = 用缺省正则）。

`tests/gui/test_options_coverage.py` 双向断言这两条。
"""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..core.config import Config
from ..core.options import build_config
from ..core.replace import Rule, rules_from_rows, rules_to_json

#: CSS 模式：单一枚举，与 webview 版一致（不拆成两个字段）
CSS_NONE, CSS_APPEND, CSS_OVERRIDE = "none", "append", "override"
CSS_MODES = (CSS_NONE, CSS_APPEND, CSS_OVERRIDE)

#: 三条内置层级，class 名就是 `opt.name`（core 侧的约定）
LEVEL_NAMES = ("volume", "chapter", "section")


@dataclass
class BasicValues:
    """「基础」页签的字段。全部是用户直接填的原始值，不做任何解释。"""

    input: str = ""
    encoding: str = ""
    out: str = ""
    overwrite: bool = True
    clean: bool = True
    title: str = ""
    author: str = ""
    date: str = ""
    language: str = ""
    cover: str = ""
    text_cover: bool = True


@dataclass
class IdentifyValues:
    """「识别」页签的字段。

    额外层级有**两份**表示，用途不同，不能互相替代：

    * `level_rows`：编辑器/设置文件用的行结构（`{h, class_name, regex}`），
      能表达「这一行还没填完」；
    * `level_specs`：交给 core 的 `hN[.class]:正则` 规格串。

    只留后者会丢掉未填完的行，只留前者则每个调用点都得自己拼规格、拼错就是 core
    静默忽略该层。`level_rows` 是真源，`level_specs` 由 `option_values()` 现拼。
    """

    #: 层级名 → 正则。**三态**：`None` = 用户没动过（跟随 core 缺省）、
    #: `""` = 显式关闭该层级、非空 = 显式正则。语义见模块 docstring。
    levels: dict[str, str | None] = field(default_factory=dict)
    #: 额外层级的行（真源）
    level_rows: list[dict] = field(default_factory=list)
    max_title_len: int = 35
    preface_title: str = ""

    @property
    def level_specs(self) -> list[str]:
        """把 `level_rows` 拼成 core 认的规格串。格式归 core 所有，**这里不拆开重组**。

        `hN` + 可选 `.class` + 冒号 + 正则。冒号后整段都是正则，所以正则里可以自带
        冒号（`h5:^a:b` 合法），不转义。跳过空正则的行：那等于「没填」，交给
        `levels.build_levels` 当没配。
        """
        specs: list[str] = []
        for row in self.level_rows:
            regex = str(row.get("regex", "")).strip()
            if not regex:
                continue
            head = f"h{row.get('h', '').lstrip('h')}"
            class_name = str(row.get("class_name", "")).strip()
            if class_name:
                head = f"{head}.{class_name}"
            specs.append(f"{head}:{regex}")
        return specs


@dataclass
class TypographyValues:
    """「排版」页签的字段。

    `indent` 是 int；`line_height` / `para_spacing` 是**字符串**，因为它们是 CSS
    长度值（`1.5` / `150%` / `1.5em` 都合法），用 Spinbox 会把用户锁死在数字上。
    """

    indent: int = 2
    line_height: str = ""
    para_spacing: str = ""
    volume_align: str = ""
    chapter_align: str = ""
    font: str = ""
    css_mode: str = CSS_NONE
    css_path: str = ""
    css_text: str = ""


@dataclass
class TocSettings:
    """目录面板底部的设置。"""

    toc_depth: int = 6
    #: 正面表述。core 里是 `toc_in_spine`，**不是** `no_toc`（后者会被静默丢弃）
    toc_in_spine: bool = True


@dataclass
class UiValues:
    """整张界面的原始值。`build_config_from_ui()` 收这个。"""

    basic: BasicValues = field(default_factory=BasicValues)
    identify: IdentifyValues = field(default_factory=IdentifyValues)
    typography: TypographyValues = field(default_factory=TypographyValues)
    toc: TocSettings = field(default_factory=TocSettings)
    #: `(查找, 替换为, 阶段)` 三元组列表；阶段可以是 core 的中文标签
    rules: list[tuple[str, str, str]] = field(default_factory=list)


def build_config_from_ui(values: UiValues) -> Config:
    """界面原始值 → `Config`，出错抛 `ValueError`（消息可直接展示）。

    **注意临时 CSS 的生命周期**：勾了 CSS 但只改了内联文本时，这里会落一个临时
    文件。core 读它是在生成时（工作线程），所以这个文件**不能在返回前删** ——
    生成的收尾处负责清理（`App._cleanup_temp_css`）。真要拿到那个路径去跟踪，
    调 `option_values()` 自己传 `write_temp_css`。

    这里**主动调 `validate()`**：`build_config()` 只翻译不校验（校验归
    `pipeline.resolve()`，那是工作线程里跑）。界面上一个填错的日期如果等到工作
    线程才报，用户看到的是「生成失败」而不是「日期格式错误」——问题定位从一行
    消息变成一段排查。同步校验能在开线程之前就拦下并弹窗。
    """
    cfg = build_config(option_values(values, write_temp_css=write_temp_css))
    cfg.validate()
    return cfg


def option_values(values: UiValues, *, write_temp_css=None) -> dict[str, Any]:
    """`UiValues` → `build_config()` 认的键名字典。

    `write_temp_css` 只在「勾了 CSS 且没给路径、只改了文本」时被调用，注入是为了
    让测试不落盘、以及让调用方跟踪临时文件的路径。
    """
    if write_temp_css is None:
        write_temp_css = globals()["write_temp_css"]
    out: dict[str, Any] = {}

    # ---- 基础 ----
    basic = values.basic
    out["input"] = basic.input
    out["encoding"] = basic.encoding
    out["out"] = basic.out
    out["overwrite"] = basic.overwrite
    out["clean"] = basic.clean
    out["title"] = basic.title
    out["author"] = basic.author
    out["date"] = basic.date
    out["language"] = basic.language
    out["cover"] = basic.cover
    out["text_cover"] = basic.text_cover

    # ---- 识别 ----
    for name in LEVEL_NAMES:
        pattern = values.identify.levels.get(name)
        # 没动过（None）就不写这个键：core 会用 option_default。写成 "" 才是关闭。
        if pattern is not None:
            out[name] = pattern
    # 额外层级走**单数** `level`（`levels` 是 Config 的字段名，不是输入键）
    if specs := values.identify.level_specs:
        out["level"] = list(specs)
    out["max_title_len"] = values.identify.max_title_len
    out["preface_title"] = values.identify.preface_title

    # ---- 替换 ----
    # core 只认一段 JSON 文本（`replace_json`），表格只是这个界面上的写法。
    # 空规则就不写这个键，免得覆盖掉别处可能给的值。
    if rules := rules_from_rows(values.rules):
        out["replace_json"] = rules_to_json(rules)

    # ---- 排版 ----
    typo = values.typography
    out["indent"] = typo.indent
    out["line_height"] = typo.line_height
    out["para_spacing"] = typo.para_spacing
    out["volume_align"] = typo.volume_align
    out["chapter_align"] = typo.chapter_align
    out["font"] = typo.font
    _add_css(out, typo, write_temp_css)

    # ---- 目录 ----
    out["toc_depth"] = values.toc.toc_depth
    out["toc_in_spine"] = values.toc.toc_in_spine  # 正面表述，不是 no_toc

    return out


def _add_css(out: dict[str, Any], typo: TypographyValues, write_temp_css) -> None:
    """按 `css_mode` 写 `css_file` / `css_append` 中的**一个**键。

    两个键在 core 里互斥（`Config.validate()` 会因为都给上而报错），所以这里不是
    「两个都写、让 core 去挑」。
    """
    mode = typo.css_mode
    if mode not in CSS_MODES or mode == CSS_NONE:
        return
    key = "css_file" if mode == CSS_OVERRIDE else "css_append"
    path = typo.css_path.strip()
    if path:
        out[key] = path
    elif typo.css_text.strip():
        # 只改了文本没给路径：落一份临时文件，core 只认路径。
        out[key] = str(write_temp_css(typo.css_text))


def write_temp_css(text: str) -> Path:
    """把界面里编辑的 CSS 写到临时文件，返回路径。

    core 的一切都走文件，没有「一段 CSS 字符串」这个入口，所以界面上改完的文本必须
    先落盘。**生命周期由调用方负责**：core 是在工作线程里才读它的，读完才能删。
    用 `mkstemp` 而不是 `NamedTemporaryFile` —— 后者在 Windows 上不手动 close 就
    无法再次打开，而 core 要用路径重新打开。
    """
    handle, name = tempfile.mkstemp(prefix="sec-style-", suffix=".css", text=True)
    with os.fdopen(handle, "w", encoding="utf-8") as fh:
        fh.write(text)
    return Path(name)


# ---------- 目录条目：稳定键与预览替换 ----------


def entry_id(entry: dict) -> str:
    """目录条目的稳定键：`起:止:raw_title`。

    重扫后按它复原勾选，所以**不能**用行号或标题单独做键 ——
    `scan_toc` 的结果会随识别设置变化，行号会漂、标题会被替换规则改掉。
    """
    start, end = entry.get("lines", (0, 0))
    return f"{start}:{end}:{entry.get('raw_title', '')}"


def preview_replacements(entries: list[dict], rules: list[Rule]) -> dict[str, str]:
    """目录条目 → 替换后的标题，`{entry_id: 结果}`。

    预览只体现 `raw` 阶段：`html` 阶段是要塞标签给阅读器渲染的，在纯文本目录里
    没有意义（与 `gui设计webview版.md` 一致）。
    """
    from ..core.replace import replacers_by_stage

    raw, _ = replacers_by_stage(rules)
    return {entry_id(e): raw.text(e.get("raw_title", "")) for e in entries}
