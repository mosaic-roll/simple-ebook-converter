"""基础 Tab：文件、书籍信息、封面、其他。"""

from __future__ import annotations

import tkinter as tk

import customtkinter as ctk

from ..constants import (
    CHECK_PADX,
    CHECK_PADY_LAST,
    CHECK_PADY_MID,
    ENCODING_LABELS,
    LANGUAGES,
)
from ..context import GuiContext
from ..defaults import default_text
from ..widgets import (
    make_field,
    make_field_btn,
    make_field_combo,
    make_field_menu,
    make_group,
)


def _bool_default(name: str, ctx: GuiContext) -> bool:
    """勾选项初值：存档里有就用存档，否则 core 的默认值。

    勾选项的值就是布尔本身（不是字符串），所以不走 `default_text()` 的字符串路子，
    但「真源在 core、存档优先」这条规矩一样。
    """
    if name in ctx.saved:
        return bool(ctx.saved[name])
    return default_text(name) == "True"


def build(parent: ctk.CTkFrame, ctx: GuiContext) -> dict:
    """构建基础 Tab，返回控件引用。"""
    parent.grid_columnconfigure(0, weight=1)

    f = make_group(parent, "文件", 0, ctx)
    input_entry = make_field_btn(f, 1, "源文件", ctx, command=ctx.cb("pick_input"))
    output_entry = make_field_btn(f, 2, "目标", ctx, command=ctx.cb("pick_output"))
    # 菜单存中文，收集时用 ENCODING_LABELS 换回 codec 名（core 只认 codec 名）
    encoding_menu = make_field_menu(f, 3, "编码", list(ENCODING_LABELS), ctx)

    m = make_group(parent, "书籍信息", 1, ctx)
    # 书名/作者各占满一整行（span=3 铺到分组右边缘）：这两项最常填长文本，
    # 挤在半宽的框里既难读也难看清
    book_title = make_field(m, 1, "书名", ctx, "书名", col=0, span=3)
    book_author = make_field(m, 2, "作者", ctx, "作者", col=0, span=3)
    # core 的 `DEFAULTS.date` 是 None（不写就省掉 dc:date），所以这里给的是**格式提示**，
    # 不是默认值：留空即「不写」
    book_date = make_field(m, 3, "出版日期", ctx, "如 1949-10-01", col=0)
    lang_menu = make_field_combo(m, 3, "语言", LANGUAGES, ctx, col=2)

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
    # 初值走 core 的 DEFAULTS（有存档用存档），不手抄字面量
    text_cover_var = tk.BooleanVar(master=c, value=_bool_default("text_cover", ctx))
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
    clean_var = tk.BooleanVar(master=o, value=_bool_default("clean", ctx))
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

    toc_in_book_var = tk.BooleanVar(master=o, value=_bool_default("toc_in_spine", ctx))
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
