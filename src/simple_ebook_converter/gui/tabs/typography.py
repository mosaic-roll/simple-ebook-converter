"""「排版」页签：缩进、行高、段间距、对齐、正文字体、CSS。

缺省值一律从 `core.options.option_default()` 取，**不手抄** `Config` 的字段默认值
——手抄的那份迟早和 core 脱节，用户改了 CLI 行为却发现界面默认值还是旧的。

布局用声明式 `Form`（见 `widgets/form.py`）：这一页有什么、怎么分组，看 `SPEC` 即可。
CSS 编辑器是不规则的组合块，不进 SPEC，作为具名控件直接摆在下方。
"""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable

import tkinter.ttk as ttk

from ...core.config import ALIGN_CHOICES
from ...core.options import OPTIONS, option_default
from ..build_config_from_ui import TypographyValues
from ..metrics import s
from ..widgets.css_editor import CssEditor
from ..widgets.form import Choice, Field, Form, Path, Section, Spin, Text
from ..widgets.scroll_frame import ScrollFrame

#: 对齐方式的中文标签
ALIGN_LABELS = {"left": "左对齐", "center": "居中", "right": "右对齐"}
ALIGN_CHOICE_LABELS = tuple(ALIGN_LABELS[a] for a in ALIGN_CHOICES)

#: 缩进字数范围
INDENT_RANGE = (0, 8)

#: 正文字体说明
FONT_HELP = "字体只从文件选取：ttf / otf / woff / woff2，会嵌入书里。"


def _default(name: str):
    """core 里该选项的缺省值。"""
    return option_default(next(opt for opt in OPTIONS if opt.name == name))


#: 排版页的布局：**这一页长什么样，看这张表就够了。**
SPEC: tuple[Section, ...] = (
    Section(
        "段落",
        (
            Field(
                "indent",
                "段落缩进",
                Spin(
                    INDENT_RANGE[0],
                    INDENT_RANGE[1],
                    default=_default("indent"),
                    help="0=不缩进",
                ),
            ),
            Field(
                "line_height",
                "行高",
                Text(default=_default("line_height"), help="1.5 / 150% 皆可"),
            ),
            Field(
                "para_spacing",
                "段间距",
                Text(default=_default("para_spacing"), help="1em / 12px 皆可"),
            ),
        ),
    ),
    Section(
        "对齐",
        (
            Field(
                "volume_align",
                "卷对齐",
                Choice(
                    ALIGN_CHOICES,
                    default=_default("volume_align"),
                    labels=ALIGN_CHOICE_LABELS,
                ),
            ),
            Field(
                "chapter_align",
                "章对齐",
                Choice(
                    ALIGN_CHOICES,
                    default=_default("chapter_align"),
                    labels=ALIGN_CHOICE_LABELS,
                ),
            ),
        ),
    ),
    Section(
        "正文字体",
        (Field("font", "正文字体", Path(kind="font", help=FONT_HELP)),),
    ),
)


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

        self.form = Form(
            wrap.inner,
            SPEC,
            on_change=lambda _name: self._changed(),
            padding=(s(12), s(12)),
        )
        self.form.pack(fill="x")

        css = ttk.LabelFrame(wrap.inner, text="样式表", padding=(s(8), s(6)))
        css.pack(fill="both", expand=True, padx=s(12), pady=(s(10), s(12)))
        self.css = CssEditor(css, on_change=self._changed)
        self.css.pack(fill="both", expand=True)

        wrap.retag_all()

    # ---------- 值 ----------

    def get(self) -> TypographyValues:
        values = self.form.values()
        # 行高/段间距是 CSS 长度值，**按字符串收**：1.5 / 150% / 1.5em 都合法。
        # 两头的空白是手误，收掉。
        values["line_height"] = values["line_height"].strip()
        values["para_spacing"] = values["para_spacing"].strip()
        mode, css_path, css_text = self.css.get()
        return TypographyValues(
            **values, css_mode=mode, css_path=css_path, css_text=css_text
        )

    def set(self, values: TypographyValues) -> None:
        self.form.set_values(
            {
                "indent": values.indent,
                "line_height": values.line_height,
                "para_spacing": values.para_spacing,
                "volume_align": values.volume_align,
                "chapter_align": values.chapter_align,
                "font": values.font,
            }
        )
        self.css.set(values.css_mode, values.css_path, values.css_text)

    # ---------- 内部 ----------

    def _changed(self) -> None:
        if self.on_change is not None:
            self.on_change()
