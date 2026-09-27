"""`tests/gui` 的共享 fixture。

`tk_root` 是**会话级**的：Tk 根窗口建一次就够，每个测试在其上建自己的控件、测完
销毁。建根窗口是这套里最慢的一步（初始化字体、量 DPI），按测试重建会让这批测试慢
十几倍。

**没有 display 就整个文件 skip**。Tk 在无显示的 Linux 上 `tk.Tk()` 抛 `TclError`，
那是环境问题不是代码问题，不该让 CI 报红。跳过用 `pytest.skip`（不是 xfail），
并在原因里说清是缺 display。
"""

from __future__ import annotations

import tkinter as tk
from collections.abc import Iterator

import pytest

from simple_ebook_converter.gui import dpi, fonts, metrics, theme


@pytest.fixture(scope="session")
def tk_root() -> Iterator[tk.Tk]:
    """建好并配好主题的根窗口。跳过的前提是这台机器有 display。"""
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"没有可用的 display，跳过 GUI 测试：{exc}")

    root.withdraw()  # 别在跑测试时弹出一个真窗口
    try:
        awareness = dpi.enable_dpi_awareness()
        metrics.sync_scaling(root, awareness)
        metrics.capture_scaling(root)
        fonts.bind_fonts(root)
        theme.apply(root)
        yield root
    finally:
        root.destroy()
