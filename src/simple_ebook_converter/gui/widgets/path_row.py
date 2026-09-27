"""一行「标签 + 路径框 + 浏览/清除按钮」。

新增的行必须接上 `on_change` 并调 `ScrollFrame.retag_all()`（见
`extra_levels.add()` 一类的动态增删），否则新增行既不触发重扫、滚轮也失效。
"""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from tkinter import filedialog

import tkinter.ttk as ttk

from ..metrics import s
from .path_entry import PathEntry

#: 路径对话框的过滤器
ANY_FILE = [("所有文件", "*.*")]
CSS_FILES = [("CSS", "*.css"), ("所有文件", "*.*")]
JSON_FILES = [("JSON", "*.json"), ("所有文件", "*.*")]
IMAGE_FILES = [("图片", "*.png *.jpg *.jpeg"), ("所有文件", "*.*")]
FONT_FILES = [("字体", "*.ttf *.otf *.woff *.woff2"), ("所有文件", "*.*")]
EPUB_FILES = [("EPUB", "*.epub"), ("所有文件", "*.*")]

#: 各用途的对话框配置
_PICKERS: dict[str, tuple[str, list]] = {
    "input": ("选择输入文件", ANY_FILE),
    "output": ("选择输出文件", EPUB_FILES),
    "css": ("选择 CSS 文件", CSS_FILES),
    "json": ("选择 JSON 文件", JSON_FILES),
    "image": ("选择封面图", IMAGE_FILES),
    "font": ("选择字体文件", FONT_FILES),
    "font_dir": ("选择字体文件夹", ANY_FILE),
}


class PathRow(ttk.Frame):
    """标签 + `PathEntry` + 按钮组。按钮组在标签右侧、路径框之后。"""

    def __init__(
        self,
        master: tk.Misc,
        label: str,
        *,
        kind: str = "output",
        picker: str | None = None,
        with_clear: bool = True,
        on_change: Callable[[], None] | None = None,
        on_valid: Callable[[Path | None], None] | None = None,
        **kwargs,
    ) -> None:
        super().__init__(master, **kwargs)
        self._picker = picker or kind
        self._on_change = on_change
        self.on_valid = on_valid

        ttk.Label(self, text=label).grid(row=0, column=0, sticky="w", padx=(0, s(6)))
        self.entry = PathEntry(
            self, kind=kind, on_change=self._changed, on_valid=self._passed, width=32
        )
        self.entry.grid(row=0, column=1, sticky="ew")
        self.columnconfigure(1, weight=1)
        # hint 挂在 entry 上，外部要提示文案时不必摸两层
        self.hint = self.entry.hint

        buttons = ttk.Frame(self)
        buttons.grid(row=0, column=2, sticky="w", padx=(s(4), 0))
        ttk.Button(buttons, text="浏览", command=self.browse, width=6).pack(side="left")
        if with_clear:
            ttk.Button(buttons, text="清除", command=self.clear, width=6).pack(
                side="left", padx=(s(4), 0)
            )

        # 提示文字在整行下面，跨三列
        self.hint.grid(row=1, column=0, columnspan=3, sticky="w")

    # ---------- 值 ----------

    def get(self) -> str:
        return self.entry.get().strip()

    def set(self, value: str | None) -> None:
        self.entry.delete(0, tk.END)
        if value:
            self.entry.insert(0, str(value))

    def get_path(self):
        return self.entry.get_path()

    def set_state(self, state: str, message: str = "") -> None:
        self.entry.set_state(state, message)

    # ---------- 事件 ----------

    def _changed(self) -> None:
        if self._on_change is not None:
            self._on_change()

    def _passed(self, path) -> None:
        if self.on_valid is not None:
            self.on_valid(path)

    def browse(self) -> str:
        """弹对话框选文件。取消返回空串（不改当前值）。"""
        title, filetypes = _PICKERS.get(self._picker, ("选择文件", ANY_FILE))
        chosen = filedialog.askopenfilename(title=title, filetypes=filetypes)
        if not chosen:
            return ""
        self.set(chosen)
        self.entry.validate()
        self._changed()
        return chosen

    def clear(self) -> None:
        self.set("")
        self.entry.clear_message()
        self._changed()
