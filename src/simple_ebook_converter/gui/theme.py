"""ttk 控件的样式与配色。

只有目录表格用了 ttk（`ttk.Treeview` / `ttk.Scrollbar`），所以本模块目前只管它。
CTk 控件的配色由 `ctk.set_appearance_mode()` 管，不需要这里插手。
"""

from __future__ import annotations

from tkinter import ttk

import customtkinter as ctk

from .constants import THEME_DARK, THEME_LIGHT

_STYLE_NAME = "Toc.Treeview"
_HEADING_STYLE = f"{_STYLE_NAME}.Heading"
_TAG_DELETED = "deleted"
_TAG_HTML = "html"

# 目录表格行高派生：ttk 的 rowheight 是像素，不随字号线性缩放，给个下限兜底
ROW_EXTRA = 16
ROW_MIN = 24


def current_palette() -> dict[str, str]:
    """当前外观模式对应的调色板。"""
    dark = ctk.get_appearance_mode() == "Dark"
    return THEME_DARK if dark else THEME_LIGHT


def apply_toc_theme(toc_table: ttk.Treeview) -> None:
    """按当前外观模式给目录表格上色（浅色/深色切换时调用）。"""
    palette = current_palette()
    style = ttk.Style()
    style.theme_use("clam")

    style.configure(
        _STYLE_NAME,
        background=palette["bg"],
        foreground=palette["fg"],
        fieldbackground=palette["field"],
    )
    style.map(
        _STYLE_NAME,
        background=[("selected", palette["sel_bg"])],
        foreground=[("selected", palette["sel_fg"])],
    )
    style.configure(
        _HEADING_STYLE,
        background=palette["head_bg"],
        foreground=palette["head_fg"],
    )
    style.map(
        _HEADING_STYLE,
        background=[("!active", palette["head_bg"]), ("active", palette["head_bg"])],
        foreground=[("!active", palette["head_fg"]), ("active", palette["head_fg"])],
    )
    # html 阶段命中过的标题：整行染蓝（tag 是 item 级的，所有列一起）
    toc_table.tag_configure(_TAG_HTML, foreground=palette["html_fg"])
    # 删除线在后配置：一条标题既被删除又被 html 规则命中时，灰字删除线优先于蓝色
    toc_table.tag_configure(_TAG_DELETED, foreground=palette["del_fg"])
    toc_table.update_idletasks()


def apply_toc_font(toc_table: ttk.Treeview, family: str, size: int) -> None:
    """把界面字体族名/字号套到目录表格上（设置窗应用、主题切换时调用）。"""
    style = ttk.Style()
    style.configure(
        _STYLE_NAME,
        font=(family, size),
        rowheight=max(size + ROW_EXTRA, ROW_MIN),
    )
    style.configure(_HEADING_STYLE, font=(family, size))
    toc_table.tag_configure(_TAG_DELETED, font=(family, size, "overstrike"))
