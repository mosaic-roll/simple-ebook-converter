"""`tests/gui` 的共享 fixture。

`tk_root` 是**会话级**的：Tk 根窗口建一次就够，每个测试在其上建自己的控件、测完
销毁。建根窗口是这套里最慢的一步（初始化字体、量 DPI），按测试重建会让这批测试慢
十几倍。

**没有 display 就整个文件 skip**。Tk 在无显示的 Linux 上 `tk.Tk()` 抛 `TclError`，
那是环境问题不是代码问题，不该让 CI 报红。跳过用 `pytest.skip`（不是 xfail），
并在原因里说清是缺 display。
"""

from __future__ import annotations

import importlib.util
import tkinter as tk
from collections.abc import Iterator

import pytest

#: sv_ttk 是 GUI 的可选依赖（`[gui]` extra）。没装时：
#: - 纯数据测试（test_app / test_options_coverage）照常跑；
#: - 需要真窗口的模块自己在文件顶部 `pytest.importorskip("sv_ttk")` 跳过。
_HAS_GUI_DEPS = importlib.util.find_spec("sv_ttk") is not None

if _HAS_GUI_DEPS:
    from simple_ebook_converter.gui import dpi, fonts, metrics, theme


@pytest.fixture(scope="session")
def tk_root() -> Iterator[tk.Tk]:
    """建好并配好主题的根窗口。跳过的前提是这台机器有 display。"""
    if not _HAS_GUI_DEPS:
        pytest.skip("未安装 sv_ttk（图形界面可选依赖），跳过需要窗口的测试")
    # DPI 感知必须在 `tk.Tk()` **之前**设：Tk 在建根窗口时读一次系统缩放并按它
    # 缓存字体度量，之后再设就只影响之后新建的窗口，根窗口上的字号还是按旧缩放
    # 算的。顺序和 `__main__.main()` 保持一致 —— 测试里换一套顺序，等于测的是
    # 一套正式程序不走的初始化路径。
    try:
        awareness = dpi.enable_dpi_awareness()
        root = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"没有可用的 display，跳过 GUI 测试：{exc}")

    root.withdraw()  # 别在跑测试时弹出一个真窗口
    try:
        metrics.sync_scaling(root, awareness)
        metrics.capture_scaling(root)
        fonts.bind_fonts(root)
        theme.apply(root)
        yield root
    finally:
        root.destroy()
