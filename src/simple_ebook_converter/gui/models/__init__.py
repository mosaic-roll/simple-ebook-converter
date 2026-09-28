"""与 Tk 无关的模型 / 草稿逻辑。

放在这里的东西**不依赖 tkinter**，因此可以直接单测（不用起窗口）。控件负责显示
与取值，状态规则集中在这里，避免同一套「脏 / 已自动填 / 三态」散落在各页签里。
"""

from __future__ import annotations

__all__ = ["autofill", "levels_state", "table_model"]
