"""通用 Treeview 构建器：树 + 滚动条的模板。

`toc_panel.py` 和 `replacement_editor.py` 的 `_build_tree` 几乎逐字相同，
只差列定义和样式名。抽成工厂函数后两处都不再重复。
"""

from __future__ import annotations

import tkinter as tk
import tkinter.ttk as ttk

from ..metrics import s, set_row_height


def build_treeview(
    parent: tk.Misc,
    *,
    columns: tuple[str, ...],
    headings: dict[str, str],
    widths: dict[str, int],
    minwidths: dict[str, int],
    style: str,
    row_height: int,
    anchors: dict[str, str] | None = None,
    heading_anchors: dict[str, str] | None = None,
    stretches: dict[str, bool] | None = None,
) -> tuple[ttk.Treeview, ttk.Scrollbar, ttk.Frame]:
    """构建「树 + 滚动条」的标准布局。

    返回 ``(tree, vbar, wrap)``，调用方负责 pack/grid 它们。
    """
    wrap = ttk.Frame(parent)
    wrap.pack(fill="both", expand=True)
    tree = ttk.Treeview(
        wrap,
        columns=columns,
        show="headings",
        selectmode="browse",
        style=style,
    )
    anchors = anchors or {}
    heading_anchors = heading_anchors or anchors
    stretches = stretches or {}
    for column in columns:
        heading_kw: dict[str, object] = {"text": headings[column]}
        ha = heading_anchors.get(column)
        if ha:
            heading_kw["anchor"] = ha
        tree.heading(column, **heading_kw)
        col_kw: dict[str, object] = {
            "width": s(widths[column]),
            "minwidth": s(minwidths[column]),
            "stretch": stretches.get(column, True),
        }
        a = anchors.get(column)
        if a:
            col_kw["anchor"] = a
        tree.column(column, **col_kw)
    set_row_height(style, px=row_height)

    vbar = ttk.Scrollbar(wrap, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=vbar.set)
    tree.pack(side="left", fill="both", expand=True)
    vbar.pack(side="right", fill="y")
    return tree, vbar, wrap
