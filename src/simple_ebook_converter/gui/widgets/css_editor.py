"""排版页签的 CSS 编辑区：模式选择 + 路径 + 内联文本。

**模式是单一枚举**（`none` / `append` / `override`），不是两个独立勾选框：
core 里 `css_file` 与 `css_append` **互斥**（都给上 `Config.validate()` 会抛错），
两个勾选框就能构造出「两个都勾」这种非法组合，得在界面里判、在 core 里再判一次。
一个单选组表达互斥只有一种状态。

`none` 时路径框与文本框整体禁用（`state="disabled"`），否则用户能在一堆灰控件里
填一堆不生效的值，生成后却没变化 —— 这类「改了没反应」最难排查。
"""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
import tkinter.ttk as ttk

from ..build_config_from_ui import CSS_APPEND, CSS_MODES, CSS_NONE, CSS_OVERRIDE
from ..fonts import font
from ..metrics import s
from .path_row import PathRow
from .scroll_frame import ScrollFrame

#: 模式 → (标签, 说明)
MODE_LABELS = {
    CSS_NONE: "使用内置样式",
    CSS_APPEND: "附加：内置样式之后追加",
    CSS_OVERRIDE: "替代：整份替代内置样式",
}

#: 文本框的目标物理高度（设计稿像素）。tk.Text 的 height 单位是**行**，不是像素，
#: 直接写 s(150) 会得到一个 150 行的巨框。按 8 行给，高度才接近设计稿。
TEXT_LINES = 8

#: 载入内置模板的按钮
LOAD_BUILTIN = "载入内置模板"


class CssEditor(ttk.Frame):
    """CSS 模式 + 文件路径 + 内联编辑。"""

    def __init__(
        self,
        master: tk.Misc,
        *,
        on_change: Callable[[], None] | None = None,
        **kwargs) -> None:
        super().__init__(master, **kwargs)
        self.on_change = on_change
        self._mode = tk.StringVar(value=CSS_NONE)

        self._build_modes()

        self.path_row = PathRow(
            self,
            "CSS 文件",
            kind="css",
            picker="css",
            with_clear=True,
            on_change=self._changed)
        self.path_row.pack(fill="x", pady=(s(8), 0))
        self._path = self.path_row.get

        self._build_text()
        self._apply_enabled()

    # ---------- 布局 ----------

    def _build_modes(self) -> None:
        bar = ttk.Frame(self)
        bar.pack(anchor="w")
        for mode in CSS_MODES:
            ttk.Radiobutton(
                bar,
                text=MODE_LABELS[mode],
                value=mode,
                variable=self._mode,
                command=self._on_mode).pack(side="left", padx=(0, s(12)))
        self._note = ttk.Label(bar, text="", wraplength=s(360))
        self._note.pack(side="left")

    def _build_text(self) -> None:
        bar = ttk.Frame(self)
        bar.pack(fill="x", pady=(s(8), 0))
        ttk.Label(bar, text="内联编辑").pack(side="left")
        ttk.Button(bar, text=LOAD_BUILTIN, command=self.load_builtin).pack(
            side="left", padx=(s(8), 0)
        )
        self.hint = ttk.Label(bar, text="")
        self.hint.pack(side="left", padx=(s(8), 0))

        # ScrollFrame 里放 Text：CSS 普遍长于屏幕高度
        wrap = ScrollFrame(self)
        wrap.pack(fill="both", expand=True, pady=(s(4), 0))
        self.text = tk.Text(
            wrap.inner,
            height=TEXT_LINES,
            wrap="none",  # CSS 不该按宽度折行：折出来的行复制出去是坏的
            font=font("mono"),
            undo=True,
            exportselection=True)
        self.text.pack(side="left", fill="both", expand=True)
        hbar = ttk.Scrollbar(wrap, orient="horizontal", command=self.text.xview)
        self.text.configure(xscrollcommand=hbar.set)
        hbar.pack(fill="x")
        self.text.bind("<FocusOut>", lambda _e: self._changed(), add="+")
        wrap.retag_all()  # Text 是后建的，得补 bindtag 才能滚

    # ---------- 模式 ----------

    def _on_mode(self) -> None:
        self._apply_enabled()
        self._changed()

    def _apply_enabled(self) -> None:
        mode = self._mode.get()
        # none 模式下路径与文本都失效：留着可编辑只会让人填了不生效的值
        editable = mode != CSS_NONE
        state = "normal" if editable else "disabled"
        self.path_row.entry.configure(state=state)
        for widget in self.path_row.winfo_children():
            if isinstance(widget, ttk.Button):
                widget.configure(state=state)
        self.text.configure(state=state)
        self._note.configure(text=MODE_LABELS[mode] if mode != CSS_NONE else "")

    # ---------- 值 ----------

    def get(self) -> tuple[str, str, str]:
        """`(css_mode, css_path, css_text)`。路径与文本都只在该模式下有意义。"""
        return self._mode.get(), self._path(), self.text.get("1.0", "end-1c")

    def set(self, mode: str, path: str = "", text: str = "") -> None:
        self._mode.set(mode if mode in CSS_MODES else CSS_NONE)
        # **顺序要紧**：先按新模式放开控件，再写值。禁用的 ttk.Entry / tk.Text 会
        # 静默忽略 insert —— 写完再放开的话，值进不去而且一点提示都没有。
        self._apply_enabled()
        self.path_row.set(path)
        self._set_text(text)

    def _set_text(self, text: str) -> None:
        """写文本框，必要时临时放开。

        `state="disabled"` 的 `tk.Text` 同样忽略 `insert`/`delete`，而
        `load_builtin()` 在 `none` 模式下也该能填内容（用户就是先看模板再决定模式）。
        """
        was = str(self.text.cget("state"))
        if was == "disabled":
            self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        if text:
            self.text.insert("1.0", text)
        if was == "disabled":
            self.text.configure(state=was)

    def load_builtin(self) -> str:
        """把内置 CSS 模板填进编辑框，作进一步改的起点。

        用 core 的 `builtin_css()` 而不是打包资源里的静态副本：改了内置模板之后
        这里自动跟着变，不会出现「导出的模板和实际生成用的不是一份」。
        """
        from ...core.builder import builtin_css
        from ...core.config import DEFAULTS

        self._set_text(builtin_css(DEFAULTS))
        self.hint.configure(text=f"已载入内置模板；{LOAD_BUILTIN} 不会自动切换模式")
        self._changed()
        return self.get()[2]

    def _changed(self) -> None:
        if self.on_change is not None:
            self.on_change()
