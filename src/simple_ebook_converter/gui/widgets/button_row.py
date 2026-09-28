"""工具条辅助：一行横排的按钮组。

`toc_panel.py` 和 `replacement_editor.py` 都用「`ttk.Frame` + 按钮 `pack(side=left)`」
的行布局。抽成轻量容器后两处都不再重复。
"""

from __future__ import annotations

import tkinter as tk
import tkinter.ttk as ttk

from ..metrics import s


class ButtonRow(ttk.Frame):
    """工具条内的一行按钮。按钮通过 ``add()`` 或 ``add_many()`` 逐个/批量加入。

    **不自带 pack/grid** —— 调用方负责布局（`pack` 或 `grid`），
    以兼容 `PathRow` 这类用 grid 的容器。
    """

    def __init__(self, parent: tk.Misc, **kwargs) -> None:
        super().__init__(parent, **kwargs)

    def add(self, text: str, command=None, **kw) -> ttk.Button:
        btn = ttk.Button(self, text=text, command=command, **kw)
        btn.pack(side="left", padx=(0, s(4)))
        return btn

    def add_many(self, items: list[tuple[str, callable | None]]) -> list[ttk.Button]:
        return [self.add(text, cmd) for text, cmd in items]

    def add_spacer(self, padx: int = s(8)) -> None:
        ttk.Label(self, text="").pack(side="left", padx=padx)

    def add_label(self, text: str) -> ttk.Label:
        lbl = ttk.Label(self, text=text)
        lbl.pack(side="left", padx=(s(4), 0))
        return lbl
