"""状态行：一行文字 + 「在忙吗」。

放在底部（`app._build_status`），铺满整宽，左右两栏的底边因此齐平。
不单独占一条底栏只为了几行字：忙态、上一步结果、标题数都靠这一行。
"""

from __future__ import annotations

import tkinter as tk

import tkinter.ttk as ttk

from .. import theme


class StatusBar(ttk.Frame):
    """底部状态行：忙态、上一步结果、标题数。"""

    def __init__(self, master: tk.Misc, *, on_busy_change=None, **kwargs) -> None:
        super().__init__(master, **kwargs)
        self._busy = False
        self._error = False
        self._on_busy_change = on_busy_change
        self._count = 0
        self._message = ""
        self.text = ttk.Label(self, text="", anchor="e")
        self.text.pack(side="right", fill="x", expand=True)
        theme.on_colors_changed(self, self._apply_colors)

    # ---------- 状态 ----------

    @property
    def busy(self) -> bool:
        return self._busy

    def set_count(self, count: int) -> None:
        """目录条目数。空闲时显示「共 N 个标题」。"""
        self._count = count
        self._update_text()

    def set_text(self, message: str) -> None:
        self._message = message
        self._update_text()

    def begin(self, message: str = "处理中…") -> None:
        """进入忙状态。"""
        self._busy = True
        self._notify_busy()
        self._message = message
        self._update_text()

    def ok(self, message: str = "") -> None:
        self._finish()
        self._error = False
        self._apply_colors()
        self._message = message
        self._update_text()

    def fail(self, message: str) -> None:
        """出错：状态文字转成危险色。消息本身已含原因，这里不再重复。"""
        self._finish()
        self._error = True
        self._apply_colors()
        self._message = message
        self._update_text()

    def _apply_colors(self) -> None:
        color = theme.colors()["error"] if self._error else theme.colors()["fg"]
        self.text.configure(foreground=color)

    def _update_text(self) -> None:
        if self._busy:
            text = self._message
        else:
            text = self._message or (f"共{self._count}个标题" if self._count else "")
        self.text.configure(text=text)

    def _finish(self) -> None:
        self._busy = False
        self._notify_busy()

    def _notify_busy(self) -> None:
        if self._on_busy_change is not None:
            self._on_busy_change(self._busy)
