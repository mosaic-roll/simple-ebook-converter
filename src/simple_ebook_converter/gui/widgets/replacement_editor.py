"""替换规则编辑器：`(查找, 替换为, 阶段)` 三列表格。

**为什么是表格而不是文本框**：规则是**有序列表**，顺序即语义（先按哪条后按哪条）。
文本框里 JSON 列表没法一眼看出顺序对不对，而表格天然按显示顺序执行。core 的
`rules_from_rows()` 就是按行序收规则，这里直接喂行。

表格 + Treeview 的两个限制与 `TocPanel` 同源：表头不能嵌控件、树不能横向滚动，
所以「查找」列宽固定、宽内容靠悬停提示或直接编辑。

空行一律忽略（`rules_from_rows` 会跳过 `pattern` 为空的行），故删除行不必
重排序号。
"""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
import tkinter.ttk as ttk

from ...core.replace import STAGE_LABELS, STAGES, Rule, rules_from_rows, rules_to_json
from .. import theme
from ..fonts import font
from ..metrics import s, set_row_height

#: 三列
FIND, REPL, STAGE = "find", "replace", "stage"

#: 行高与列宽（设计稿像素）
ROW_HEIGHT = 26
COL_WIDTHS = {FIND: 200, REPL: 200, STAGE: 70}
COL_MINWIDTHS = {FIND: 120, REPL: 120, STAGE: 56}
HEADINGS = {FIND: "查找（正则）", REPL: "替换为", STAGE: "阶段"}

#: 阶段下拉的中文标签，取自 core —— 界面不另立一套
STAGE_CHOICES = tuple(STAGE_LABELS[stage] for stage in STAGES)

#: 标签 → 取值，反查用
_BY_LABEL = {label: stage for stage, label in STAGE_LABELS.items()}


class ReplacementEditor(ttk.Frame):
    """替换规则表格 + 工具条。"""

    def __init__(
        self,
        master: tk.Misc,
        *,
        on_change: Callable[[], None] | None = None,
        **kwargs,
    ) -> None:
        super().__init__(master, **kwargs)
        self.on_change = on_change
        self._rows: list[dict] = []

        self._build_tree()
        self._build_toolbar()

    # ---------- 布局 ----------

    def _build_tree(self) -> None:
        wrap = ttk.Frame(self)
        wrap.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(
            wrap,
            columns=(FIND, REPL, STAGE),
            show="headings",
            selectmode="browse",
            style="Mono.Treeview",
        )
        for column in (FIND, REPL, STAGE):
            self.tree.heading(column, text=HEADINGS[column])
            # 全部可拉伸，但「查找」给足初宽 —— 规则里最长的通常是它
            self.tree.column(
                column,
                width=s(COL_WIDTHS[column]),
                minwidth=s(COL_MINWIDTHS[column]),
                stretch=True,
            )
        set_row_height("Mono.Treeview", px=ROW_HEIGHT)

        vbar = ttk.Scrollbar(wrap, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vbar.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vbar.pack(side="right", fill="y")

        self.tree.bind("<Double-1>", self._on_edit)
        self.tree.bind("<Delete>", self._on_delete)
        self.hint = ttk.Label(self, text="")
        theme.on_colors_changed(self.tree, self._apply_tree_colors)
        theme.on_colors_changed(
            self.hint, lambda: self.hint.configure(foreground=theme.colors()["error"])
        )

    def _apply_tree_colors(self) -> None:
        self.tree.tag_configure("bad", foreground=theme.colors()["error"])

    def _build_toolbar(self) -> None:
        bar = ttk.Frame(self)
        bar.pack(fill="x", pady=(s(6), 0))
        # 按钮分两行：六个一行在窄栏里放不下，最右边的「导出」会被挤出可视区
        row1 = ttk.Frame(bar)
        row1.pack(fill="x")
        for text, command in (
            ("添加", self.add),
            ("删除", self.remove_selected),
            ("上移", lambda: self.move_selected(-1)),
            ("下移", lambda: self.move_selected(1)),
        ):
            ttk.Button(row1, text=text, width=6, command=command).pack(
                side="left", padx=(0, s(4))
            )

        row2 = ttk.Frame(bar)
        row2.pack(fill="x", pady=(s(4), 0))
        for text, command in (("导入", self.import_json), ("导出", self.export_json)):
            ttk.Button(row2, text=text, width=6, command=command).pack(
                side="left", padx=(0, s(4))
            )

        # 阶段说明常驻：html 阶段的行为和 raw 差很多，值得常驻而不是塞进帮助。
        # 独占一行并按可用宽度折行，免得在窄栏里把整行撑出可视区。
        self._stage_hint = ttk.Label(
            bar,
            text="「HTML」阶段匹配转义后的标题，可塞 <span> 之类标签",
        )
        self._stage_hint.pack(anchor="w", fill="x", pady=(s(4), 0))
        self._stage_hint.bind("<Configure>", self._wrap_stage_hint)

        self.hint.pack(anchor="w", pady=(s(4), 0))

    def _wrap_stage_hint(self, event: tk.Event) -> None:
        if event.width and self._stage_hint.cget("wraplength") != event.width:
            self._stage_hint.configure(wraplength=event.width)

    # ---------- 值 ----------

    def get_rows(self) -> list[tuple[str, str, str]]:
        """`(查找, 替换为, 阶段标签)` 三元组列表，按表格显示顺序。

        阶段给**中文标签**：`rules_from_rows` 认标签也认取值，给标签是为了存进
        settings 时人可读。
        """
        return [
            (self.tree.set(iid, FIND), self.tree.set(iid, REPL), self.tree.set(iid, STAGE))
            for iid in self._order()
        ]

    def get_rules(self) -> list[Rule]:
        """当前规则（已解析、已校验）。`rules_from_rows` 会跳过 `查找` 为空的行。"""
        return rules_from_rows(self.get_rows())

    def get_json(self) -> str:
        """当前规则 → core 认的 JSON 文本。空规则给 `[]` 而不是空串。"""
        return rules_to_json(self.get_rules())

    def set_rows(self, rows) -> None:
        """按 `(查找, 替换为, 阶段)` 覆盖全部行。`阶段` 认标签也认取值。"""
        self._clear()
        for pattern, replacement, stage in rows:
            self._insert(pattern, replacement, _label_of(stage))
        self._changed()

    def set_json(self, text: str) -> None:
        """用一段 core 格式的 JSON 覆盖全部行；不合法抛 `ValueError`（消息可展示）。"""
        from ..core.replace import rules_from_json

        self.set_rows([(r.pattern, r.replace, r.stage) for r in rules_from_json(text)])

    # ---------- 增删改 ----------

    def add(self, pattern: str = "", replacement: str = "", stage: str = "") -> None:
        self._insert(pattern, replacement, stage or STAGE_CHOICES[0])
        self._changed()

    def remove_selected(self) -> int:
        """删掉选中的行，返回删了几行。"""
        iids = self.tree.selection()
        if not iids:
            return 0
        for iid in iids:
            self.tree.delete(iid)
        self._changed()
        return len(iids)

    def move_selected(self, delta: int) -> bool:
        """上移/下移。**顺序即语义**，所以必须能调，且调整后立刻通知刷新预览。"""
        iids = self._order()
        index = next((i for i, iid in enumerate(iids) if iid in self.tree.selection()), None)
        if index is None:
            return False
        target = index + delta
        if not 0 <= target < len(iids):
            return False
        moved = iids[index]
        # 用 `Treeview.move()`，不要 detach + insert：detach 后 item id 仍在，
        # 再用同一个 id insert 会抛 `Item X already exists`，行就「消失」了。
        self.tree.move(moved, "", target)
        self.tree.selection_set(moved)
        self.tree.see(moved)
        self._changed()
        return True

    def _on_edit(self, event: tk.Event) -> None:
        """双击开编辑框：单行内联编辑，`Enter` 提交、`Esc` 取消。"""
        if self.tree.identify_region(event.x, event.y) != "cell":
            return
        iid = self.tree.identify_row(event.y)
        if not iid:
            return
        column = self.tree.identify_column(event.x)  # #1/#2/#3
        if column == "#3":  # 阶段列用下拉，不开文本框
            return
        name = (FIND, REPL)[int(column[1:]) - 1]
        self._edit_cell(iid, name)
        return "break"

    def _on_delete(self, _event: tk.Event) -> str:
        if self.remove_selected():
            return "break"
        return None

    def _edit_cell(self, iid: str, name: str) -> None:
        """在单元格里放一个临时 Entry / Combobox，提交或取消后销毁。"""
        bbox = self.tree.bbox(iid, name)
        if not bbox:
            return
        x, y, width, height = bbox
        current = self.tree.set(iid, name)
        variable = tk.StringVar(value=current)

        def commit() -> None:
            self.tree.set(iid, name, variable.get())
            box.destroy()
            self.tree.focus_set()
            self._changed()

        def cancel() -> None:
            box.destroy()
            self.tree.focus_set()

        if name == STAGE:
            box: tk.Misc = ttk.Combobox(
                self, textvariable=variable, values=STAGE_CHOICES, state="readonly", width=12
            )
        else:
            box = ttk.Entry(self, textvariable=variable, font=font("mono"))
        box.place(x=x, y=y, width=width, height=height)
        box.focus_set()
        box.selection_range(0, tk.END)
        box.bind("<Return>", lambda _e: commit())
        box.bind("<Escape>", lambda _e: cancel())
        # FocusOut 绑 commit 而不是 cancel：Entry 里按 Tab 提交是最自然的操作。
        # 注意它会盖过 Escape —— Enter 先触发 commit 并销毁控件，随后 FocusOut
        # 在已销毁的 box 上触发，Tk 会忽略，这次调用是 no-op，不会二次写回。
        box.bind("<FocusOut>", lambda _e: commit())
        if name == STAGE:
            box.tk.call("ttk::combobox::Post", box)

    # ---------- 导入导出 ----------

    def import_json(self) -> int:
        """读一个 core 格式的 JSON 规则文件。失败只提示、不清空已有规则。"""
        from tkinter import filedialog

        from ..core.pipeline import read_input  # noqa: F401  仅为统一错误类型

        path = filedialog.askopenfilename(
            title="导入替换规则", filetypes=[("JSON", "*.json"), ("所有文件", "*.*")]
        )
        if not path:
            return 0
        try:
            self.set_json(open(path, encoding="utf-8").read())
        except (OSError, ValueError) as exc:
            self._error(f"导入失败：{exc}")
            return 0
        self.hint.configure(text="")
        return len(self.get_rules())

    def export_json(self) -> str:
        """把当前规则写成 JSON 文本并弹保存框。取消返回空串。"""
        from tkinter import filedialog

        path = filedialog.asksaveasfilename(
            title="导出替换规则",
            defaultextension=".json",
            filetypes=[("JSON", "*.json")],
        )
        if not path:
            return ""
        try:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(self.get_json())
        except OSError as exc:
            self._error(f"导出失败：{exc}")
            return ""
        self.hint.configure(text="")
        return path

    # ---------- 内部 ----------

    def _order(self) -> list[str]:
        """当前显示顺序的 iid 列表。行号会随插入/删除漂移，故每次都现取。"""
        return list(self.tree.get_children())

    def _insert(self, pattern: str, replacement: str, stage_label: str) -> str:
        iid = self.tree.insert(
            "", "end", values=(pattern, replacement, stage_label)
        )
        return iid

    def _clear(self) -> None:
        self.tree.delete(*self.tree.get_children())

    def _error(self, message: str) -> None:
        self.hint.configure(text=message)

    def _changed(self) -> None:
        if self.on_change is not None:
            self.on_change()


def _label_of(stage: str) -> str:
    """取值或标签 → 中文标签。"""
    return STAGE_LABELS.get(stage, stage if stage in _BY_LABEL else STAGE_CHOICES[0])
