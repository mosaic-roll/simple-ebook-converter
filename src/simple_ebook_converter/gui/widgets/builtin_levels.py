"""内置层级编辑区：每个层级一行「启用勾选 + 正则框 + 恢复默认」。

三态（未动过 / 显式关闭 / 显式正则）的规则在 `models.levels_state`，这里只负责把它
接到控件上。原来这三行的 grid 写在识别页里，抽成组件后识别页不再有手写布局。

`levels` / `touched` 对外公开：识别页要拿它们算 `IdentifyValues.levels`，测试也直接
引用（`tab._levels[...]`）。
"""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable, Iterable

import tkinter.ttk as ttk

from ..metrics import s
from ..models import levels_state
from .button_row import ButtonRow
from .regex_entry import regex_entry

#: 一行里的「恢复默认」按钮文字
RESTORE_LABEL = "恢复默认"


class BuiltinLevelsEditor(ttk.Frame):
    """内置层级（卷 / 章 / 节）的三行编辑器。"""

    def __init__(
        self,
        master: tk.Misc,
        *,
        titles: Iterable[tuple[str, str]],
        default_of: Callable[[str], object],
        on_change: Callable[[], None] | None = None,
        on_toggle: Callable[[], None] | None = None,
        **kwargs,
    ) -> None:
        super().__init__(master, **kwargs)
        self._default_of = default_of
        self._on_change = on_change
        #: 勾选/恢复默认时额外调用（识别页据此重算额外层级的冲突判断）
        self._on_toggle = on_toggle
        #: 选项名 → (启用变量, 正则变量)
        self.levels: dict[str, tuple[tk.BooleanVar, tk.StringVar]] = {}
        #: 选项名 → 用户动过没有（三态里的 `None` 靠它）
        self.touched: dict[str, bool] = {}

        for index, (name, label) in enumerate(titles):
            self.levels[name] = self._row(name, label, index)
            self.touched[name] = False

    # ---------- 布局 ----------

    def _row(self, name: str, label: str, row: int) -> tuple[tk.BooleanVar, tk.StringVar]:
        frame = ttk.Frame(self)
        frame.grid(row=row, column=0, sticky="ew", pady=(0, s(4)))
        self.columnconfigure(0, weight=1)
        frame.columnconfigure(1, weight=1)

        default = str(self._default_of(name))
        enabled = tk.BooleanVar(value=bool(default))
        ttk.Checkbutton(
            frame, text=label, variable=enabled, command=lambda n=name: self._toggle(n)
        ).grid(row=0, column=0, sticky="w")

        pattern = tk.StringVar(value=default)
        # **先放「恢复默认」再放正则框**：正则框 `fill=x, expand`，pack 会把空间优先
        # 给它、把后放的控件挤出可视区。按钮先占住右边，框再吃剩下的。
        btns = ButtonRow(frame)
        btns.grid(row=0, column=2, sticky="e", padx=(s(6), 0))
        btns.add_spacer_expand()
        btns.add(
            RESTORE_LABEL,
            lambda n=name, v=pattern: self.restore_default(n, v),
            width=8,
        )
        entry = regex_entry(frame, textvariable=pattern, width=40)
        entry.grid(row=0, column=1, sticky="ew", padx=(s(6), s(4)))
        pattern.trace_add("write", lambda *_, n=name: self._pattern_edited(n))
        return enabled, pattern

    # ---------- 值 ----------

    def state(self) -> dict[str, str | None]:
        """收集三态：`None`（未动过）/ `""`（显式关闭）/ 非空正则。"""
        return {
            name: levels_state.to_saved(
                enabled.get(), self.touched[name], pattern.get()
            )
            for name, (enabled, pattern) in self.levels.items()
        }

    def set_state(self, values: dict[str, str | None]) -> None:
        for name, (enabled, pattern) in self.levels.items():
            on, text, touched = levels_state.from_saved(
                values.get(name), str(self._default_of(name))
            )
            enabled.set(on)
            pattern.set(text)
            # 放在 set 之后：`pattern.set` 会触发 write trace 把 touched 置真
            self.touched[name] = touched

    # ---------- 事件 ----------

    def restore_default(self, name: str, var: tk.StringVar) -> None:
        """「恢复默认」：填回 core 缺省。"""
        var.set(str(self._default_of(name)))
        self.touched[name] = False
        self._toggle(name)

    def _pattern_edited(self, name: str) -> None:
        self.touched[name] = True
        self._notify()

    def _toggle(self, name: str) -> None:
        if self.levels[name][0].get():
            self.touched[name] = True
        if self._on_toggle is not None:
            self._on_toggle()
        self._notify()

    def _notify(self) -> None:
        if self._on_change is not None:
            self._on_change()
