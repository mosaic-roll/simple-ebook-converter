"""界面设置的持久化：`settings.json`。

刻意不引入 `platformdirs` —— 为一个配置目录加一个依赖不划算，而各平台的标准位置
本来就能用标准库推出来（Windows 的 `%APPDATA%`、XDG 的 `$XDG_CONFIG_HOME`、
macOS 的 `~/Library/Application Support`）。装了 `platformdirs` 就用它。

**这里存的是界面状态，不是 `build_config()` 的入参。** 两套 schema 不要混：键名
故意跟 `values` 不一样（例如 `level` 在两边含义不同）。
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

#: 配置版本。结构变了就 +1，旧文件按缺省处理而不是硬读
VERSION = 1

#: 设置损坏时给状态栏看的提示
BROKEN_MESSAGE = "设置损坏，已用默认值"


@dataclass
class LevelEntry:
    """一个内置层级的持久化状态。**存字符串，不存 `{active, regex}` 对象。**

    那个对象写法制造了一个自相矛盾的状态（`active: false` 但 `regex: "^第.+"` 该听
    谁的）。三层语义其实只有一个维度 —— 「这条层级最终用什么正则」：

    * `None`：用户没动过 → 永远跟随 core 缺省
    * `""`：显式关闭该层级
    * 非空：显式设了这条正则
    """

    pattern: str | None = None


@dataclass
class Settings:
    """会被记住的东西。当次字段（输入/输出路径、书名作者等）一律不存。"""

    version: int = VERSION
    window: dict[str, int] = field(default_factory=lambda: {"w": 1200, "h": 800})
    overwrite: bool = True
    clean: bool = True
    language: str = ""
    text_cover: bool = True
    levels: dict[str, LevelEntry] = field(default_factory=dict)
    level: list[str] = field(default_factory=list)
    max_title_len: int = 35
    preface_title: str = ""
    indent: int = 2
    line_height: str = ""
    para_spacing: str = ""
    volume_align: str = ""
    chapter_align: str = ""
    css_mode: str = ""
    css_path: str = ""
    font: str = ""
    toc_depth: int = 6
    toc_in_spine: bool = True
    replacements: list[dict] = field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps(_encode(self), ensure_ascii=False, indent=2)

    @classmethod
    def from_dict(cls, data: Any) -> tuple["Settings", bool]:
        """读回设置。返回 `(设置, 是否损坏)`。

        字段逐个取、类型不对就用缺省 —— 一个坏字段不该让整份设置作废。
        """
        if not isinstance(data, dict):
            return cls(), True

        known = {f for f in cls.__dataclass_fields__}
        merged: dict[str, Any] = {k: v for k, v in data.items() if k in known}
        damaged = any(v is not None and not _type_ok(k, v) for k, v in merged.items())

        settings = cls()
        for name in known - {"version"}:
            if name not in merged:
                continue
            value = merged[name]
            if not _type_ok(name, value):
                damaged = True
                continue
            setattr(settings, name, _coerce(name, value))
        if data.get("version") != VERSION:
            # 版本对不上：只当没这份设置，不用旧结构猜
            return cls(), True
        return settings, damaged

    @classmethod
    def load(cls) -> tuple["Settings", bool]:
        """从磁盘读设置。文件不存在不算损坏；读不了或解不开算损坏（用缺省启动）。"""
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
        """写回磁盘，返回写到的路径。写不了返回 `None`（设置是可选功能，不该因此崩）。"""
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


#: 字段名 → 期望类型。用于逐字段校验，避免一个坏字段毁掉整份设置
_TYPES: dict[str, type | tuple[type, ...]] = {
    "version": int,
    "window": dict,
    "overwrite": bool,
    "clean": bool,
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


def _type_ok(name: str, value: Any) -> bool:
    kind = _TYPES.get(name)
    if kind is None:
        return False
    # bool 是 int 的子类，`True` 混进 int 字段要当成损坏
    if kind is int and isinstance(value, bool):
        return False
    return isinstance(value, kind)


def _coerce(name: str, value: Any) -> Any:
    """把 JSON 里的值转成字段该有的形态；`levels` / `replacements` 单独处理。"""
    if name == "levels":
        return {
            key: LevelEntry(val if isinstance(val, str) else None)
            for key, val in value.items()
        }
    return value


def _encode(settings: Settings) -> dict[str, Any]:
    data = asdict(settings)
    data["levels"] = {k: v["pattern"] for k, v in data["levels"].items()}
    return data
