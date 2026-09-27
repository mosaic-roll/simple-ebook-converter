"""状态栏：进度条 + 状态文字 + 忙时按钮禁用。

只管**显示**。后台线程要回主线程更新界面，走 `mainthread.MainThread.post()` ——
那不是本类的职责：状态栏没有任何东西是「线程相关的」，把它当线程跳板会让
「谁在碰控件」这个问题变得更难回答。

进度是**不确定态**（不确定时长的活给假百分比更糟）：用 `mode="indeterminate"` 起转、
`stop()` 收，而不是 `value` 从 0 爬到 100。
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from ..metrics import s
from ..theme import COLORS


class StatusBar(ttk.Frame):
    """底部状态栏。`set_text()` 任何时候都能用，`begin()` 之后会顺带转进度条。

    `on_busy_change(busy)` 在忙状态**每次翻转**后调用。App 用它统一刷新控件
    可用性 —— 比在 `begin/ok/fail` 的每个调用点都记得手动刷一次可靠。
    """

    def __init__(self, master: tk.Misc, *, on_busy_change=None, **kwargs) -> None:
        super().__init__(master, **kwargs)
        self._busy = False
        self._on_busy_change = on_busy_change

        self.bar = ttk.Progressbar(self, mode="determinate", length=s(160))
        self.bar.pack(side="left")
        self.text = ttk.Label(self, text="就绪", style="Muted.TLabel")
        self.text.pack(side="left", padx=(s(8), 0))
        self.detail = ttk.Label(self, text="", style="Muted.TLabel", foreground=COLORS["muted"])
        self.detail.pack(side="right")

    # ---------- 状态 ----------

    @property
    def busy(self) -> bool:
        return self._busy

    def set_text(self, message: str) -> None:
        """只改文字。空串=没话说，不是「清空成空白」。"""
        self.text.configure(text=message or "就绪")

    def set_detail(self, message: str) -> None:
        """右侧补充信息（编码、统计…），不影响主状态文字。"""
        self.detail.configure(text=message)

    def begin(self, message: str = "处理中…") -> None:
        """进入忙状态：进度条转起来，状态栏变忙。**`busy` 期间按钮应为 disabled。**"""
        self._busy = True
        self._notify_busy()
        self.bar.configure(mode="indeterminate")
        self.bar.start(12)  # ms，12~15 是「明显在动但不闪」的区间
        self.set_text(message)

    def ok(self, message: str = "完成", detail: str = "") -> None:
        self._finish()
        self.set_text(message)
        self.set_detail(detail)

    def fail(self, message: str, detail: str = "") -> None:
        """出错：状态栏转成错误色。消息本身已含原因，这里不再重复。"""
        self._finish()
        self.text.configure(foreground=COLORS["error"], text=message or "失败")
        self.set_detail(detail)

    def _finish(self) -> None:
        self._busy = False
        self._notify_busy()
        self.bar.stop()
        self.bar.configure(mode="determinate", value=0)
        self.text.configure(foreground="")

    def _notify_busy(self) -> None:
        if self._on_busy_change is not None:
            self._on_busy_change(self._busy)
