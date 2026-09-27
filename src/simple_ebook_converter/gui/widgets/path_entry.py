"""路径输入框：`ttk.Entry` 子类 + 即时校验 + 红色/橙色提示。

校验分两级，**分工明确**：

* **即时提示**（本类）：填完失焦后立刻给反馈，一行提示文字（红=错误、橙=警告）。
  这是「我刚才填的东西对不对」，错了用户还能改。
* **权威判定**：`core.options._path()` —— 它在 `build_config()` 里跑，路径不存在
  会抛 `ValueError`。生成按钮走的是那条路。

所以这里的检查**不替代** core，只是提前告诉用户。**橙色警告不拦生成**：输出目录
不存在是可以的，生成时会建目录（`pipeline.write_epub` 里的 `mkdir(parents=True)`）。

校验态用提示文字的颜色表示（sv_ttk 不暴露输入框边框色），颜色取自 `theme.colors()`，
亮暗主题各一套。
"""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from pathlib import Path

import tkinter.ttk as ttk

from .. import theme


#: 校验结论
OK, ERROR, WARN = "ok", "error", "warn"


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
        self._state = OK

        self.hint = ttk.Label(master, text="", wraplength=0)
        self.bind("<KeyRelease>", self._on_key_release, add="+")
        self.bind("<FocusOut>", self._on_focus_out, add="+")
        theme.on_colors_changed(self, self._apply_colors)

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
        self._apply_colors()
        self.hint.configure(text=message)

    def _apply_colors(self) -> None:
        # sv_ttk 不给输入框边框色，只能用提示文字的颜色表达校验态
        palette = theme.colors()
        color = {"error": palette["error"], "warn": palette["warn"]}.get(
            self._state, palette["fg"]
        )
        self.hint.configure(foreground=color)

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
