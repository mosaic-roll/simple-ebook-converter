"""基础 Tab：文件、书籍信息、封面、其他。"""

from __future__ import annotations

import tkinter as tk

import customtkinter as ctk

from ...core.options import option_label
from ..constants import (
    CHECK_PADX,
    CHECK_PADY_LAST,
    CHECK_PADY_MID,
    ENCODING_LABELS,
    GAP,
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
    # 书名/作者各占满一行（span=3），长文本在半宽框里放不下
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
    # 两个勾选框装在一个透明子框架里并排，**不能**直接塞进分组的 4 列 grid。
    #
    # 为什么：路径输入框那一行是 `column=1, columnspan=3, sticky="ew"`，也就是它要吃
    # 1/2/3 三列的宽度。而 grid 里某个控件的自然宽度只会加到它**自己那一列**上
    # （跨列的才分摊给有权重的列）。所以把「自动发现封面」放进第 2 列，第 2 列就被撑到
    # 7 个字宽，输入框跟着短一截、整体往右偏。
    #
    # 子框架自己跨 0-3 列、`sticky="ew"` 铺满整行，宽度和分组一致；内部用 `pack` 并排，
    # 起点就是这一行的左边，跟外层 grid 的排法对齐。跨列的宽度需求会分摊给有权重的列
    # （3、1），和原先那个单勾选框完全一样——实测分组最小宽 478、标签列 64，与旧布局
    # 一字不差，所以路径框既不变窄也不平移。子框架不设 width、不给背景，`grid` 出来的
    # 位置就是它唯一的作用。
    checks = ctk.CTkFrame(c, fg_color="transparent")
    checks.grid(
        row=2,
        column=0,
        columnspan=4,
        padx=CHECK_PADX,
        pady=CHECK_PADY_LAST,
        sticky="ew",
    )

    # 初值走 core 的 DEFAULTS（有存档用存档），不手抄字面量
    text_cover_var = tk.BooleanVar(
        master=checks, value=_bool_default("text_cover", ctx)
    )
    ctk.CTkCheckBox(
        checks,
        text="无封面时生成文字封面",
        variable=text_cover_var,
        font=ctx.fonts.base,
    ).pack(side="left")
    # 排在文字封面右边。两个开关各自独立、都默认开：文字封面管「没图时画不画一页」，
    # 自动发现管「去不去同目录找图」。标签取 core 选项表里的 `cover_discovery`，不手抄。
    cover_discovery_var = tk.BooleanVar(
        master=checks, value=_bool_default("cover_discovery", ctx)
    )
    ctk.CTkCheckBox(
        checks,
        text=option_label("cover_discovery"),
        variable=cover_discovery_var,
        font=ctx.fonts.base,
    ).pack(side="left", padx=(GAP, 0))

    o = make_group(parent, "其他", 3, ctx)
    # 同一行并排，直接占第 0/2 列——**不用**像封面组那样套透明子框架：这组里没有跨列的
    # 字段行，没有输入框的宽度要保护，两个勾选框的自然宽度落在哪列都无所谓。
    clean_var = tk.BooleanVar(master=o, value=_bool_default("clean", ctx))
    ctk.CTkCheckBox(
        o,
        text="清理段首空格及空行",
        variable=clean_var,
        font=ctx.fonts.base,
    ).grid(
        row=1,
        column=0,
        columnspan=2,
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
        row=1,
        column=2,
        columnspan=2,
        padx=CHECK_PADX,
        pady=CHECK_PADY_MID,
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
        "cover_discovery_var": cover_discovery_var,
        "clean_var": clean_var,
        "toc_in_book_var": toc_in_book_var,
    }
