"""GUI 入口：建立 DPI 感知 → 建根窗口 → 同步缩放 → 绑定字体 → 铺主题 → 起 App。

## 顺序是硬约束

    enable_dpi_awareness()      # 必须在建窗口之前
      root = tk.Tk()
      metrics.sync_scaling(root) # 必须在建任何控件之前
      fonts.bind_fonts(root)    # 必须在 theme.apply() 之前
      theme.apply(root)         # 依赖上面两步的产物
      App(root)

任意一步提前或跳过，后面会**静默**出错：

* DPI 感知没设 → Tk 8.6 在系统缩放之上再乘一次进程缩放，125% 的屏上界面变 156%。
* `sync_scaling()` 晚于建控件 → 已建的控件按旧 scaling 定位，窗口一大就错位。
* `bind_fonts()` 晚于 `theme.apply()` → 样式拿到未解析的字体名，由 Tk 静默回退，
  界面上看不出「等宽没等宽」。
* `sync_scaling()` 必须在 `tk.Tk()` **之后**：`winfo_fpixels("1i")` 要有真实屏幕
  才能量到 DPI。

## 无显示环境

`tk.Tk()` 在无显示的 Linux 上抛 `TclError`。命令行只想要 CLI 行为时不该因为
「恰好装了这个包」就报一个栈回溯，所以这里给一句人话。
"""

from __future__ import annotations

import sys
import tkinter as tk
from tkinter import ttk

from . import dpi, fonts, metrics, theme
from .app import App

#: 退出码：环境跑不起来
EXIT_NO_DISPLAY = 2


def main(argv: list[str] | None = None) -> int:
    """GUI 入口。返回进程退出码。"""
    del argv  # 界面没有位置参数/开关，全走设置文件

    awareness = dpi.enable_dpi_awareness()

    try:
        root = tk.Tk()
    except tk.TclError as exc:
        print(
            f"无法创建图形界面（{exc}）。\n"
            "无显示环境下请改用命令行：simple-ebook-converter --help",
            file=sys.stderr,
        )
        return EXIT_NO_DISPLAY

    try:
        metrics.sync_scaling(root, awareness)
        metrics.capture_scaling(root)
        fonts.bind_fonts(root)
        style = theme.apply(root)
    except tk.TclError as exc:
        root.destroy()
        print(f"初始化界面失败：{exc}", file=sys.stderr)
        return EXIT_NO_DISPLAY

    del style  # 样式已挂到 root 上，不必留在本地
    App(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
