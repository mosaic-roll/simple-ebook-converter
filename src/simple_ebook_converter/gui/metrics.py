"""像素 → 真实像素的换算，以及 `tk scaling` 与 Treeview 行高。

Tk 没有内置的「按 DPI 缩放几何」机制：`grid` / `pack` / `canvas` / `column(width=…)`
收到的都是**屏幕像素**，不会跟着 `tk scaling` 变（`tk scaling` 只影响**字体磅值**
与少量以点为单位的量）。所以所有硬编码像素都必须显式过 `s()`。

启动顺序是硬要求（见 `__main__.py`）：

    sync_scaling(root, awareness)   # 先按真实 DPI 把 tk scaling 摆好（管字体）
    capture_scaling(root)           # 再把换算系数定死给 s()（管几何）
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from .dpi import NA, UNAWARE

#: 设计稿里所有像素值的基准 DPI
BASE_DPI = 96.0

#: 换算系数，由 `capture_scaling()` 定死。未初始化时为 1.0（先当 96 DPI 用）
_SCALE = 1.0

#: `capture_scaling()` 记下的真实 DPI，供状态栏显示与排查
_REAL_DPI = BASE_DPI

#: 没有 `tk scaling` 可调时的保守下限：Tk 默认 scaling 是 72/72=1（1 磅 = 1 像素）
_MIN_SCALING = 1.0


def s(px: int | float) -> int:
    """设计稿里的像素 → 当前屏幕上的真实像素。

    刻意**不**缩放 0：调用方想表达「宽 0 / 隐藏某列」时要写字面量 `0`，`s(0)`
    会因 `max(1, …)` 兜底变成 1px，露出一条谁也看不懂的细缝（见 `TocPanel`）。
    """
    return max(1, round(px * _SCALE))


def scale() -> float:
    """当前换算系数。测试与状态栏用。"""
    return _SCALE


def real_dpi() -> float:
    """`capture_scaling()` 记下的真实 DPI。"""
    return _REAL_DPI


def sync_scaling(root: tk.Misc, awareness: str) -> float:
    """按真实 DPI 设 `tk scaling`，返回设完的值。**必须在建任何控件之前调。**

    `tk scaling` 的含义是「1 磅等于多少像素」。Tk 的初值来自系统（Windows 上通常
    已经是 96 DPI 对应的 1.333），但它**不知道**我们已经在进程级关掉了位图缩放，
    所以这里要按真实 DPI 重新摆一次，字体才会跟着显示器缩放走。

    DPI 的来源按可信度排序：

    1. Windows 且进程已 per-monitor aware → `root.winfo_fpixels("1i")`；
    2. 否则退回 Tk 自己的 `tk scaling`（Tk 已经按系统设过了，别动它）。

    设成 DPI/72 而不是 DPI/96：`tk scaling` 的单位是**磅**（1/72 英寸），不是像素。
    """
    if awareness in (NA, UNAWARE):
        # 没拿到 DPI 意识：不动 Tk 的 scaling，让 Tk 保持它自己按系统算出来的值。
        # 在这种模式下 Windows 还在给我们做位图拉伸，界面不会糊。
        return float(root.tk.call("tk", "scaling"))

    try:
        dpi = float(root.winfo_fpixels("1i"))
    except tk.TclError:
        return float(root.tk.call("tk", "scaling"))
    if dpi <= 0:
        return float(root.tk.call("tk", "scaling"))

    value = max(_MIN_SCALING, dpi / 72.0)
    root.tk.call("tk", "scaling", value)
    return value


def capture_scaling(root: tk.Misc) -> float:
    """把 `s()` 的换算系数定死，返回系数。**在 `sync_scaling()` 之后调一次。**

    Tk 8.6 不会处理 `WM_DPICHANGED`，所以窗口拖到另一块缩放比例不同的屏幕时
    既不会重算字体、也不会重算这里存下的系数 —— 字体和尺寸在启动时就定死了。
    这不是 bug 修复不完的妥协，是库级限制（见设计稿 §13.2）。
    """
    global _SCALE, _REAL_DPI

    try:
        dpi = float(root.winfo_fpixels("1i"))
    except tk.TclError:
        dpi = 0.0
    if dpi <= 0:
        # 拿不到真实 DPI：退回 `tk scaling` 推出的等效 DPI。
        dpi = float(root.tk.call("tk", "scaling")) * 72.0

    _REAL_DPI = dpi
    _SCALE = max(0.1, dpi / BASE_DPI)
    return _SCALE


def set_row_height(name: str, px: int) -> None:
    """给某个 Treeview style 设行高（**必须显式设**，否则 150% 下字大了行没变高、
    文字上下被裁）。`name` 是自定义 style 名，别改全局 `Treeview`。

    这里用**朴素**的 `tkinter.ttk.Style` 而不是 `ttkbootstrap.Style`：
    `ttkbootstrap.Style(root)` 的第一个参数是**主题名**，传 root 会当成主题名去查、
    直接抛 TclError（而且 `ttkbootstrap.Style()` 不带主题会**重置**成默认主题）。
    行高只是往 Tcl 的 style 数据库里写一个值，两者共用同一个数据库。
    """
    ttk.Style().configure(name, rowheight=s(px))
