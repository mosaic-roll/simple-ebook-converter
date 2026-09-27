"""进程 DPI 意识。**必须在 `tk.Tk()` 之前调用。**

Tk 8.6 只认进程级的 DPI 意识，不处理 `WM_DPICHANGED`（per-monitor），所以这里能做
的只有一件事：让 Windows 停止对整个进程做位图拉伸，把缩放责任交回给应用，由应用
按真实 DPI 自己画。

本模块刻意不 import tkinter：调用点在 `import tkinter` 之前，这是唯一的硬顺序约束。
"""

from __future__ import annotations

import sys

#: Windows 上 per-monitor-v2 的 DPI 上下文句柄（DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2）
_PER_MONITOR_AWARE_V2 = -4
_PER_MONITOR_AWARE = -3

#: 返回值：进程实际生效的 DPI 意识。`unaware` 表示设失败，调用方应退到
#: 「按 Tk 自己报的 scaling 画」的保守路径。
NA = "n/a"
UNAWARE = "unaware"


def enable_dpi_awareness() -> str:
    """把进程设成 per-monitor DPI 意识，返回生效的模式名。

    必须在 `tk.Tk()` **之前**调：Tk 初始化时会读一次当前进程的 DPI 意识并缓存，
    之后再设就对已建的窗口无效了。

    非 Windows 平台直接返回 `"n/a"` —— X11/macOS 的缩放模型与这里无关。
    """
    if sys.platform != "win32":
        return NA

    import ctypes

    # 不显式声明 argtypes/restypes 时，ctypes 会把 -4 这样的整数按 C 的 int
    # 传进一个按指针接收的函数，句柄被截断成 32 位 → 静默失败。所以必须声明。
    try:
        set_context = ctypes.windll.user32.SetProcessDpiAwarenessContext
    except AttributeError:  # Windows 8.1 及更早，没有这个 API
        return _set_context_fallback()

    set_context.argtypes = [ctypes.c_void_p]
    set_context.restype = ctypes.c_bool

    for context in (_PER_MONITOR_AWARE_V2, _PER_MONITOR_AWARE):
        if set_context(ctypes.c_void_p(context)):
            return "per-monitor-v2" if context == _PER_MONITOR_AWARE_V2 else "per-monitor"
    return _set_context_fallback()


def _set_context_fallback() -> str:
    """Win 8.1 及更早：`SetProcessDpiAwareness` 只认枚举值，context 那个 API 没有。"""
    import ctypes

    # DPI_AWARENESS: 0=unaware 1=system 2=per-monitor
    for value, name in ((2, "per-monitor"), (1, "system")):
        try:
            if ctypes.windll.shcore.SetProcessDpiAwareness(value) == 0:
                return name
        except (AttributeError, OSError):
            break
    return UNAWARE
