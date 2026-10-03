"""GUI 测试共用的 Tk 根窗口。

同一进程里反复销毁/重建根窗口不稳，会把后面的用例随机 `skip` 掉。建一次用到底，
不 `destroy()`——进程退出时 Tcl 自己收尾。
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
