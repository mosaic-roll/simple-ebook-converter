"""ttk 控件的样式与配色。

只有目录表格用了 ttk（`ttk.Treeview` / `ttk.Scrollbar`），所以本模块目前只管它。
CTk 控件的配色由 `ctk.set_appearance_mode()` 管，不需要这里插手。
"""

from __future__ import annotations

from tkinter import font as tkfont
from tkinter import ttk

import customtkinter as ctk

from .constants import (
    TAG_DELETED,
    TAG_HTML,
    TAG_HTML_DELETED,
    THEME_DARK,
    THEME_LIGHT,
)

_STYLE_NAME = "Toc.Treeview"
_HEADING_STYLE = f"{_STYLE_NAME}.Heading"

# 目录表格行高 = 字体实际像素高 + 上下留白。ttk 的 rowheight 只认像素，而字号是 pt，
# 两者不能直接相加；量字体实际高度才能对上（见 apply_toc_font）。
ROW_EXTRA = 8
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
    toc_table.tag_configure(TAG_HTML, foreground=palette["html_fg"])
    # 删除线由 apply_toc_font() 挂，这里只管字色
    toc_table.tag_configure(TAG_DELETED, foreground=palette["del_fg"])
    # 「既删除又命中 html」单独一个 tag：删除优先，灰字 + 删除线，蓝色等恢复后才回来。
    # 单独一个 tag 就不用赌 Tk 里多个 tag 哪个的前景色生效
    toc_table.tag_configure(TAG_HTML_DELETED, foreground=palette["del_fg"])
    toc_table.update_idletasks()


def apply_toc_font(toc_table: ttk.Treeview, family: str, size: int) -> None:
    """把界面字体族名/字号套到目录表格上（设置窗应用、主题切换时调用）。

    行高量字体的实际像素高，不拿 pt 直接加常数：`rowheight` 只认像素，字号却是 pt，
    两者相加在 150% 缩放下会明显偏小（pt→px 的换算 Tk 自己按 `tk scaling` 做）。
    """
    linespace = tkfont.Font(family=family, size=size).metrics("linespace")
    style = ttk.Style()
    style.configure(
        _STYLE_NAME,
        font=(family, size),
        rowheight=max(linespace + ROW_EXTRA, ROW_MIN),
    )
    style.configure(_HEADING_STYLE, font=(family, size))
    toc_table.tag_configure(TAG_DELETED, font=(family, size, "overstrike"))
    toc_table.tag_configure(TAG_HTML_DELETED, font=(family, size, "overstrike"))
