"""主题与基础样式。**必须在建任何控件之前调 `apply()`。**

选 `clam` 是因为它是**唯一**支持 `bordercolor` / `lightcolor` / `darkcolor` 定制的
内置 ttk 主题 —— 路径校验的红框/黄框就靠它（§4.2）。`vista` 上 `bordercolor` 会被
**静默忽略**，所以 `apply()` 之后必须探一次 `border_color_supported()`。

不做深色模式切换按钮，但所有颜色集中在这里，日后要加只改这一处。
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from .fonts import UI_SIZE, font
from .metrics import s

#: 唯一支持边框定制的内置主题
THEME = "clam"

#: 设计稿里的所有颜色集中在这里。别处不许出现字面量颜色。
COLORS = {
    "fg": "#1c1c1c",
    "bg": "#ffffff",
    "muted": "#6b6b6b",
    "line": "#d0d0d0",
    "accent": "#1a6fd4",
    "accent_fg": "#ffffff",
    "error": "#c62828",
    "warn": "#b26a00",
    "del": "#9a9a9a",
    "tip_bg": "#ffffe0",
    "sel": "#d8e8fb",
}

#: 校验态：error / warn → 对应的 style 名与颜色
_ERROR_STYLE = "Error.TEntry"
_WARN_STYLE = "Warn.TEntry"


def apply(root: tk.Misc) -> ttk.Style:
    """装主题 + 铺基础样式，返回配好的 `Style`。

    一个前置条件由调用点保证（见 `__main__.py`）：`metrics.sync_scaling()` 已跑过 ——
    本函数用 `s()` 定死尺寸和字号。字体不依赖它（见 `fonts` 模块的说明）。
    """
    style = ttk.Style(root)
    style.theme_use(THEME)
    root.configure(background=COLORS["bg"])

    ui_font = font("ui", UI_SIZE)
    style.configure(".", font=ui_font, background=COLORS["bg"], foreground=COLORS["fg"])
    style.configure("TFrame", background=COLORS["bg"])
    style.configure("TLabel", background=COLORS["bg"], foreground=COLORS["fg"])
    style.configure("TButton", padding=(s(8), s(4)))
    style.configure("TCheckbutton", background=COLORS["bg"], foreground=COLORS["fg"])
    style.configure("TRadiobutton", background=COLORS["bg"], foreground=COLORS["fg"])
    style.configure("TLabelframe", background=COLORS["bg"], bordercolor=COLORS["line"])
    style.configure("TLabelframe.Label", background=COLORS["bg"], foreground=COLORS["fg"])
    style.configure("TNotebook", bordercolor=COLORS["line"])
    style.configure("TNotebook.Tab", padding=(s(10), s(4)))

    # 强调按钮（clam 上背景色可配）
    style.configure("Accent.TButton", background=COLORS["accent"], foreground=COLORS["accent_fg"])
    style.map(
        "Accent.TButton",
        background=[("active", COLORS["accent"]), ("disabled", COLORS["line"])],
        foreground=[("disabled", COLORS["bg"])],
    )

    # 提示文字 / 危险文字
    style.configure("Muted.TLabel", foreground=COLORS["muted"])
    style.configure("Danger.TButton", foreground=COLORS["error"])

    # 目录表格：独立 style 名，行高才不会波及所有 Treeview
    style.configure("Toc.Treeview", background=COLORS["bg"], fieldbackground=COLORS["bg"])
    style.configure("Toc.Treeview.Heading", font=font("ui", UI_SIZE, "bold"))
    style.map("Toc.Treeview", background=[("selected", COLORS["sel"])])

    _configure_entry_state(style, _ERROR_STYLE, COLORS["error"])
    _configure_entry_state(style, _WARN_STYLE, COLORS["warn"])

    # 等宽字体：正则框、CSS 文本框用
    style.configure("Mono.TEntry", font=font("mono", UI_SIZE))
    style.configure("Mono.Treeview", font=font("mono", UI_SIZE))
    return style


def _configure_entry_state(style: ttk.Style, name: str, color: str) -> None:
    """配一个校验态 Entry 样式。

    `configure` 给默认值、`map` 把每个状态都钉死：只写 `configure` 的话，控件获得
    焦点时 ttk 会用 focus 态重新查一次样式，红框会闪掉。

    `lightcolor` / `darkcolor` 一起配：clam 在某些平台用它们画 3D 边框，只配
    `bordercolor` 会看到「红边框 + 黑边」的双色。
    """
    style.configure(name, bordercolor=color, lightcolor=color, darkcolor=color)
    style.map(
        name,
        bordercolor=[("focus", color)],
        lightcolor=[("focus", color)],
        darkcolor=[("focus", color)],
    )


def border_color_supported(root: tk.Misc) -> bool:
    """当前主题认不认 `bordercolor`（决定路径校验能不能靠红框表达）。

    `bordercolor` 是 **element option**，不是 widget option —— 所以
    `widget.cget("bordercolor")` 探测不到任何东西、恒为假。正确做法是让 `Style`
    替我们查它自己配过的东西。
    """
    style = ttk.Style(root)
    if style.theme_use() != THEME:
        return False
    value = style.lookup(_ERROR_STYLE, "bordercolor")
    return bool(value) and str(value) not in ("", "unknown")
