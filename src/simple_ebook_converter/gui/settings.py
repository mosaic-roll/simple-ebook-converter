"""界面设置的持久化：`settings.json`。

刻意不引入 `platformdirs` —— 为一个配置目录加一个依赖不划算，而各平台的标准位置
本来就能用标准库推出来（Windows 的 `%APPDATA%`、XDG 的 `$XDG_CONFIG_HOME`、
macOS 的 `~/Library/Application Support`）。装了 `platformdirs` 就用它。

**这里存的是界面状态，不是 `build_config()` 的入参。** 两套 schema 不要混：键名
故意跟 `values` 不同（例如 `level` 在 `values` 里是 core 的层级规格、在这里是编辑器的行）。
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

#: 配置版本。结构变了就 +1，旧文件按缺省处理而不是硬读
VERSION = 1

#: 设置损坏时给状态栏看的提示
BROKEN_MESSAGE = "设置损坏，已用默认值"

#: 三条内置层级的 class 名（= core 的选项名）。`levels` 的键只认这三个：
#: 多出来的名字会被 IdentifyTab 拿去查表，查不到就是 KeyError。
LEVEL_NAMES = ("volume", "chapter", "section")

#: 字段名 → 期望类型。用于逐字段校验，避免一个坏字段毁掉整份设置。
#: 缺项即「不认识」→ `from_dict` 直接判损坏。
_TYPES: dict[str, type | tuple[type, ...]] = {
    "version": int,
    "window": dict,
    "encoding": str,
    "overwrite": bool,
    "clean": bool,
    "date": str,
    "language": str,
    "text_cover": bool,
    "levels": dict,
    "level": list,
    "max_title_len": int,
    "preface_title": str,
    "indent": int,
    "line_height": str,
    "para_spacing": str,
    "volume_align": str,
    "chapter_align": str,
    "css_mode": str,
    "css_path": str,
    "font": str,
    "toc_depth": int,
    "toc_in_spine": bool,
    "replacements": list,
}


@dataclass
class Settings:
    """会被记住的东西。

    用**扁平字段**而不是嵌 `BasicValues` / `IdentifyValues` 那几个 dataclass：设置文件
    是长期躺在用户磁盘上的，扁平结构在损坏时能逐字段降级（`from_dict` 就是这么做的），
    嵌结构一旦有一层类型不对就整块作废。

    当次的输入/输出路径、书名作者**不存** —— 换一本书就该重来。
    """

    version: int = VERSION
    window: dict[str, int] = field(default_factory=lambda: {"w": 1200, "h": 800})
    #: 源文本编码。空串 = 不指定，交给 core 缺省。
    #: 这是**该存的**：GB18030 / UTF-8 是源文件的属性，不是「换本书就该重来」的东西，
    #: 用户处理一批 txt 时会一直用同一个编码，每次重填纯属折磨。
    encoding: str = ""
    overwrite: bool = True
    clean: bool = True
    #: 书里的日期。空串 = 不写。同一本书反复改样式时它是稳定的，不该丢。
    date: str = ""
    language: str = ""
    text_cover: bool = True
    #: 层级名 → 持久化的三态。**存字符串**，不存 `{active, regex}` 对象：
    #: 那个写法有 `active: false` 但 `regex: "^第.+"` 的自相矛盾状态（该听谁的？）。
    #: 三层语义只有一个维度 —— 「这条层级最终用什么正则」：
    #: `None` 没动过（跟随 core 缺省）/ `""` 显式关闭 / 非空 显式正则。
    levels: dict[str, str | None] = field(default_factory=dict)
    #: 额外层级，存编辑器的行（`{h, class_name, regex}`），不是 core 的规格串
    level: list[dict] = field(default_factory=list)
    max_title_len: int = 35
    preface_title: str = ""
    indent: int = 2
    #: 行高/段间距是 CSS 长度值，存字符串（`1.5` / `150%` / `1.5em` 都合法）
    line_height: str = ""
    para_spacing: str = ""
    volume_align: str = ""
    chapter_align: str = ""
    css_mode: str = ""
    css_path: str = ""
    font: str = ""
    toc_depth: int = 6
    #: 正面表述。core 里是 `toc_in_spine`，不是 `no_toc`
    toc_in_spine: bool = True
    #: `(查找, 替换为, 阶段标签, 是否启用)` 四元组列表
    replacements: list[list[str | bool]] = field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps(asdict_shallow(self), ensure_ascii=False, indent=2)

    @classmethod
    def from_dict(cls, data: Any) -> tuple["Settings", bool]:
        """读回设置，返回 `(设置, 是否损坏)`。

        逐字段取、类型不对就用缺省 —— 一个坏字段不该让整份设置作废。
        版本对不上则整份按缺省处理：不拿旧结构硬猜。
        """
        if not isinstance(data, dict):
            return cls(), True
        if data.get("version") != VERSION:
            return cls(), True

        settings = cls()
        damaged = False
        for name, value in data.items():
            if name not in _TYPES:
                damaged = True  # 不认识的键：可能来自更新的版本，不静默丢
                continue
            if not _type_ok(name, value):
                damaged = True  # 类型不对：用缺省继续
                continue
            if name == "levels" and set(value) - set(LEVEL_NAMES):
                # 内置层级名只该有这三个。多出来的键会被 IdentifyTab 拿去查表而 KeyError，
                # 所以丢掉并报损坏 —— 丢掉是为了能继续用，报损坏是为了让用户知道少了东西。
                damaged = True
            setattr(settings, name, _coerce(name, value))
        return settings, damaged

    @classmethod
    def from_values(cls, values) -> "Settings":
        """`UiValues` → 只存该记的那些字段。**不记输入/输出路径。**"""
        basic, identify, typography, toc = (
            values.basic,
            values.identify,
            values.typography,
            values.toc,
        )
        return cls(
            encoding=basic.encoding,
            overwrite=basic.overwrite,
            clean=basic.clean,
            date=basic.date,
            language=basic.language,
            text_cover=basic.text_cover,
            levels=dict(identify.levels),
            level=[dict(row) for row in identify.level_rows],
            max_title_len=identify.max_title_len,
            preface_title=identify.preface_title,
            indent=typography.indent,
            line_height=typography.line_height,
            para_spacing=typography.para_spacing,
            volume_align=typography.volume_align,
            chapter_align=typography.chapter_align,
            css_mode=typography.css_mode,
            css_path=typography.css_path,
            font=typography.font,
            toc_depth=toc.toc_depth,
            toc_in_spine=toc.toc_in_spine,
            replacements=[list(row) for row in values.rules],
        )

    def to_values(self):
        """`Settings` → `UiValues`。没存的字段（输入/输出路径等）留空。"""
        from .build_config_from_ui import (
            BasicValues,
            IdentifyValues,
            TocSettings,
            TypographyValues,
            UiValues,
        )

        return UiValues(
            basic=BasicValues(
                encoding=self.encoding,
                overwrite=self.overwrite,
                clean=self.clean,
                date=self.date,
                language=self.language,
                text_cover=self.text_cover,
            ),
            identify=IdentifyValues(
                levels=dict(self.levels),
                level_rows=[dict(row) for row in self.level],
                max_title_len=self.max_title_len,
                preface_title=self.preface_title,
            ),
            typography=TypographyValues(
                indent=self.indent,
                line_height=self.line_height,
                para_spacing=self.para_spacing,
                volume_align=self.volume_align,
                chapter_align=self.chapter_align,
                font=self.font,
                css_mode=self.css_mode,
                css_path=self.css_path,
            ),
            toc=TocSettings(toc_depth=self.toc_depth, toc_in_spine=self.toc_in_spine),
            rules=[tuple(row) for row in self.replacements],  # type: ignore[misc]
        )

    @classmethod
    def load(cls) -> tuple["Settings", bool]:
        """从磁盘读。文件不存在不算损坏；读不了或解不开算损坏（用缺省启动）。"""
        path = config_path()
        try:
            raw = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return cls(), False
        except OSError:
            return cls(), True
        try:
            return cls.from_dict(json.loads(raw))
        except json.JSONDecodeError:
            return cls(), True

    def save(self) -> Path | None:
        """写回磁盘，返回写到的路径。写不了返回 `None`。

        设置是可选功能，写不了（只读目录、权限）不该让 GUI 崩或弹错。
        """
        path = config_path()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(self.to_json(), encoding="utf-8")
        except OSError:
            return None
        return path


# ---------- 路径与编解码 ----------


def config_dir() -> Path:
    """配置文件所在目录。装了 `platformdirs` 就用它，否则按平台标准位置推。"""
    try:
        import platformdirs

        return Path(platformdirs.user_config_dir("simple-ebook-converter"))
    except ImportError:
        pass
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / "simple-ebook-converter"
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "simple-ebook-converter"


def config_path() -> Path:
    return config_dir() / "settings.json"


def _type_ok(name: str, value: Any) -> bool:
    kind = _TYPES[name]
    # bool 是 int 的子类，`True` 混进 int 字段要当成损坏
    if kind is int and isinstance(value, bool):
        return False
    return isinstance(value, kind)


def _coerce(name: str, value: Any) -> Any:
    """转成字段该有的形态。`levels` 存的是 `str | None` 的字典，容许旧的对象写法。"""
    if name == "levels":
        return {key: _level_pattern(val) for key, val in value.items() if key in LEVEL_NAMES}
    return value


def _level_pattern(value: Any) -> str | None:
    """`levels` 的值 → 正则字符串。旧版对象写法取 `pattern`；其余给 `None`（跟随缺省）。"""
    if isinstance(value, dict):
        pattern = value.get("pattern")
        return pattern if isinstance(pattern, str) else None
    return value if isinstance(value, str) or value is None else None


def asdict_shallow(settings: Settings) -> dict[str, Any]:
    """`dataclasses.asdict` 的一层版本。`levels` 已经是 `{str: str|None}`，不需要递归。"""
    from dataclasses import fields

    return {f.name: getattr(settings, f.name) for f in fields(settings)}


def load_settings() -> Settings:
    """读设置，损坏就用缺省。这层不返回「是否损坏」——调用方只看值。"""
    return Settings.load()[0]


def save_settings(data: Settings) -> Path | None:
    return data.save()
