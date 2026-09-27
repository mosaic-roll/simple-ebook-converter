"""主题：使用 sv_ttk 提供现代外观。

sv_ttk 是 ttk 的扩展主题引擎，提供扁平化、现代化的控件外观。
本模块只安装主题，样式全交给 sv_ttk 处理。
"""

from __future__ import annotations

import tkinter as tk

import sv_ttk
import tkinter.ttk as ttk

from .fonts import UI_SIZE, font


def apply(root: tk.Misc) -> None:
    """安装 sv_ttk 主题并设置全局字体。"""
    sv_ttk.set_theme("light")
    style = ttk.Style(root)
    # 全局字体：sv_ttk 默认字号偏小，用 fonts 模块统一控制
    style.configure(".", font=font("ui", UI_SIZE))
    # 等宽控件（正则、CSS 编辑器）
    style.configure("Mono.TEntry", font=font("mono", UI_SIZE))
    style.configure("Mono.Treeview", font=font("mono", UI_SIZE))
