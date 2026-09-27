"""主题：使用 sv_ttk 提供现代外观。

sv_ttk 是 ttk 的扩展主题引擎，提供扁平化、现代化的控件外观，
无需手写大量样式配置。本模块只做字体定制和校验态样式。
"""

from __future__ import annotations

import tkinter as tk

import sv_ttk
import tkinter.ttk as ttk

from .fonts import UI_SIZE, font

#: 默认主题（light）
DEFAULT_THEME = "light"

#: 校验态 style 名
_ERROR_STYLE = "Error.TEntry"
_WARN_STYLE = "Warn.TEntry"


def apply(root: tk.Misc) -> ttk.Style:
    """安装 sv_ttk 主题并配置校验态样式。

    sv_ttk 自动处理大部分样式，这里只设置全局字体和校验边框颜色。
    """
    sv_ttk.set_theme(DEFAULT_THEME)
    style = ttk.Style(root)
    # 全局字体：sv_ttk 默认字号偏小，用 fonts 模块统一控制
    style.configure(".", font=font("ui", UI_SIZE))
    # 等宽控件（正则、CSS 编辑器）
    style.configure("Mono.TEntry", font=font("mono", UI_SIZE))
    style.configure("Mono.Treeview", font=font("mono", UI_SIZE))
    # 校验态：红/黄框
    style.configure(_ERROR_STYLE, bordercolor="#c62828", lightcolor="#c62828", darkcolor="#c62828")
    style.map(_ERROR_STYLE, bordercolor=[("focus", "#c62828")])
    style.configure(_WARN_STYLE, bordercolor="#b26a00", lightcolor="#b26a00", darkcolor="#b26a00")
    style.map(_WARN_STYLE, bordercolor=[("focus", "#b26a00")])
    return style
