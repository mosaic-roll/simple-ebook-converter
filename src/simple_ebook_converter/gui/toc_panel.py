"""右侧目录面板：目录树预览 + 编辑（改标题、删除线、深度、导入导出）。

目录树 JSON 是**扁平列表**（文档序），层级由 `level` 决定，没有 children 嵌套；
回喂时按 level 栈式挂树，与 `lines` 无关。
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from tkinter import ttk
from typing import Any

import customtkinter as ctk

from .constants import (
    BTN_GAP,
    BTN_W_M,
    BTN_W_XL,
    GAP,
    GROUP_PADX,
    OPTION_W_S,
    TOC_DEPTHS,
)
from .context import GuiContext
from .theme import apply_toc_font

# ---- 表格列（只有本面板用） ----
TREE_COL_WIDTH = 60
TITLE_WIDTH = 150
RESULT_WIDTH = 150
TABLE_HEIGHT = 16

_STYLE_NAME = "Toc.Treeview"
_TAG_DELETED = "deleted"
_TAG_HTML = "html"

_CORNER_RADIUS = 4
_PADX_LABEL = 12
_PADY_TITLE = (8, 4)
_PADY_TOOLBAR = (0, 4)
_PADY_BOTTOM = (0, 10)
_DEFAULT_DEPTH = TOC_DEPTHS[-1]


def build(parent: ctk.CTkFrame, ctx: GuiContext) -> dict:
    """构建目录面板，返回控件引用。"""
    font = ctx.fonts.base
    panel = ctk.CTkFrame(parent, corner_radius=_CORNER_RADIUS)
    panel.grid(row=0, column=1, sticky="nsew", padx=(GAP // 2, 0))
    panel.grid_rowconfigure(2, weight=1)
    panel.grid_columnconfigure(0, weight=1)

    ctk.CTkLabel(panel, text="目录", font=ctx.fonts.bold).grid(
        row=0, column=0, sticky="w", padx=_PADX_LABEL, pady=_PADY_TITLE
    )

    top = ctk.CTkFrame(panel, fg_color="transparent")
    top.grid(row=1, column=0, sticky="ew", padx=GROUP_PADX, pady=_PADY_TOOLBAR)
    top.grid_columnconfigure(0, weight=1)

    ctk.CTkButton(
        top,
        text="重新扫描",
        width=BTN_W_XL,
        font=font,
        command=ctx.cb("rescan_toc"),
    ).grid(row=0, column=0, sticky="w")

    right_top = ctk.CTkFrame(top, fg_color="transparent")
    right_top.grid(row=0, column=1, sticky="e")
    ctk.CTkButton(
        right_top,
        text="导入",
        width=BTN_W_M,
        font=font,
        command=ctx.cb("import_toc"),
    ).pack(side="left", padx=(0, BTN_GAP))
    ctk.CTkButton(
        right_top,
        text="导出",
        width=BTN_W_M,
        font=font,
        command=ctx.cb("export_toc"),
    ).pack(side="left")

    table = _make_table(panel)

    populate_toc(table, _TEST_ENTRIES)
    apply_toc_font(table, ctx.fonts.family, ctx.fonts.toc_size)

    bottom = ctk.CTkFrame(panel, fg_color="transparent")
    bottom.grid(row=3, column=0, sticky="ew", padx=GROUP_PADX, pady=_PADY_BOTTOM)
    bottom.grid_columnconfigure(0, weight=1)

    depth_menu = ctk.CTkOptionMenu(
        _label_row(bottom, "目录深度", font),
        values=TOC_DEPTHS,
        width=OPTION_W_S,
        anchor="center",
        font=font,
        dropdown_font=font,
    )
    depth_menu.set(_DEFAULT_DEPTH)
    depth_menu.pack(side="left", padx=(6, 0))

    right = ctk.CTkFrame(bottom, fg_color="transparent")
    right.grid(row=0, column=1, sticky="e")
    ctk.CTkButton(
        right,
        text="删除",
        width=BTN_W_M,
        font=font,
        command=lambda: set_deleted(table, True),
    ).pack(side="left", padx=(0, BTN_GAP))
    ctk.CTkButton(
        right,
        text="恢复",
        width=BTN_W_M,
        font=font,
        command=lambda: set_deleted(table, False),
    ).pack(side="left")

    return {
        "panel": panel,
        "table": table,
        "depth_menu": depth_menu,
    }


def set_deleted(table: ttk.Treeview, deleted: bool) -> None:
    """给选中条目加/去删除线标记。

    删除**不是**从列表里移除：原标题要留着显示删除线，组装时正文自动并入上文、
    子章节自动合并（见 CLI 设计「目录树 JSON 与 --toc-file」的编辑语义）。
    """
    tags = (_TAG_DELETED,) if deleted else ()
    for item_id in table.selection():
        table.item(item_id, tags=tags)


def entries_from_preview(results: Iterable[Any]) -> list[dict[str, Any]]:
    """`core.pipeline.preview_titles()` 的结果 → `populate_toc()` 吃的条目。

    html 阶段命中过的标题：`result` 填 `title_html`（那段 HTML 源码），整行标蓝。
    没命中就填未转义的 `title`——此时 `title_html` 只是转义结果，显示它满屏 `&amp;`
    噪声。蓝色落在整行（`html_applied`）上，不是某一列。
    """
    return [
        {
            "level": r.level,
            "raw_title": r.raw_title,
            "result": r.title_html if r.html_applied else r.title,
            "html_applied": r.html_applied,
        }
        for r in results
    ]


def populate_toc(table: ttk.Treeview, entries: Iterable[Mapping[str, Any]]) -> None:
    """扁平目录树条目 → 表格里的层级树。

    每条 entry 需要 `raw_title` / `level`；`result` 缺省与 `raw_title` 相同，
    `deleted` 为真时画删除线，`html_applied` 为真时整行标蓝（html 阶段命中过），
    `open` 为真时默认展开。`result` / `html_applied` 由 `entries_from_preview()` 算好。

    两个 tag 会叠加：一条标题既删除又被 html 规则命中时，删除线照画，颜色归删除线
    （见 `theme.apply_toc_theme()` 里两个 tag 的配置顺序）。
    """
    stack: list[tuple[int, str]] = []  # (level, item_id)，栈顶是当前父节点
    for entry in entries:
        level = int(entry.get("level", 0))
        title = str(entry.get("raw_title", ""))
        result = str(entry.get("result", title))
        while stack and stack[-1][0] >= level:
            stack.pop()
        parent = stack[-1][1] if stack else ""
        item_id = table.insert(parent, "end", values=(title, result))
        tags: tuple[str, ...] = ()
        if entry.get("deleted"):
            tags += (_TAG_DELETED,)
        if entry.get("html_applied"):
            tags += (_TAG_HTML,)
        if tags:
            table.item(item_id, tags=tags)
        if entry.get("open"):
            table.item(item_id, open=True)
        stack.append((level, item_id))


def _make_table(parent: ctk.CTkFrame) -> ttk.Treeview:
    holder = ctk.CTkFrame(parent, fg_color="transparent")
    holder.grid(row=2, column=0, sticky="nsew", padx=GROUP_PADX, pady=_PADY_TOOLBAR)
    holder.grid_rowconfigure(0, weight=1)
    holder.grid_columnconfigure(0, weight=1)

    table = ttk.Treeview(
        holder,
        columns=("title", "result"),
        show="tree headings",
        height=TABLE_HEIGHT,
        style=_STYLE_NAME,
    )
    table.heading("#0", text="")
    table.column("#0", width=TREE_COL_WIDTH, minwidth=TREE_COL_WIDTH, stretch=False)
    table.heading("title", text="标题")
    table.heading("result", text="替换结果")
    table.column("title", width=TITLE_WIDTH, anchor="w", stretch=True)
    table.column("result", width=RESULT_WIDTH, anchor="w", stretch=True)

    vsb = ttk.Scrollbar(holder, orient="vertical", command=table.yview)
    hsb = ttk.Scrollbar(holder, orient="horizontal", command=table.xview)
    table.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

    table.grid(row=0, column=0, sticky="nsew")
    vsb.grid(row=0, column=1, sticky="ns")
    hsb.grid(row=1, column=0, sticky="ew")
    return table


def _label_row(parent: ctk.CTkFrame, label: str, font: ctk.CTkFont) -> ctk.CTkFrame:
    """「标签 + 控件」那一行的容器，返回后把控件 pack 进去即可。"""
    row = ctk.CTkFrame(parent, fg_color="transparent")
    row.grid(row=0, column=0, sticky="w")
    ctk.CTkLabel(row, text=label, font=font).pack(side="left")
    return row


# TODO: 接 core 后删掉本表，改由 core.pipeline 的扫描结果填充 populate_toc()
_TEST_ENTRIES: tuple[dict[str, Any], ...] = (
    {"raw_title": "第一卷 起源", "level": 2, "open": True},
    {"raw_title": "第一章 开端", "level": 3},
    {"raw_title": "第二章 离别", "level": 3, "open": True},
    {"raw_title": "第一节 清晨", "level": 4},
    {"raw_title": "第二卷 风暴", "level": 2, "open": True},
    {"raw_title": "第三章 重逢", "level": 3},
)
