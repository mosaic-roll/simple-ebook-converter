"""设置窗：界面字体族、界面字号、目录字号。

字体族与界面字号走 `FontManager`（CTk 字体实例，就地更新），目录字号是 ttk 的
字体，要另外调 `theme.apply_toc_font()`。

应用时通过 `on_apply` 回调统一写盘，避免设置窗本身依赖 app 层的 config 模块。
"""

from __future__ import annotations

from collections.abc import Callable
from tkinter import ttk

import customtkinter as ctk

from . import theme
from .constants import (
    BTN_GAP,
    BTN_W_L,
    DEFAULT_TOC_SIZE,
    DEFAULT_UI_SIZE,
    FONT_SIZES,
)
from .context import GuiContext
from .fonts import font_presets, label_to_size, size_to_label

# ---- 只有设置窗用 ----
PAD = 20
ROW_PADY = 10
LABEL_PADX = (0, 12)
FIELD_WIDTH = 160
CENTER_DELAY_MS = 20  # 等窗体算完真实尺寸再居中，太早拿到的是 1x1
BTN_ROW_PADY = (ROW_PADY, 0)

_CORNER_TRANSPARENT = "transparent"


def open(
    app: ctk.CTk,
    ctx: GuiContext,
    toc_table: ttk.Treeview,
    *,
    on_apply: Callable[[], None],
) -> None:
    """打开设置窗。`toc_table` 用于把新字号套到目录表格上；`on_apply` 在用户点
    「应用」时调用，负责同步 FontManager 与持久化配置。"""
    fonts = ctx.fonts
    win = ctk.CTkToplevel(app)
    win.attributes("-alpha", 0.0)  # ① 先透明，别让用户看到初始态
    win.title("设置")
    win.resizable(False, False)
    win.transient(app)
    win.grab_set()

    body = ctk.CTkFrame(win, fg_color=_CORNER_TRANSPARENT)
    body.pack(fill="both", expand=True, padx=PAD, pady=PAD)
    body.grid_columnconfigure(0, weight=0)  # 标签列：不拉伸
    body.grid_columnconfigure(1, weight=1)  # 控件列：吸收剩余宽度

    font_combo = ctk.CTkComboBox(
        body,
        values=list(font_presets().keys()),
        width=FIELD_WIDTH,
        font=fonts.base,
        dropdown_font=fonts.base,
    )
    font_combo.set(fonts.family_label)

    ui_menu = ctk.CTkOptionMenu(
        body,
        values=FONT_SIZES,
        width=FIELD_WIDTH,
        anchor="center",
        font=fonts.base,
        dropdown_font=fonts.base,
    )
    ui_menu.set(size_to_label(fonts.ui_size, DEFAULT_UI_SIZE))

    toc_menu = ctk.CTkOptionMenu(
        body,
        values=FONT_SIZES,
        width=FIELD_WIDTH,
        anchor="center",
        font=fonts.base,
        dropdown_font=fonts.base,
    )
    toc_menu.set(size_to_label(fonts.toc_size, DEFAULT_TOC_SIZE))

    add_row(body, 0, "字体", font_combo, ctx)
    add_row(body, 1, "界面字号", ui_menu, ctx)
    add_row(body, 2, "目录字号", toc_menu, ctx)

    def apply_and_close() -> None:
        fonts.set_family_label(font_combo.get())
        fonts.set_ui_size(label_to_size(ui_menu.get(), DEFAULT_UI_SIZE))
        fonts.set_toc_size(label_to_size(toc_menu.get(), DEFAULT_TOC_SIZE))
        theme.apply_toc_font(toc_table, fonts.family, fonts.toc_size)
        on_apply()
        win.destroy()

    btns = ctk.CTkFrame(body, fg_color=_CORNER_TRANSPARENT)
    btns.grid(row=3, column=0, columnspan=2, pady=BTN_ROW_PADY)
    ctk.CTkButton(
        btns, text="应用", width=BTN_W_L, font=ctx.fonts.base, command=apply_and_close
    ).pack(side="left", padx=BTN_GAP)
    ctk.CTkButton(
        btns, text="取消", width=BTN_W_L, font=ctx.fonts.base, command=win.destroy
    ).pack(side="left", padx=BTN_GAP)

    def center_and_show() -> None:
        app.update_idletasks()
        win.update_idletasks()
        px, py = app.winfo_rootx(), app.winfo_rooty()
        pw, ph = app.winfo_width(), app.winfo_height()
        ww, wh = win.winfo_width(), win.winfo_height()
        win.geometry(f"+{px + (pw - ww) // 2}+{py + (ph - wh) // 2}")
        win.attributes("-alpha", 1.0)  # ② 位置定好后再恢复可见

    app.after(CENTER_DELAY_MS, center_and_show)


def add_row(
    parent: ctk.CTkFrame, r: int, label: str, widget: ctk.CTkBaseClass, ctx: GuiContext
) -> None:
    """一行：标签列固定宽，控件列吸收剩余宽度。"""
    ctk.CTkLabel(parent, text=label, anchor="w", font=ctx.fonts.base).grid(
        row=r, column=0, sticky="w", padx=LABEL_PADX, pady=(0, ROW_PADY)
    )
    widget.grid(row=r, column=1, sticky="ew", pady=(0, ROW_PADY))
