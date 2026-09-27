"""主题：ttkbootstrap 的 `flatly`。

**样式交给 ttkbootstrap，本模块只做三件它不管的事**：

1. 把界面字体换成 `fonts` 探测到的族（ttkbootstrap 默认字号偏小、族也不受控）。
2. 给「等宽」控件一个 `Mono.*` style（正则是代码，不该用比例字体）。
3. 把主题色导出一个 `COLORS` 给极少数必须用原始颜色的地方（已划掉的灰字、
   校验提示文字）。**别处一律用 `bootstyle=`，不要手写颜色。**

不自己 `style.configure("TButton", …)`：那正是上一版「很多代码浪费在调样式上」的
由来。ttkbootstrap 的主题已经把这些定好了。
"""

from __future__ import annotations

import tkinter as tk

import ttkbootstrap as ttk

from .fonts import UI_SIZE, font

#: ttkbootstrap 主题名。`bootstrap-light` 是 2.x 的现代浅色主题，`flatly` 已被标记为
#: legacy（3.0 移除）—— 两者同源，用前者免得下一次升级主题名失效。
THEME = "bootstrap-light"

#: 主题色，`apply()` 时从 ttkbootstrap 填进来。别处不许出现字面量颜色。
COLORS: dict[str, str] = {}


def apply(root: tk.Misc) -> ttk.Style:
    """装主题，返回配好的 `Style`。

    前置条件由调用点保证（见 `__main__.py`）：`metrics.sync_scaling()` 与
    `fonts.bind_fonts()` 都已跑过 —— 本模块用 `font()` 定字体。
    """
    style = ttk.Style(theme=THEME)
    colors = style.colors
    COLORS.update(
        {
            "fg": colors.fg,
            "bg": colors.bg,
            "muted": colors.secondary,
            "line": colors.border,
            "accent": colors.primary,
            "accent_fg": colors.selectfg,
            "error": colors.danger,
            "warn": colors.warning,
            "del": colors.secondary,
            "sel": colors.selectbg,
        }
    )
    root.configure(background=colors.bg)

    # 全局字体：ttkbootstrap 的主题字体不受 fonts 控制，这里统一盖掉
    style.configure(".", font=font("ui", UI_SIZE))
    # 等宽：正则框、CSS 文本框、替换表格
    style.configure("Mono.TEntry", font=font("mono", UI_SIZE))
    style.configure("Mono.Treeview", font=font("mono", UI_SIZE))
    return style
