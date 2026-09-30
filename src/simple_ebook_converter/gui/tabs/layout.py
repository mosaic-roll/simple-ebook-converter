"""排版 Tab：段落、对齐、嵌入字体、自定义 CSS。

自定义 CSS 有两种来源：「直接编辑」在文本框里写，可选忽略/追加/覆盖内置样式；
「使用文件」只填路径，该文件整体覆盖内置 CSS（对应 core 的 `--css-file`），
此时模式与文本框禁用但内容保留。
"""

from __future__ import annotations

import tkinter as tk

import customtkinter as ctk

from ..constants import (
    ALIGN_LABELS,
    BTN_W_L,
    CHECK_PADX,
    CHECK_PADY_LAST,
    SEG_PADY,
)
from ..context import GuiContext
from ..widgets import make_field, make_field_btn, make_field_menu, make_group

#: CSS 模式取值 → core 侧对应项：追加=`--css-append`，覆盖=`--css-file`
CSS_MODES = ["忽略", "追加", "覆盖"]

#: CSS 来源取值：文本框直接写 / 从文件读。文件来源等同 core 的 `--css-file`
CSS_SOURCE_TEXT = "text"
CSS_SOURCE_FILE = "file"


def build(parent: ctk.CTkFrame, ctx: GuiContext) -> dict:
    """构建排版 Tab，返回控件引用。"""
    parent.grid_columnconfigure(0, weight=1)
    font = ctx.fonts.base

    # ---- 段落 ----
    p = make_group(parent, "段落", 0, ctx)
    indent = make_field(p, 1, "缩进", ctx, "2", col=0)
    line_height = make_field(p, 1, "行高", ctx, "1.5", col=2)
    para_spacing = make_field(p, 2, "段间距", ctx, "1em", col=0)
    margin = make_field(p, 2, "页边距", ctx, "20", col=2)

    # ---- 对齐方式 ----
    # 菜单存的是中文，收集时用 ALIGN_LABELS 换回 core 取值
    al = make_group(parent, "对齐方式", 1, ctx)
    align_volume = make_field_menu(
        al, 1, "卷", list(ALIGN_LABELS), ctx, default="居中", col=0
    )
    align_chapter = make_field_menu(
        al, 1, "章", list(ALIGN_LABELS), ctx, default="居中", col=2
    )
    align_body = make_field_menu(
        al, 2, "正文", list(ALIGN_LABELS), ctx, default="两端对齐", col=2
    )

    # ---- 嵌入字体 ----
    fo = make_group(parent, "嵌入字体", 2, ctx)
    font_entry = make_field_btn(
        fo,
        1,
        "路径",
        ctx,
        command=ctx.cb("pick_font"),
        placeholder="字体文件（.ttf / .otf / .woff）",
    )

    # ---- 自定义 CSS ----
    css = make_group(parent, "自定义 CSS", 3, ctx)
    css.grid_configure(sticky="nsew", pady=(8, 0))
    css.grid_rowconfigure(4, weight=1)

    # row=1：来源单选框，两个选项直接并排
    source_var = tk.StringVar(master=css, value=CSS_SOURCE_TEXT)
    src_row = ctk.CTkFrame(css, fg_color="transparent")
    src_row.grid(
        row=1,
        column=0,
        columnspan=4,
        sticky="w",
        padx=CHECK_PADX,
        pady=(4, 2),
    )
    ctk.CTkRadioButton(
        src_row,
        text="直接编辑",
        variable=source_var,
        value=CSS_SOURCE_TEXT,
        font=font,
        command=lambda: _on_source_change(),
    ).pack(side="left", padx=(0, 16))
    ctk.CTkRadioButton(
        src_row,
        text="使用文件",
        variable=source_var,
        value=CSS_SOURCE_FILE,
        font=font,
        command=lambda: _on_source_change(),
    ).pack(side="left")

    # row=2：路径行，走 make_field_btn，和嵌入字体/封面对齐
    css_path = make_field_btn(
        css,
        2,
        "路径",
        ctx,
        command=ctx.cb("pick_css"),
        placeholder="CSS 文件路径（整体覆盖内置样式）",
        extra_btns=[("清空", ctx.cb("clear_css"))],
    )

    # row=3：模式 + 加载内置样式
    mode_row = ctk.CTkFrame(css, fg_color="transparent")
    mode_row.grid(
        row=3, column=0, columnspan=4, sticky="ew", padx=CHECK_PADX, pady=SEG_PADY
    )
    mode_row.grid_columnconfigure(0, weight=1)

    css_mode = ctk.CTkSegmentedButton(mode_row, values=CSS_MODES)
    css_mode.set(CSS_MODES[0])
    css_mode.grid(row=0, column=0, sticky="w")

    load_builtin_btn = ctk.CTkButton(
        mode_row,
        text="加载内置样式",
        width=BTN_W_L,
        font=font,
        command=ctx.cb("load_builtin_css"),
    )
    load_builtin_btn.grid(row=0, column=1, sticky="e")

    # row=4：文本框
    css_text = ctk.CTkTextbox(css, font=font)
    css_text.grid(
        row=4,
        column=0,
        columnspan=4,
        padx=CHECK_PADX,
        pady=CHECK_PADY_LAST,
        sticky="nsew",
    )

    # ---- 来源切换 ----
    def _on_source_change() -> None:
        # 路径框两种来源下都能编辑，不跟着切 state
        if source_var.get() == CSS_SOURCE_FILE:
            # 使用文件：只有路径生效，模式与文本框禁用（内容保留）
            css_mode.configure(state="disabled")
            css_text.configure(state="disabled")
            load_builtin_btn.configure(state="disabled")
        else:
            # 直接编辑：模式 + 文本框生效
            css_mode.configure(state="normal")
            css_text.configure(state="normal")
            load_builtin_btn.configure(state="normal")

    _on_source_change()
    parent.grid_rowconfigure(3, weight=1)

    # TODO: 接 core 后收集配置要以 css_source 为准 —— 文件模式只用 css_path（覆盖
    # 内置 CSS），文本模式才看 css_mode + css_text。禁用只是不让改，值都还留着。
    return {
        "indent": indent,
        "line_height": line_height,
        "para_spacing": para_spacing,
        "margin": margin,
        "align_volume": align_volume,
        "align_chapter": align_chapter,
        "align_body": align_body,
        "font_entry": font_entry,
        "css_source": source_var,
        "css_mode": css_mode,
        "css_path": css_path,
        "css_text": css_text,
    }
