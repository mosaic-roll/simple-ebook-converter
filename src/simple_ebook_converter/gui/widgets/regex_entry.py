r"""单行正则编辑框。

**为什么必须是 `ttk.Entry` 而不是 `tk.Text`**：正则长且不可折行地看才有意义
（`\d{1,3}` 这类片段在等宽下能一眼数清位数）。`Text` 只能靠折行，折行点不可见；
`Text` + `wrap="none"` + 横向滚动条则要拖滚动条才能看到后半段。`ttk.Entry` 单行、
内容超出时**内建**横向滚动（`xview`），`Home`/`End`/`←→`/光标移动全都正常。

滚轮归属：

* **普通滚轮不在这里绑竖向滚动** —— 焦点在框里时普通滚轮应该滚外层 ScrollFrame，
  否则用户会以为页面卡住。所以本框的 `<MouseWheel>` 处理器返回 `None`，把事件
  放行给 ScrollFrame 的 bindtag。
* **`Shift+滚轮` 归这个框**，横向滚动。

前提是 ScrollFrame 的 bindtag 已挂到这个 Entry 上，否则返回 `None` 也没有接收者，
滚轮会完全没反应（见 `ScrollFrame.retag_all()`）。
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from ..fonts import MONO_FONT, font

#: X11 的 Shift 修饰键掩码
_SHIFT_MASK = 1 << 0

#: 一次滚轮横移几格。macOS 的 `event.delta` 很小（1~10），不按格数放大基本看不出动静
_UNITS_PER_WHEEL = 3


def regex_entry(master: tk.Misc, **kwargs) -> ttk.Entry:
    """造一个等宽、单行、`Shift+滚轮` 横向滚动的正则输入框。

    普通滚轮绑一个「放行」处理器：它必须**返回 `None`**（而不是 `"break"`），
    Tk 才会继续把事件交给 bindtags 里的下一个处理器，也就是 ScrollFrame。
    """
    entry = ttk.Entry(master, **kwargs)
    mono = font(MONO_FONT)
    if mono is not None:
        entry.configure(font=mono)
    entry.configure(exportselection=True)

    entry.bind("<Shift-MouseWheel>", _hscroll, add="+")
    entry.bind("<MouseWheel>", _pass_through, add="+")

    # X11：`<Button-4>` / `<Button-5>` 同样会匹配到带 Shift 的事件（修饰键在 state
    # 里，不改变事件类型），所以只能在一个处理器里判 state。
    entry.bind("<Button-4>", _hscroll_x11, add="+")
    entry.bind("<Button-5>", _hscroll_x11, add="+")
    return entry


def _hscroll(event: tk.Event) -> str:
    """`Shift+滚轮`（Windows / macOS）横向滚动。

    `event.delta` 的约定是**向上为正**，所以 delta > 0（向上）= 看更靠左的文字。
    `xview_scroll` 的正值是「视口右移」（看更靠后），方向与 `event.delta` 相反，
    所以取一次负号。
    """
    delta = int(getattr(event, "delta", 0) or 0)
    if delta:
        event.widget.xview_scroll(-_UNITS_PER_WHEEL if delta > 0 else _UNITS_PER_WHEEL, "units")
    return "break"


def _hscroll_x11(event: tk.Event) -> str | None:
    """X11 的 `Shift+Button-4/5`。不带 Shift 就返回 `None` 放行给竖向滚动。"""
    if not (int(getattr(event, "state", 0)) & _SHIFT_MASK):
        return None
    num = getattr(event, "num", None)
    if num == 4:  # 上 → 看更靠左
        event.widget.xview_scroll(-_UNITS_PER_WHEEL, "units")
    elif num == 5:  # 下 → 看更靠右
        event.widget.xview_scroll(_UNITS_PER_WHEEL, "units")
    else:
        return None
    return "break"


def _pass_through(_event: tk.Event) -> None:
    """普通滚轮：**返回 `None`**，让 ScrollFrame 的 bindtag 去处理竖向滚动。

    不能返回 `"break"`，也不能在这里自己滚 —— 那会导致焦点在正则框里时页面不动。
    """
    return None
