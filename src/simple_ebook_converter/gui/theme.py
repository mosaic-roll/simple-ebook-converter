"""主题：使用 sv_ttk 提供现代外观。

sv_ttk 是 ttk 的扩展主题引擎，提供扁平化、现代化的控件外观。
本模块只安装主题和全局字体，具体控件样式全交给 sv_ttk，
不再手写 `TButton`/`TLabel` 之类的一堆配置。
"""

from __future__ import annotations

import tkinter as tk
import tkinter.ttk as ttk

import sv_ttk

from .fonts import UI_SIZE, font

#: sv_ttk 的亮色主题名。`sv_ttk.set_theme()` 实际就是把 `theme_use()` 切成它。
THEME = "sun-valley-light"


def apply(root: tk.Misc) -> ttk.Style:
    """安装 sv_ttk 主题并设置全局字体，返回配置好的 `Style`。"""
    sv_ttk.set_theme("light")
    style = ttk.Style(root)
    # 全局字体：sv_ttk 默认字号偏小，用 fonts 模块统一控制
    style.configure(".", font=font("ui", UI_SIZE))
    # 等宽控件（正则、CSS 编辑器）
    style.configure("Mono.TEntry", font=font("mono", UI_SIZE))
    style.configure("Mono.Treeview", font=font("mono", UI_SIZE))
    return style
