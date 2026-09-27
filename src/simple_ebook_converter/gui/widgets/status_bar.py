"""状态栏：进度条 + 状态文字 + 忙时按钮禁用。

**Tk 不是线程安全的**：后台线程不能碰任何控件，只能 `after()` 回主线程。本类只提供
`begin/ok/fail` 三个入口，各自内部保证「状态更新」和「控件更新」在主线程上发生。

进度是**不确定态**（不确定时长的活给假百分比更糟）：用 `mode="indeterminate"` 起转、
`stop()` 收，而不是 `value` 从 0 爬到 100。
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from ..metrics import s
from ..theme import COLORS


class StatusBar(ttk.Frame):
    """底部状态栏。`set_text()` 任何时候都能用，`begin()` 之后会顺带转进度条。"""

    def __init__(self, master: tk.Misc, **kwargs) -> None:
        super().__init__(master, **kwargs)
        self._busy = False

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
        self.bar.stop()
        self.bar.configure(mode="determinate", value=0)
        self.text.configure(foreground="")

    # ---------- 线程回调 ----------

    def on_main(self, callback, delay_ms: int = 0) -> str:
        """后台线程回到主线程的**唯一**入口。

        Tk 不是线程安全的：后台线程碰控件会随机卡死或直接崩。收口到这一个方法，
        比让每处自己 `root.after(0, ...)` 更难写错。
        """
        root = self.winfo_toplevel()
        return root.after(delay_ms, callback) if delay_ms > 0 else root.after_idle(callback)
