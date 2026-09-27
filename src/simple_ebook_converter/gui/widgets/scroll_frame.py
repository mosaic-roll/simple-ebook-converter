"""竖向滚动容器：Canvas + 内层 Frame + 竖滚动条。

**Tk 的事件不向父控件冒泡。** 所以只给 Canvas 绑滚轮是没用的：子控件铺满视口时，
指针落在子控件上，事件根本到不了 Canvas。正确做法是给**所有后代**挂一个自定义
bindtag，在那个 tag 上绑处理器（`bindtags()` 里自定义 tag 排在 class 绑定之后、
toplevel 之前，能收到所有后代的事件）。

动态新增控件之后必须调 `retag_all()` 补上新控件，否则新增的行滚不动。
"""

from __future__ import annotations

import tkinter as tk
import ttkbootstrap as ttk

from ..metrics import s

#: 自定义 bindtag 名。所有 ScrollFrame 共用同一个（class binding 是全局的），
#: 处理逻辑与具体实例无关，所以不需要按实例区分。
BINDTAG = "SecScrollFrame"

#: 视口的最小高度（设计稿像素）。内容装得下时不出滚动条；装不下时至少这么高，
#: 不会把控件压扁。
MIN_HEIGHT = 420

#: X11 的 Shift 修饰键掩码。Windows/macOS 上用不到（它们走 `<MouseWheel>`）
_SHIFT_MASK = 1 << 0


class ScrollFrame(ttk.Frame):
    """一个能竖向滚动的内容容器。内容放在 `.inner` 上。"""

    def __init__(self, master: tk.Misc, **kwargs) -> None:
        super().__init__(master, **kwargs)
        self.canvas = tk.Canvas(
            self,
            highlightthickness=0,
            borderwidth=0,
            background="#ffffff",
            height=s(MIN_HEIGHT),
        )
        self.vbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self._on_yscroll)
        self.inner = ttk.Frame(self.canvas)

        # 内层跟随视口宽度（内容只跟着宽走，高度由内容决定）
        self._win = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.inner.bind("<Configure>", self._on_inner_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)

        self.canvas.pack(side="left", fill="both", expand=True)
        self._enable_wheel()

    # ---------- 布局 ----------

    def _on_inner_configure(self, _event: tk.Event) -> None:
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_configure(self, event: tk.Event) -> None:
        self.canvas.itemconfigure(self._win, width=event.width)

    def _on_yscroll(self, first: str, last: str) -> None:
        """滚动条跟随 canvas；内容装得下时把滚动条收起来，把宽度让给内容。"""
        # 阈值 0.999 而不是 1.0：浮点比较下 `last` 常常是 0.99999…，
        # 用 `>= 1.0` 判断会让滚动条永远收不掉。
        if float(first) <= 0.0 and float(last) >= 0.999:
            self.vbar.pack_forget()
        else:
            self.vbar.pack(side="right", fill="y")
        self.vbar.set(first, last)

    # ---------- 滚轮 ----------

    def _enable_wheel(self) -> None:
        """在自定义 bindtag 上绑滚轮，挂在所有后代（含自己）上。"""
        self.bind_class(BINDTAG, "<MouseWheel>", self._wheel_vertical)
        self.bind_class(BINDTAG, "<Button-4>", self._wheel_vertical)
        self.bind_class(BINDTAG, "<Button-5>", self._wheel_vertical)
        self.retag_all()

    def retag_all(self) -> None:
        """重新给所有后代挂上滚轮 bindtag。**动态增删控件后必须调。**

        递归而不是只扫一层：设计上以为「Canvas + vbar + inner + inner 的直接子控件」
        就是全部，但 `inner` 里的每个子控件自己还可能有子控件（`PathRow` 里就有
        按钮组）。只扫两层的话，第四层往下的控件滚不动。
        """
        for widget in self.winfo_children():
            self._retag_descendants(widget)
        self._retag_descendants(self)

    def _retag_descendants(self, widget: tk.Misc) -> None:
        """给 `widget` 及其所有后代挂 bindtag。"""
        if BINDTAG not in widget.bindtags():
            widget.bindtags((*widget.bindtags(), BINDTAG))
        for child in widget.winfo_children():
            self._retag_descendants(child)

    def _wheel_vertical(self, event: tk.Event) -> str:
        """竖向滚动一格；已经在顶/底了就**不**吃掉事件，交给上层（如滚动表格）。

        返回 `"break"` 表示已处理。不 break 的话事件会继续往外传，在嵌套的
        ScrollFrame（或 Treeview）里会滚两下。
        """
        if _is_shift(event):
            return None  # Shift+滚轮是「横向」，归焦点所在的控件管
        delta = _wheel_delta(event)
        if not delta:
            return None
        first, last = (float(x) for x in self.canvas.yview())
        if delta < 0 and first <= 0.0:
            return None
        if delta > 0 and last >= 0.999:
            return None
        self.canvas.yview_scroll(delta, "units")
        return "break"


# ---------- 滚轮事件的符号归一 ----------


def _wheel_delta(event: tk.Event) -> int:
    """把三种滚轮事件归一成「往上 = +1，往下 = -1」。

    * Windows / macOS：`<MouseWheel>` 才有 `event.delta`，120 是一格；
    * X11：`<Button-4>` / `<Button-5>`，用 `event.num`，**没有** `delta` 属性 ——
      直接读 `event.delta` 会 AttributeError。
    """
    num = getattr(event, "num", None)
    if num == 4:
        return 1
    if num == 5:
        return -1
    delta = getattr(event, "delta", 0)
    if not delta:
        return 0
    steps = int(delta) // 120
    if steps == 0:
        steps = 1 if delta > 0 else -1
    return 1 if steps > 0 else -1


def _is_shift(event: tk.Event) -> bool:
    """Shift 是否按下。X11 上 `<Button-4>` 同样会匹配带 Shift 的事件，修饰键只在
    `state` 里，所以只能在一个处理器里判，不能靠分别绑两个序列。"""
    return bool(int(getattr(event, "state", 0)) & _SHIFT_MASK)
