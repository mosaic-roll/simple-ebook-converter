"""「排版」页签：缩进、行高、段间距、对齐、正文字体、CSS。

缺省值一律从 `core.options.option_default()` 取，**不手抄** `Config` 的字段默认值
——手抄的那份迟早和 core 脱节，用户改了 CLI 行为却发现界面默认值还是旧的。
"""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
import ttkbootstrap as ttk

from ...core.config import ALIGN_CHOICES
from ...core.options import OPTIONS, option_default
from ..build_config_from_ui import TypographyValues
from ..metrics import s
from ..widgets.css_editor import CssEditor
from ..widgets.path_row import PathRow
from ..widgets.scroll_frame import ScrollFrame

#: 对齐方式的中文标签
ALIGN_LABELS = {"left": "左对齐", "center": "居中", "right": "右对齐"}
ALIGN_CHOICE_LABELS = tuple(ALIGN_LABELS[a] for a in ALIGN_CHOICES)
_BY_LABEL = {label: value for value, label in ALIGN_LABELS.items()}

#: 缩进字数范围
INDENT_RANGE = (0, 8)


class TypographyTab(ttk.Frame):
    """排版设置。"""

    def __init__(
        self,
        master: tk.Misc,
        *,
        on_change: Callable[[], None] | None = None,
        **kwargs,
    ) -> None:
        super().__init__(master, **kwargs)
        self.on_change = on_change

        wrap = ScrollFrame(self)
        wrap.pack(fill="both", expand=True)
        body = ttk.Frame(wrap.inner, padding=(s(12), s(12)))
        body.pack(fill="both", expand=True)

        grid = ttk.Frame(body)
        grid.pack(fill="x")
        self._indent = tk.IntVar(value=option_default(_option("indent")))
        self._line_height = tk.StringVar(value=option_default(_option("line_height")))
        self._para_spacing = tk.StringVar(value=option_default(_option("para_spacing")))
        self._volume_align = tk.StringVar(
            value=ALIGN_LABELS[option_default(_option("volume_align"))]
        )
        self._chapter_align = tk.StringVar(
            value=ALIGN_LABELS[option_default(_option("chapter_align"))]
        )

        self._int_row(grid, "段落缩进", self._indent, 1, INDENT_RANGE, "0=不缩进")
        self._text_row(grid, "行高", self._line_height, 2, "1.5 / 150% 皆可")
        self._text_row(grid, "段间距", self._para_spacing, 3, "1em / 12px 皆可")
        self._choice_row(grid, "卷对齐", self._volume_align, 4)
        self._choice_row(grid, "章对齐", self._chapter_align, 5)

        self.font_row = PathRow(
            body, "正文字体", kind="font", picker="font", on_change=self._changed
        )
        self.font_row.pack(fill="x", pady=(s(10), 0))
        ttk.Label(
            body,
            text="字体只从文件选取：ttf / otf / woff / woff2，会嵌入书里。",
            bootstyle="secondary",
        ).pack(anchor="w")

        css = ttk.LabelFrame(body, text="样式表", padding=(s(8), s(6)))
        css.pack(fill="both", expand=True, pady=(s(12), 0))
        self.css = CssEditor(css, on_change=self._changed)
        self.css.pack(fill="both", expand=True)

        wrap.retag_all()

    # ---------- 值 ----------

    def get(self) -> TypographyValues:
        mode, css_path, css_text = self.css.get()
        return TypographyValues(
            indent=_clamp(self._indent.get(), *INDENT_RANGE),
            # 行高/段间距是 CSS 长度值，**按字符串收**：1.5 / 150% / 1.5em 都合法
            line_height=self._line_height.get().strip(),
            para_spacing=self._para_spacing.get().strip(),
            volume_align=_align_value(self._volume_align.get()),
            chapter_align=_align_value(self._chapter_align.get()),
            font=self.font_row.get(),
            css_mode=mode,
            css_path=css_path,
            css_text=css_text,
        )

    def set(self, values: TypographyValues) -> None:
        self._indent.set(values.indent)
        self._line_height.set(values.line_height)
        self._para_spacing.set(values.para_spacing)
        self._volume_align.set(ALIGN_LABELS.get(values.volume_align, values.volume_align))
        self._chapter_align.set(ALIGN_LABELS.get(values.chapter_align, values.chapter_align))
        self.font_row.set(values.font)
        self.css.set(values.css_mode, values.css_path, values.css_text)

    # ---------- 内部 ----------

    def _int_row(
        self, parent, label: str, var: tk.IntVar, row: int, span, hint: str
    ) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=(0, s(4)))
        ttk.Spinbox(
            parent, from_=span[0], to=span[1], width=5, textvariable=var, command=self._changed
        ).grid(row=row, column=1, sticky="w", padx=(s(6), 0), pady=(0, s(4)))
        var.trace_add("write", lambda *_: self._changed())
        ttk.Label(parent, text=hint, bootstyle="secondary").grid(
            row=row, column=2, sticky="w", padx=(s(6), 0)
        )
        parent.columnconfigure(1, weight=1)

    def _text_row(self, parent, label: str, var: tk.StringVar, row: int, hint: str) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=(0, s(4)))
        ttk.Entry(parent, textvariable=var, width=20).grid(
            row=row, column=1, sticky="ew", padx=(s(6), s(6)), pady=(0, s(4))
        )
        var.trace_add("write", lambda *_: self._changed())
        ttk.Label(parent, text=hint, bootstyle="secondary").grid(
            row=row, column=2, sticky="w"
        )
        parent.columnconfigure(1, weight=1)

    def _choice_row(self, parent, label: str, var: tk.StringVar, row: int) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=(0, s(4)))
        combo = ttk.Combobox(
            parent, textvariable=var, values=ALIGN_CHOICE_LABELS, state="readonly", width=12
        )
        combo.grid(row=row, column=1, sticky="w", padx=(s(6), 0), pady=(0, s(4)))
        combo.bind("<<ComboboxSelected>>", lambda _e: self._changed())

    def _changed(self) -> None:
        if self.on_change is not None:
            self.on_change()


def _option(name: str):
    """按名字取 `core.options.OPTIONS` 里的一条。core 的查找函数是下划线私有的。"""
    return next(opt for opt in OPTIONS if opt.name == name)


def _align_value(label: str) -> str:
    """中文标签 → core 的取值；不认识就原样返回（让 core 去报错）。"""
    return _BY_LABEL.get(label, label)


def _clamp(value, low: int, high: int) -> int:
    try:
        return max(low, min(high, int(value)))
    except (TypeError, ValueError):
        return low
