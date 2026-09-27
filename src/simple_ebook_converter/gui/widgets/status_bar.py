"""状态行：一行文字 + 「在忙吗」。

放在顶部动作条的右侧。**没有进度条**：任务时长不定，假进度比没有更糟；也**没有
单独的 detail 行**（编码/书名/标题数分别属于状态文字、目录面板，不该挤在一个角落里
重复）。本类只回答两件事：现在忙不忙、上一步的结果是什么。

忙状态翻转时回调 `on_busy_change(busy)`，让 App 统一刷新控件可用性 —— 比在每个
调用点都记得手动刷一次可靠。

后台线程回主线程不在这里 —— 那是 `mainthread.MainThread` 的事。
"""

from __future__ import annotations

import tkinter as tk

import tkinter.ttk as ttk


class StatusBar(ttk.Frame):
    """顶部右侧的一行状态文字。"""

    def __init__(self, master: tk.Misc, *, on_busy_change=None, **kwargs) -> None:
        super().__init__(master, **kwargs)
        self._busy = False
        self._on_busy_change = on_busy_change
        self.text = ttk.Label(self, text="", anchor="e")
        self.text.pack(side="right", fill="x", expand=True)

    # ---------- 状态 ----------

    @property
    def busy(self) -> bool:
        return self._busy

    def set_text(self, message: str) -> None:
        self.text.configure(text=message)

    def begin(self, message: str = "处理中…") -> None:
        """进入忙状态。"""
        self._busy = True
        self._notify_busy()
        self.set_text(message)

    def ok(self, message: str = "") -> None:
        self._finish()
        self.text.configure()
        self.set_text(message)

    def fail(self, message: str) -> None:
        """出错：状态文字转成危险色。消息本身已含原因，这里不再重复。"""
        self._finish()
        self.text.configure(foreground="#c62828")
        self.set_text(message)

    def _finish(self) -> None:
        self._busy = False
        self._notify_busy()

    def _notify_busy(self) -> None:
        if self._on_busy_change is not None:
            self._on_busy_change(self._busy)
