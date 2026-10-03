"""GUI 测试共用的 Tk 根窗口。

同一进程里反复销毁/重建 Tk 根窗口不稳：销毁后紧接着新建有时抛 `TclError`，
表现为后面用到根窗口的用例随机 `skip`。建一次就用到底，不 `destroy()`——
进程退出时 Tcl 自己收尾，不泄漏。
"""

import tkinter as tk

import pytest


@pytest.fixture(scope="session")
def tk_root():
    """全 GUI 测试共用的根窗口；无图形环境就跳过整个会话。"""
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("没有图形环境")
    root.withdraw()
    return root
