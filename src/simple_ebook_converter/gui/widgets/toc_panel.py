"""目录面板：左栏的目录表格 + 工具条 + 底部设置。

三处与 Tk 有关的妥协都在这里：

* **表头不能嵌控件** —— `Treeview` 的表头不是 widget，嵌不了 Checkbutton。所以
  「全部启用」放到工具条里。
* **行删除线做不到** —— `tree.tag_configure(font=…)` 在 Tk 8.6 上被忽略。改用
  前景变灰 + `check` 列留空。
* **行高必须显式设** —— Tk 默认行高不跟 `tk scaling` 走，150% 下字大了行没变高、
  文字上下被裁。所以用独立 style 名 + `metrics.set_row_height()`。

`deleted` 走 `toc_file` 回传给 core（§7.5）：本面板只负责收集「哪些条目被划掉」，
合并语义由 `core.toc.tree_from_json` 实现，界面不自己写。
"""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from tkinter import ttk

from ..build_config_from_ui import TocSettings, entry_id
from ..metrics import s, set_row_height
from ..theme import COLORS

#: 三列
CHECK, TITLE, RESULT = "check", "title", "result"

#: 行高（设计稿像素）与三列的宽
ROW_HEIGHT = 24
COL_WIDTHS = {CHECK: 32, TITLE: 260, RESULT: 180}
COL_MINWIDTHS = {CHECK: 32, TITLE: 120, RESULT: 100}
HEADINGS = {CHECK: "启用", TITLE: "标题", RESULT: "替换后"}

#: 「已划掉」用的行 tag。不用删除线（`tag_configure(font=…)` 被忽略），用灰前景 + 空 check
TAG_DELETED = "deleted"

#: 目录深度范围
DEPTH_RANGE = (1, 6)


class TocPanel(ttk.Frame):
    """目录表格 + 工具条 + 目录设置。"""

    def __init__(
        self,
        master: tk.Misc,
        *,
        on_rescan: Callable[[], None] | None = None,
        on_import: Callable[[], None] | None = None,
        on_export: Callable[[], None] | None = None,
        on_setting_change: Callable[[], None] | None = None,
        **kwargs,
    ) -> None:
        super().__init__(master, **kwargs)
        self.on_rescan = on_rescan
        self.on_import = on_import
        self.on_export = on_export
        self.on_setting_change = on_setting_change

        #: 条目 id → 是否划掉。重扫后按 id 复原勾选（`entry_id` = 起:止:raw_title）
        self._deleted: dict[str, bool] = {}
        self._entries: list[dict] = []

        self._build_toolbar()
        self._build_tree()
        self._build_settings()

    # ---------- 布局 ----------

    def _build_toolbar(self) -> None:
        bar = ttk.Frame(self)
        bar.pack(fill="x", pady=(0, s(4)))
        for text, command in (("重扫", self.on_rescan), ("导入", self.on_import), ("导出", self.on_export)):
            ttk.Button(bar, text=text, command=command or (lambda: None)).pack(side="left")

        self.v_all = tk.BooleanVar(value=False)
        self.cb_all = ttk.Checkbutton(bar, text="全部启用", variable=self.v_all, command=self._toggle_all)
        self.cb_all.pack(side="left", padx=(s(12), 0))

    def _build_tree(self) -> None:
        wrap = ttk.Frame(self)
        wrap.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(
            wrap,
            columns=(CHECK, TITLE, RESULT),
            show="headings",
            selectmode="browse",
            style="Toc.Treeview",
        )
        for column in (CHECK, TITLE, RESULT):
            self.tree.heading(column, text=HEADINGS[column])
            self.tree.column(
                column,
                width=s(COL_WIDTHS[column]),
                minwidth=s(COL_MINWIDTHS[column]),
                stretch=column is not TITLE,
            )
        # height 不设，交给 pack(expand=True)
        set_row_height(ttk.Style(self), "Toc.Treeview", px=ROW_HEIGHT)

        vbar = ttk.Scrollbar(wrap, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vbar.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vbar.pack(side="right", fill="y")

        self.tree.tag_configure(TAG_DELETED, foreground=COLORS["del"])
        self.tree.bind("<Button-1>", self._on_click)
        self.set_result_column(None)  # 初始没有替换规则 → 结果列隐藏

    def _build_settings(self) -> None:
        bar = ttk.Frame(self)
        bar.pack(fill="x", pady=(s(6), 0))
        ttk.Label(bar, text="目录深度").pack(side="left")
        self.v_depth = tk.IntVar(value=6)
        ttk.Spinbox(
            bar,
            from_=DEPTH_RANGE[0],
            to=DEPTH_RANGE[1],
            width=4,
            textvariable=self.v_depth,
            command=self._settings_changed,
        ).pack(side="left", padx=(s(4), s(12)))
        self.v_depth.trace_add("write", lambda *_: self._settings_changed())

        self.v_in_spine = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            bar, text="书页含目录", variable=self.v_in_spine, command=self._settings_changed
        ).pack(side="left")

    # ---------- 内容 ----------

    def set_entries(self, entries: list[dict]) -> None:
        """填入新的目录条目。**已划掉的 id 会跨这次重扫保留。**"""
        self._entries = list(entries)
        self.tree.delete(*self.tree.get_children())
        for entry in self._entries:
            iid = entry_id(entry)
            self.tree.insert("", "end", iid=iid, values=self._row_values(entry, iid))

    def set_result_column(self, values: dict[str, str] | None) -> None:
        """显示/隐藏「替换后」列。

        显隐由**传进来的值**决定，不另开一个开关：非空 dict 就显示，`None`/`{}`
        就把宽度设成**字面量 0** 隐藏。规则数归零时预览自然返回空 dict，少一个状态
        就少一处能写错的地方。
        """
        show = bool(values)
        # 隐藏时必须写字面量 0，不能写 s(0)：s() 有 max(1, …) 兜底，会算出 1px，
        # 结果是「明明没有规则却露出一条细缝」。
        self.tree.column(
            RESULT,
            width=s(COL_WIDTHS[RESULT]) if show else 0,
            minwidth=s(COL_MINWIDTHS[RESULT]) if show else 0,
            stretch=show,
        )
        for iid in self.tree.get_children():
            entry = next((e for e in self._entries if entry_id(e) == iid), None)
            if entry is None:
                continue
            shown = values.get(iid, "") if values else ""
            self.tree.set(iid, RESULT, shown)
            self.tree.item(iid, values=self._row_values(entry, iid, shown))

    def set_enabled(self, enabled: bool) -> None:
        """没有输入文件时禁用交互（导入/导出/勾选都没意义）。"""
        for child in self.winfo_children():
            self._set_enabled_recursive(child, enabled)

    def _set_enabled_recursive(self, widget: tk.Misc, enabled: bool) -> None:
        # 勾选框/按钮的「可用」是它们自己的状态，没法从父容器继承
        if isinstance(widget, (ttk.Button, ttk.Checkbutton, ttk.Spinbox)):
            try:
                widget.configure(state="normal" if enabled else "disabled")
            except tk.TclError:
                pass
        for child in widget.winfo_children():
            self._set_enabled_recursive(child, enabled)

    # ---------- 勾选 / 划掉 ----------

    def _row_values(self, entry: dict, iid: str, shown: str = "") -> tuple[str, str, str]:
        deleted = self._deleted.get(iid, False)
        # 已划掉：灰前景 + check 列留空（用空格而不是「□」，少一个字符就不用担心字形）
        mark = "  " if deleted else "√"
        title = " " * (2 * max(0, entry.get("level", 1) - 1)) + entry.get("raw_title", "")
        return (mark, title, shown)

    def _on_click(self, event: tk.Event) -> None:
        """点 `check` 列切换启用；点别处就是普通选中。"""
        if self.tree.identify_region(event.x, event.y) != "cell":
            return
        if self.tree.identify_column(event.x) != "#1":  # #1 = 第一列 = check
            return
        iid = self.tree.identify_row(event.y)
        if not iid:
            return
        self._set_deleted(iid, not self._deleted.get(iid, False))
        return "break"

    def _set_deleted(self, iid: str, deleted: bool) -> None:
        self._deleted[iid] = deleted
        entry = next((e for e in self._entries if entry_id(e) == iid), None)
        if entry is not None:
            shown = self.tree.set(iid, RESULT)
            self.tree.item(
                iid,
                values=self._row_values(entry, iid, shown),
                tags=(TAG_DELETED,) if deleted else (),
            )

    def _toggle_all(self) -> None:
        deleted = not self.v_all.get()  # 全选 = 都不划掉
        for entry in self._entries:
            self._set_deleted(entry_id(entry), deleted)
        self.v_all.set(not deleted)

    # ---------- 设置 ----------

    def _settings_changed(self) -> None:
        if self.on_setting_change is not None:
            self.on_setting_change()

    def get_toc_settings(self) -> TocSettings:
        """底部的目录设置。`toc_in_spine` 是**正面表述**（core 里的键名，别写成 no_toc）。"""
        return TocSettings(
            toc_depth=_clamp_depth(self.v_depth.get()),
            toc_in_spine=bool(self.v_in_spine.get()),
        )

    def set_toc_settings(self, data: TocSettings) -> None:
        self.v_depth.set(_clamp_depth(data.toc_depth))
        self.v_in_spine.set(data.toc_in_spine)

    # ---------- 导出给 core ----------

    def toc_entries_with_flags(self) -> list[dict]:
        """带 `deleted` 标记的目录条目，供 `to_json` 落盘成 `--toc-file` 的形状。"""
        return [
            {**entry, "deleted": True} if self._deleted.get(entry_id(entry), False) else dict(entry)
            for entry in self._entries
        ]

    def deleted_count(self) -> int:
        return sum(1 for value in self._deleted.values() if value)


def _clamp_depth(value) -> int:
    low, high = DEPTH_RANGE
    try:
        return max(low, min(high, int(value)))
    except (TypeError, ValueError):
        return high
