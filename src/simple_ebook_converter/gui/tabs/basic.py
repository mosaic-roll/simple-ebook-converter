"""「基础」页签：输入、输出、书籍信息、清理开关。

值收集只做一件事：把控件内容搬进 `BasicValues`，**不做解释**。校验在
`build_config_from_ui()` 之后由 core 兜底，这里只管即时反馈（红/黄框 + 提示）。
"""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from tkinter import ttk

from ...core.encoding import ENCODING_CHOICES
from ..build_config_from_ui import BasicValues
from ..metrics import s
from ..widgets.path_row import PathRow
from ..widgets.scroll_frame import ScrollFrame


class BasicTab(ttk.Frame):
    """基础设置。`get()` 收成一个 `BasicValues`。"""

    def __init__(
        self,
        master: tk.Misc,
        *,
        on_change: Callable[[], None] | None = None,
        on_input_chosen: Callable[[str], None] | None = None,
        **kwargs,
    ) -> None:
        super().__init__(master, **kwargs)
        self.on_change = on_change
        self.on_input_chosen = on_input_chosen

        wrap = ScrollFrame(self)
        wrap.pack(fill="both", expand=True)
        body = ttk.Frame(wrap.inner, padding=(s(12), s(12)))
        body.pack(fill="both", expand=True)

        self.input_row = PathRow(
            body, "输入文件", kind="input", on_change=self._changed, on_valid=self._input_valid
        )
        self.input_row.pack(fill="x")
        self.input_row.hint.grid_forget()  # 输入行有专用提示，不重复占位

        # 编码候选取自 core 的 ENCODING_CHOICES（首项就是 auto），不另抄一份
        self._encoding = self._choice_row(body, "编码", ENCODING_CHOICES, "自动检测")
        self.out_row = PathRow(body, "输出文件", kind="output", on_change=self._changed)
        self.out_row.pack(fill="x", pady=(s(10), 0))

        self.v_overwrite = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            body, text="覆盖已有文件", variable=self.v_overwrite, command=self._changed
        ).pack(anchor="w", pady=(s(6), 0))

        meta = ttk.LabelFrame(body, text="书籍信息", padding=(s(8), s(6)))
        meta.pack(fill="x", pady=(s(12), 0))
        # 属性名与 BasicValues 的字段一一对应，get()/set() 直接引用
        self._title = self._text_row(meta, "书名", 0)
        self._author = self._text_row(meta, "作者", 1)
        self._date = self._text_row(meta, "出版日期", 2, "2024-05-13")
        self._language = self._text_row(meta, "语言", 3, "zh")

        self.cover_row = PathRow(
            body, "封面图", kind="image", picker="image", on_change=self._changed
        )
        self.cover_row.pack(fill="x", pady=(s(10), 0))

        self.v_text_cover = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            body, text="无封面图时生成文字封面页", variable=self.v_text_cover, command=self._changed
        ).pack(anchor="w")

        self.v_clean = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            body, text="清理文本（去段首段尾空格、删空行）", variable=self.v_clean, command=self._changed
        ).pack(anchor="w", pady=(s(6), 0))

        wrap.retag_all()

    # ---------- 值 ----------

    def get(self) -> BasicValues:
        return BasicValues(
            input=self.input_row.get(),
            encoding=self._encoding.get(),
            out=self.out_row.get(),
            overwrite=bool(self.v_overwrite.get()),
            clean=bool(self.v_clean.get()),
            title=self._title.get().strip(),
            author=self._author.get().strip(),
            date=self._date.get().strip(),
            language=self._language.get().strip(),
            cover=self.cover_row.get(),
            text_cover=bool(self.v_text_cover.get()),
        )

    def set(self, values: BasicValues) -> None:
        self.input_row.set(values.input)
        self._encoding.set(values.encoding)
        self.out_row.set(values.out)
        self.v_overwrite.set(values.overwrite)
        self.v_clean.set(values.clean)
        self._title.set(values.title)
        self._author.set(values.author)
        self._date.set(values.date)
        self._language.set(values.language)
        self.cover_row.set(values.cover)
        self.v_text_cover.set(values.text_cover)

    def set_input(self, path: str) -> None:
        """外部（拖入/命令行/最近文件）改了输入路径时同步。只在真的变了才回调。"""
        if self.input_row.get() == path:
            return
        self.input_row.set(path)
        self._changed()

    def detect_border_support(self, root: tk.Misc) -> None:
        for row in (self.input_row, self.out_row, self.cover_row):
            row.detect_border_support(root)

    # ---------- 内部 ----------

    def _text_row(
        self, parent: ttk.Frame, label: str, row: int, hint: str = ""
    ) -> tk.StringVar:
        """一行标签 + Entry。返回其 StringVar。"""
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=(0, s(4)))
        var = tk.StringVar()
        entry = ttk.Entry(parent, textvariable=var, width=32)
        entry.grid(row=row, column=1, sticky="ew", padx=(s(6), 0), pady=(0, s(4)))
        entry.bind("<KeyRelease>", lambda _e: self._changed(), add="+")
        if hint:
            ttk.Label(parent, text=hint, style="Muted.TLabel").grid(
                row=row, column=2, sticky="w", padx=(s(6), 0)
            )
        parent.columnconfigure(1, weight=1)
        return var

    def _choice_row(self, parent: ttk.Frame, label: str, choices, hint: str = ""):
        """一行标签 + 只读下拉。返回 StringVar。"""
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=(s(8), 0))
        ttk.Label(row, text=label).pack(side="left")
        var = tk.StringVar()
        combo = ttk.Combobox(row, textvariable=var, values=choices, state="readonly", width=18)
        combo.pack(side="left", padx=(s(6), 0))
        combo.bind("<<ComboboxSelected>>", lambda _e: self._changed())
        if hint:
            ttk.Label(row, text=hint, style="Muted.TLabel").pack(side="left", padx=(s(8), 0))
        return var

    def _input_valid(self, _path) -> None:
        """输入文件确定后告知外部（要重扫目录）。"""
        if self.on_input_chosen is not None:
            self.on_input_chosen(self.input_row.get())

    def _changed(self) -> None:
        if self.on_change is not None:
            self.on_change()
