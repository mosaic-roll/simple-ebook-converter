"""右侧目录面板：目录树预览 + 编辑（改标题、删除线、深度）。

目录树条目是**扁平列表**（文档序），层级由 `level` 决定，没有 children 嵌套。
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from pathlib import Path
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
    TAG_DELETED,
    TAG_HTML,
    TAG_HTML_DELETED,
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
    # 不在这里填初始数据：面板建好后由 app 负责（ctx.toc_entries → _refresh_toc_preview），
    # 在此填充只会被立即覆盖一次。
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
        command=lambda: set_deleted(table, ctx.toc_entries, True),
    ).pack(side="left", padx=(0, BTN_GAP))
    ctk.CTkButton(
        right,
        text="恢复",
        width=BTN_W_M,
        font=font,
        command=lambda: set_deleted(table, ctx.toc_entries, False),
    ).pack(side="left")

    return {
        "panel": panel,
        "table": table,
        "depth_menu": depth_menu,
    }


def _tags_for(deleted: bool, html_hit: bool) -> tuple[str, ...]:
    """一个条目最终该挂哪些 tag。

    删除优先：既被标记删除又命中 html 规则时走 `TAG_HTML_DELETED`（灰字 + 删除线），
    蓝色等恢复后才回来。用第三个 tag 而不是让 `TAG_DELETED` / `TAG_HTML` 抢前景色，
    不依赖 Tk 的多 tag 优先级。
    """
    if deleted and html_hit:
        return (TAG_HTML_DELETED,)
    if deleted:
        return (TAG_DELETED,)
    if html_hit:
        return (TAG_HTML,)
    return ()


def set_deleted(table: ttk.Treeview, entries: list[dict], deleted: bool) -> None:
    """给选中的条目打/去删除线，并把标记写回 `entries`。

    表格 item 的 iid 就是它在 `entries` 里的下标（见 `populate_toc`），据此一一对应。
    删除**不删**正文也不把条目从树上摘下来，原样留着显示删除线，装配时再自动融合到
    前一条、内容当正文处理（和 CLI 的「目录树 JSON → --toc-file」那条路一样）。

    这里读—改—写而不是直接覆盖 `tags`：覆盖会把 html 命中的蓝色一起抹掉。
    """
    for item_id in table.selection():
        index = int(item_id)
        if 0 <= index < len(entries):
            entries[index]["deleted"] = deleted
        current = set(table.item(item_id, "tags") or ())
        html_hit = bool(current & {TAG_HTML, TAG_HTML_DELETED})
        table.item(item_id, tags=_tags_for(deleted, html_hit))


def entries_from_preview(results: Iterable[Any]) -> list[dict[str, Any]]:
    """`core.pipeline.preview_titles()` 的结果 → `populate_toc()` 吃的条目。

    命中过 html 规则的标题：`result` 填 `title_html`（HTML 源码），整行标蓝；没命中
    填未转义的 `title`——那时 `title_html` 只是转义结果，显示它满屏 `&amp;` 噪声。
    """
    return [
        {
            "level": r.level,
            "raw_title": r.raw_title,
            "result": r.title_html if r.html_hit else r.title,
            "html_hit": r.html_hit,
        }
        for r in results
    ]


def populate_toc(table: ttk.Treeview, entries: Iterable[Mapping[str, Any]]) -> None:
    """扁平目录树条目 → 表格里的层级树。

    每条 entry 需要 `raw_title` / `level`；`result` 默认与 `raw_title` 相同，
    `deleted` 为真时画删除线，`html_hit` 为真时整行标蓝（html 阶段命中过）。
    `result` / `html_hit` 由 `entries_from_preview()` 算好。

    item 的 iid 用条目下标，`set_deleted()` 靠它把删除标记写回对应 entry。
    tag 由 `_tags_for()` 统一算：删除优先，既删除又命中时灰字带删除线，蓝色等恢复后回来。
    """
    stack: list[tuple[int, str]] = []  # (level, item_id)，栈顶是当前父节点
    for index, entry in enumerate(entries):
        level = int(entry.get("level", 0))
        title = str(entry.get("raw_title", ""))
        result = str(entry.get("result", title))
        while stack and stack[-1][0] >= level:
            stack.pop()
        parent = stack[-1][1] if stack else ""
        # 全部默认展开：每次刷新重建整棵树，保留展开态需要额外状态；
        # 目录通常几十条，全展开比记住用户折叠了哪几节更简单。
        item_id = table.insert(
            parent, "end", iid=str(index), values=(title, result), open=True
        )
        tags = _tags_for(bool(entry.get("deleted")), bool(entry.get("html_hit")))
        if tags:
            table.item(item_id, tags=tags)
        # level 0（前言）只装自己的段落，不当容器往下挂（与 core 的 TreeBuilder.add 同）：
        # 它在书里按 h3 渲染，与卷同级；若推进栈，后续 level 2/3 的条目会挂到它下面，
        # 预览里就看成「前言比卷高一层」。
        if level > 0:
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


# 面板初始展示的示例目录（真实数据来自扫描，app 启动时会立即用它覆盖此表）。
# 命名不加下划线前缀，因为跨模块导入使用。
SAMPLE_ENTRIES: tuple[dict[str, Any], ...] = (
    {"raw_title": "第一卷 起源", "level": 2},
    {"raw_title": "第一章 开端", "level": 3},
    {"raw_title": "第二章 离别", "level": 3},
    {"raw_title": "第一节 清晨", "level": 4},
    {"raw_title": "第二卷 风暴", "level": 2},
    {"raw_title": "第三章 重逢", "level": 3},
)


def export_toc_json(entries: list[dict], path: Path) -> None:
    """导出目录 JSON：由 entries 重建 Node 后调 `core.toc.to_json` 序列化。

    格式与 `--toc-only --toc-format json` 完全一致（raw_title / level /
    class_name / line，`deleted` 为真时才写）。条目缺行号（未扫描）时报 ValueError。
    """
    from ..core.parser import Node
    from ..core.toc import to_json

    nodes = [
        Node(
            title=str(e.get("raw_title", "")),
            raw_title=str(e.get("raw_title", "")),
            level=int(e.get("level", 0)),
            class_name=str(e.get("class_name", "")),
            line=int(e.get("line", 0)),
            deleted=bool(e.get("deleted", False)),
        )
        for e in entries
    ]
    if any(n.line < 1 for n in nodes):
        raise ValueError("目录条目缺少行号，请先「重新扫描」再导出")
    depth = max((n.level for n in nodes), default=6)
    data = to_json(nodes, depth=depth)
    Path(path).write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def import_toc_json(path: Path) -> list[dict]:
    """从 JSON 文件加载目录条目（与 `to_json` 导出一致），返回扁平条目列表。

    只做读取与字段校验，不挂树、不切正文——界面要的是 raw_title / level /
    class_name / line / deleted，生成阶段再由 core 从这些条目重建。
    读不了、不是列表或字段非法时抛 `ValueError`。
    """
    from ..core.toc import load_toc

    data = load_toc(path)
    entries: list[dict] = []
    for i, item in enumerate(data, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"第 {i} 个条目不是 JSON 对象")  # noqa: TRY004  # 用户数据校验统一抛 ValueError
        title = item.get("raw_title")
        level = item.get("level")
        line = item.get("line")
        if not isinstance(title, str) or not title.strip():
            raise ValueError(f"第 {i} 个条目缺少标题（raw_title）")
        if not isinstance(level, int) or isinstance(level, bool) or not 0 <= level <= 6:
            raise ValueError(f"第 {i} 个条目的层级不合法：{level!r}")
        if not isinstance(line, int) or isinstance(line, bool) or line < 1:
            raise ValueError(f"第 {i} 个条目的行号不合法：{line!r}")
        class_name = item.get("class_name", "")
        if not isinstance(class_name, str):
            raise ValueError(f"第 {i} 个条目的 class_name 不合法：{class_name!r}")  # noqa: TRY004  # 同上
        deleted = item.get("deleted", False)
        if not isinstance(deleted, bool):
            raise ValueError(f"第 {i} 个条目的 deleted 只能是 true/false")  # noqa: TRY004  # 同上
        entries.append(
            {
                "raw_title": title.strip(),
                "level": level,
                "class_name": class_name,
                "line": line,
                "deleted": deleted,
            }
        )
    return entries
