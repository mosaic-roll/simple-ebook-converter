"""主题：sv_ttk 外观 + 随亮/暗切换的语义色。

## 职责

* 安装 sv_ttk 主题、把 sv_ttk 自带的**固定像素字体**换成会随 DPI 缩放的磅值；
* 提供一套语义色（`fg`/`bg`/`muted`/`error`/`warn`），亮暗各一份。

**纯控件样式交给 sv_ttk，本模块不写 `TButton`/`TLabel` 那一堆配置。** 只有
sv_ttk 没提供的语义色（错误红、警告橙、已删灰）才在这里定义。

## 换色怎么传播

`sv_ttk.set_theme()` 会切 `theme_use()`，Tk 随即给每个控件发 `<<ThemeChanged>>`。
控件构造时调 `on_colors_changed()`，把「重取当前色」的回调挂上去；切主题时回调
重跑，颜色跟着换。控件自己不去读 `sv_ttk.get_theme()`（那需要 root），只读本模块
的 `colors()` —— 模式由 `apply()` / `set_mode()` 维护在这里。
"""

from __future__ import annotations

import tkinter as tk
import tkinter.font as tkfont
import tkinter.ttk as ttk
from collections.abc import Callable

import sv_ttk

from .fonts import TITLE_SIZE, UI_SIZE, actual_family, font

#: 支持的 sv_ttk 主题
LIGHT = "light"
DARK = "dark"
MODES = (LIGHT, DARK)

#: 亮/暗两套语义色。`fg`/`bg`/`muted` 取自 sv_ttk 自带调色板（见
#: `sv_ttk/theme/{light,dark}.tcl` 的 `colors` 数组），`error`/`warn` 是 sv_ttk
#: 没提供的，按两种底色各挑一套保证对比度。
_PALETTES: dict[str, dict[str, str]] = {
    LIGHT: {
        "fg": "#1c1c1c",
        "bg": "#fafafa",
        "muted": "#a0a0a0",
        "error": "#c62828",
        "warn": "#b26a00",
    },
    DARK: {
        "fg": "#fafafa",
        "bg": "#1c1c1c",
        "muted": "#8a8a8a",
        "error": "#ff6b6b",
        "warn": "#e0a458",
    },
}

#: sv_ttk 自建的具名字体 → 覆盖用的 `(磅值, 字重)`。sv_ttk 用负数字号（像素）且
#: 固定不变，高 DPI 下偏小，这里换成会随 `tk scaling` 缩放的磅值。
_SV_FONTS: dict[str, tuple[int, str]] = {
    "SunValleyBodyFont": (UI_SIZE, ""),
    "SunValleyBodyStrongFont": (UI_SIZE, "bold"),
    "SunValleyBodyLargeFont": (TITLE_SIZE, ""),
    # 表头（Treeview Heading）与分组框标题都用它；原先比正文还小，调到和正文一致
    "SunValleyCaptionFont": (UI_SIZE, ""),
}

#: 当前模式。由 `apply()` / `set_mode()` 维护，`colors()` 据此取色。
_MODE = LIGHT


def apply(root: tk.Misc, mode: str = LIGHT) -> ttk.Style:
    """安装 sv_ttk 主题、覆盖字体，返回配置好的 `Style`。"""
    set_mode(mode, root)
    _override_fonts(root)
    style = ttk.Style(root)
    # 全局默认字体：sv_ttk 没显式配字体的控件走这里
    style.configure(".", font=font("ui", UI_SIZE))
    # 等宽控件（正则、CSS 编辑器）
    style.configure("Mono.TEntry", font=font("mono", UI_SIZE))
    style.configure("Mono.Treeview", font=font("mono", UI_SIZE))
    return style


def mode() -> str:
    """当前主题模式：`LIGHT` 或 `DARK`。"""
    return _MODE


def colors() -> dict[str, str]:
    """当前主题的语义色表。控件取色都走这里，不要写死颜色字面量。"""
    return _PALETTES[_MODE]


def set_mode(mode: str, root: tk.Misc | None = None) -> None:
    """切到指定亮/暗模式。Tk 会向所有控件发 `<<ThemeChanged>>`，颜色随之刷新。"""
    global _MODE
    if mode not in MODES:
        raise ValueError(f"未知主题模式：{mode!r}")
    sv_ttk.set_theme(mode, root)
    _MODE = mode


def toggle(root: tk.Misc | None = None) -> str:
    """在亮/暗之间切换，返回切换后的模式。"""
    new = DARK if _MODE == LIGHT else LIGHT
    set_mode(new, root)
    return new


def on_colors_changed(widget: tk.Misc, callback: Callable[[], None]) -> None:
    """主题切换时重跑 `callback`，并**立即先跑一次**。

    这样控件构造时只需注册，不必再单独调一遍取色。`callback` 内部用 `colors()`
    取当前色。绑定的是 Tk 的 `<<ThemeChanged>>`：`sv_ttk.set_theme()` 换
    `theme_use()` 时 Tk 会给每个控件发这个虚拟事件。
    """
    widget.bind("<<ThemeChanged>>", lambda _event: callback(), add="+")
    callback()


def _override_fonts(root: tk.Misc) -> None:
    """把 sv_ttk 的具名字体换成会随 DPI 缩放的磅值。"""
    family = actual_family("ui")
    for name, (size, weight) in _SV_FONTS.items():
        try:
            named = tkfont.nametofont(name, root=root)
        except tk.TclError:
            continue  # 该主题没建这个字体（换版本时会遇到），跳过
        named.configure(family=family, size=size, weight=weight or "normal")
