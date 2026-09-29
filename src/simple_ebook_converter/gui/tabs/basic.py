"""基础 Tab：文件、书籍信息、封面、其他。"""

from __future__ import annotations

import tkinter as tk

import customtkinter as ctk

from ..constants import (
    CHECK_PADX,
    CHECK_PADY_LAST,
    CHECK_PADY_MID,
    ENCODINGS,
    LANGUAGES,
)
from ..context import GuiContext
from ..widgets import (
    make_field,
    make_field_btn,
    make_field_combo,
    make_field_menu,
    make_group,
)


def build(parent: ctk.CTkFrame, ctx: GuiContext) -> dict:
    """构建基础 Tab，返回控件引用。"""
    parent.grid_columnconfigure(0, weight=1)

    f = make_group(parent, "文件", 0, ctx)
    input_entry = make_field_btn(f, 1, "源文件", ctx, command=ctx.cb("pick_input"))
    output_entry = make_field_btn(f, 2, "目标", ctx, command=ctx.cb("pick_output"))
    encoding_menu = make_field_menu(f, 3, "编码", ENCODINGS, ctx)

    m = make_group(parent, "书籍信息", 1, ctx)
    book_title = make_field(m, 1, "书名", ctx, "书名", col=0)
    book_author = make_field(m, 1, "作者", ctx, "作者", col=2)
    book_date = make_field(m, 2, "日期", ctx, "2024-05-13", col=0)
    lang_menu = make_field_combo(m, 2, "语言", LANGUAGES, ctx, col=2)

    c = make_group(parent, "封面", 2, ctx)
    cover_entry = make_field_btn(
        c,
        1,
        "路径",
        ctx,
        command=ctx.cb("pick_cover"),
        placeholder="封面图片（.jpg / .png / .webp）",
        extra_btns=[("查看", ctx.cb("open_cover"))],
    )
    # TODO: 接 core 后初值取 core.config.DEFAULTS["text_cover"]
    text_cover_var = tk.BooleanVar(master=c, value=True)
    ctk.CTkCheckBox(
        c,
        text="无封面时生成文字封面",
        variable=text_cover_var,
        font=ctx.fonts.base,
    ).grid(
        row=2,
        column=0,
        columnspan=4,
        padx=CHECK_PADX,
        pady=CHECK_PADY_LAST,
        sticky="w",
    )

    o = make_group(parent, "其他", 3, ctx)
    # TODO: 接 core 后初值取 core.config.DEFAULTS["clean"]
    clean_var = tk.BooleanVar(master=o, value=True)
    ctk.CTkCheckBox(
        o,
        text="清理段首空格及空行",
        variable=clean_var,
        font=ctx.fonts.base,
    ).grid(
        row=1,
        column=0,
        columnspan=4,
        padx=CHECK_PADX,
        pady=CHECK_PADY_MID,
        sticky="w",
    )

    # TODO: 接 core 后初值取 core.config.DEFAULTS["toc"]（--no-toc 取反）
    toc_in_book_var = tk.BooleanVar(master=o, value=True)
    ctk.CTkCheckBox(
        o,
        text="生成书内目录页",
        variable=toc_in_book_var,
        font=ctx.fonts.base,
    ).grid(
        row=2,
        column=0,
        columnspan=4,
        padx=CHECK_PADX,
        pady=CHECK_PADY_LAST,
        sticky="w",
    )

    return {
        "input_entry": input_entry,
        "output_entry": output_entry,
        "encoding_menu": encoding_menu,
        "book_title": book_title,
        "book_author": book_author,
        "book_date": book_date,
        "lang_menu": lang_menu,
        "cover_entry": cover_entry,
        "text_cover_var": text_cover_var,
        "clean_var": clean_var,
        "toc_in_book_var": toc_in_book_var,
    }
