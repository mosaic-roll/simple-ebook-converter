"""「替换」页签：交给 `ReplacementEditor`。

这页没有自己的状态，全部转交表格：`get_rows()` 直接喂 `UiValues.rules`，
`build_config_from_ui()` 再交给 core 的 `rules_from_rows()`。
"""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
import ttkbootstrap as ttk

from ..metrics import s
from ..widgets.replacement_editor import ReplacementEditor
from ..widgets.scroll_frame import ScrollFrame


class ReplaceTab(ttk.Frame):
    """替换规则。"""

    def __init__(
        self,
        master: tk.Misc,
        *,
        on_change: Callable[[], None] | None = None,
        **kwargs,
    ) -> None:
        super().__init__(master, **kwargs)
        wrap = ScrollFrame(self)
        wrap.pack(fill="both", expand=True)
        body = ttk.Frame(wrap.inner, padding=(s(12), s(12)))
        body.pack(fill="both", expand=True)

        ttk.Label(
            body,
            text="替换只作用于标题。规则按表格顺序依次执行，顺序不同结果不同。",
            bootstyle="secondary",
        ).pack(anchor="w", pady=(0, s(8)))
        self.editor = ReplacementEditor(body, on_change=on_change)
        self.editor.pack(fill="both", expand=True)

        wrap.retag_all()

    # ---------- 值 ----------

    def get_rows(self) -> list[tuple[str, str, str]]:
        return self.editor.get_rows()

    def set_rows(self, rows) -> None:
        self.editor.set_rows(rows)
