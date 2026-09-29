"""排版 Tab：段落、对齐、嵌入字体、自定义 CSS。"""

from __future__ import annotations

import customtkinter as ctk

from ..constants import ALIGNS, CHECK_PADX, CHECK_PADY_LAST, SEG_PADY
from ..context import GuiContext
from ..widgets import make_field, make_field_btn, make_field_menu, make_group

#: CSS 模式取值 → core 侧对应项：`--css-append` / `--css-file`
CSS_MODES = ["忽略", "追加", "覆盖"]


def build(parent: ctk.CTkFrame, ctx: GuiContext) -> dict:
    """构建排版 Tab，返回控件引用。"""
    parent.grid_columnconfigure(0, weight=1)

    p = make_group(parent, "段落", 0, ctx)
    indent = make_field(p, 1, "缩进", ctx, "2", col=0)
    line_height = make_field(p, 1, "行高", ctx, "1.5", col=2)
    para_spacing = make_field(p, 2, "段间距", ctx, "1em", col=0)
    margin = make_field(p, 2, "页边距", ctx, "20", col=2)

    al = make_group(parent, "对齐方式", 1, ctx)
    align_volume = make_field_menu(al, 1, "卷", ALIGNS, ctx, default="center", col=0)
    align_chapter = make_field_menu(al, 1, "章", ALIGNS, ctx, default="center", col=2)
    align_section = make_field_menu(al, 2, "节", ALIGNS, ctx, default="left", col=0)
    align_body = make_field_menu(al, 2, "正文", ALIGNS, ctx, default="left", col=2)

    fo = make_group(parent, "嵌入字体", 2, ctx)
    font_entry = make_field_btn(fo, 1, "路径", ctx, command=ctx.cb("pick_font"))

    css = make_group(parent, "自定义 CSS", 3, ctx)
    css.grid_configure(sticky="nsew", pady=(8, 0))
    css.grid_columnconfigure(0, weight=1)
    css.grid_rowconfigure(2, weight=1)

    css_mode = ctk.CTkSegmentedButton(css, values=CSS_MODES)
    css_mode.set(CSS_MODES[0])
    css_mode.grid(
        row=1, column=0, columnspan=4, padx=CHECK_PADX, pady=SEG_PADY, sticky="w"
    )

    css_text = ctk.CTkTextbox(css, font=ctx.fonts.base)
    css_text.grid(
        row=2,
        column=0,
        columnspan=4,
        padx=CHECK_PADX,
        pady=CHECK_PADY_LAST,
        sticky="nsew",
    )

    parent.grid_rowconfigure(3, weight=1)

    return {
        "indent": indent,
        "line_height": line_height,
        "para_spacing": para_spacing,
        "margin": margin,
        "align_volume": align_volume,
        "align_chapter": align_chapter,
        "align_section": align_section,
        "align_body": align_body,
        "font_entry": font_entry,
        "css_mode": css_mode,
        "css_text": css_text,
    }
