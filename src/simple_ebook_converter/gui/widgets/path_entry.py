"""路径输入框：`ttk.Entry` 子类 + 即时校验 + 红/黄框。

校验分两级，**分工明确**：

* **即时提示**（本类）：填完失焦后立刻给反馈，红框/黄框 + 一行提示文字。这是
  「我刚才填的东西对不对」，错了用户还能改。
* **权威判定**：`core.options._path()` —— 它在 `build_config()` 里跑，路径不存在
  会抛 `ValueError`。生成按钮走的是那条路。

所以这里的检查**不替代** core，只是提前告诉用户。**黄框不拦生成**：输出目录
不存在是可以的，生成时会建目录（`pipeline.write_epub` 里的 `mkdir(parents=True)`）。

红框靠 `Error.TEntry` / `Warn.TEntry` 的 `bordercolor`，**只有 `clam` 生效**（§4.2）。
`theme.apply()` 之后用 `theme.border_color_supported()` 探一次；不支持时退化成
只有提示文字。
"""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from pathlib import Path
from tkinter import ttk

from ..theme import COLORS, border_color_supported

#: 校验结论
OK, ERROR, WARN = "ok", "error", "warn"

#: 提示文字的 style 名（写在 `theme.apply()` 里）
_MUTED = "Muted.TLabel"
_ERROR_STYLE = "Error.TEntry"
_WARN_STYLE = "Warn.TEntry"


class PathEntry(ttk.Entry):
    """一个会自己校验的路径输入框。`kind` 决定校验规则。"""

    def __init__(
        self,
        master: tk.Misc,
        *,
        kind: str = "output",
        on_change: Callable[[], None] | None = None,
        on_valid: Callable[[Path | None], None] | None = None,
        **kwargs,
    ) -> None:
        super().__init__(master, **kwargs)
        self.kind = kind
        self._on_change = on_change
        self._on_valid = on_valid
        self._valid: Path | None = None
        self._has_border = True
        self._state = OK

        self.hint = ttk.Label(master, text="", style=_MUTED, wraplength=0)
        self.bind("<KeyRelease>", self._on_key_release, add="+")
        self.bind("<FocusOut>", self._on_focus_out, add="+")

    # ---------- 校验 ----------

    def get_path(self) -> Path | None:
        """当前内容 → `Path`，空串返回 `None`（视同未填，不校验）。"""
        text = self.get().strip()
        return Path(text) if text else None

    def is_valid(self) -> bool:
        return self.get_path() is not None and self._state != ERROR

    def set_state(self, state: str, message: str = "") -> None:
        """设置校验态。`state` 是 `OK` / `ERROR` / `WARN`。"""
        self._state = state
        if self._has_border and state == ERROR:
            self.configure(style=_ERROR_STYLE)
        elif self._has_border and state == WARN:
            self.configure(style=_WARN_STYLE)
        else:
            self.configure(style="")
        self.hint.configure(
            text=message,
            style=_MUTED,
            foreground=COLORS["error"] if state == ERROR else COLORS["warn"],
        )

    def detect_border_support(self, root: tk.Misc) -> bool:
        """探测当前主题认不认 `bordercolor`；不认就退化成只有提示文字。"""
        self._has_border = border_color_supported(root)
        return self._has_border

    def clear_message(self) -> None:
        self.hint.configure(text="")

    # ---------- 事件 ----------

    def _on_key_release(self, event: tk.Event) -> None:
        # 提示文字立刻清掉，但**不重算校验**：边打字边红框会一直闪，失焦才算。
        if self.hint.cget("text"):
            self.clear_message()
        if self._on_change is not None:
            self._on_change()

    def _on_focus_out(self, _event: tk.Event) -> None:
        self.validate()

    def validate(self) -> Path | None:
        """按 `kind` 校验当前内容，更新提示与 `on_valid`，返回通过校验的路径。"""
        path = self.get_path()
        state, message = _check(self.kind, path)
        self.set_state(state, message)
        self._valid = path if state != ERROR else None
        if self._on_valid is not None:
            self._on_valid(self._valid)
        return self._valid


def _check(kind: str, path: Path | None) -> tuple[str, str]:
    """`(状态, 提示文字)`。空路径一律 `OK`（视同未填，交给生成时再拦）。"""
    if path is None:
        return OK, ""
    if kind == "input":
        if not path.is_file():
            return ERROR, f"文件不存在：{path}"
        return OK, ""
    if kind == "output":
        if path.is_dir():
            return ERROR, f"这是一个目录，请填文件名：{path}"
        parent = path.parent
        if not parent.is_dir():
            # 黄框而不是红框：生成时会把目录建出来，不该拦
            return WARN, f"目录不存在，生成时会自动创建：{parent}"
        return OK, ""
    if kind == "file":
        # 封面、字体这类：不存在就是错，必须先准备好
        return (OK, "") if path.is_file() else (ERROR, f"文件不存在：{path}")
    return OK, ""
