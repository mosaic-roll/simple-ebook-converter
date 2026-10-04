"""规则 Tab：内置层级正则 + 额外层级行。

内置层级的默认值统一取自 core 的 `option_default()`（唯一真源，界面不手抄正则或字面
量）。卷/章是长正则，启动时直接填进框；字数上限/无标题章节的默认值放进 placeholder，
框留空即表示用默认值。「恢复默认」回填的也是同一处。

额外层级行没有选中态：添加就是往末尾加一行，删除就是去掉最后一行，行号不会
出现空洞，所以每次只需要摆好新行那一行。行数多了在滚动容器里上下滚。默认 hN
见 `EXTRA_LEVEL_DEFAULTS`。
"""

from __future__ import annotations

import customtkinter as ctk

from ..constants import (
    BTN_GAP,
    BTN_W_L,
    BTN_W_XL,
    ENTRY_W_M,
    GROUP_PADX,
    HEADINGS,
    OPTION_W_S,
)
from ..context import GuiContext
from ..defaults import default_text
from ..widgets import _bind_placeholder_restore, make_field_btn, make_group

#: 预置行取值方式：`PREFILL` 启动时把默认值填进框（卷/章是长正则，placeholder 放不下）；
#: `HINT` 框留空、placeholder 显示默认值，留空即表示用默认值（字数/前言的默认值很短）。
PREFILL = "prefill"
HINT = "hint"

#: 预置行：(标签, core 选项名, 取值方式)。默认值一律走 core 的 `option_default()`。
BUILTIN_ROWS: tuple[tuple[str, str, str], ...] = (
    ("卷", "volume", PREFILL),
    ("章", "chapter", PREFILL),
    ("排除", "exclude", PREFILL),  # core 默认就是空，等于不填
    ("字数上限", "max_title_len", HINT),
    ("无标题章节", "preface_title", HINT),
)

#: 额外层级的默认 hN：第 1~3 行分别预填 h4/h5/h6，之后新增的行都 h6
EXTRA_LEVEL_DEFAULTS = ("h4", "h5", "h6")


def _default_level(index: int) -> str:
    """第 `index` 行（0 起）该预填的 hN。"""
    if index < len(EXTRA_LEVEL_DEFAULTS):
        return EXTRA_LEVEL_DEFAULTS[index]
    return EXTRA_LEVEL_DEFAULTS[-1]


def build(parent: ctk.CTkFrame, ctx: GuiContext) -> dict:
    """构建规则 Tab，返回控件引用。"""
    parent.grid_columnconfigure(0, weight=1)
    font = ctx.fonts.base

    # ---- 基础规则：组标题 + 字段行 ----
    b = make_group(parent, "基础规则", 0, ctx)

    rule_entries: dict[str, ctk.CTkEntry] = {}
    row_defaults: dict[str, str] = {}

    def restore_default(label: str) -> None:
        """回填该行的 core 默认值——「恢复默认」不是清空。"""
        entry = rule_entries.get(label)
        if entry is None:
            return
        entry.delete(0, "end")
        entry.insert(0, row_defaults.get(label, ""))

    # row=0 组标题，字段从 row=1 起
    for i, (label, opt_name, mode) in enumerate(BUILTIN_ROWS, start=1):
        text = default_text(opt_name)  # 纯 core 默认值：placeholder 与「恢复默认」用
        row_defaults[label] = text
        entry = make_field_btn(
            b,
            i,
            label,
            ctx,
            command=lambda lbl=label: restore_default(lbl),
            btn_text="恢复默认",
            btn_width=BTN_W_L,
            placeholder=text if mode == HINT else "",
        )
        # 预填行（卷/章/排除）总是填：有存档用存档，否则 core 默认；
        # 提示行（字数/前言）只在有存档时才填，否则留空让 placeholder 显示默认值。
        if mode == PREFILL or opt_name in ctx.saved:
            entry.insert(0, default_text(opt_name, ctx.saved))
        rule_entries[label] = entry

    # ---- 额外规则：组标题 + 按钮条（都左对齐） + 滚动容器 ----
    a = make_group(parent, "额外规则", 1, ctx)
    a.grid_rowconfigure(2, weight=1)

    extra_rows: list[dict[str, ctk.CTkBaseClass]] = []

    # row=2：滚动容器。fg_color 透明就没有边框可画，corner_radius 得跟着给 0，
    # 否则 CTk 会为一个看不见的圆角预留一圈空白，行就跟组标题错开
    holder = ctk.CTkScrollableFrame(a, fg_color="transparent", corner_radius=0)
    # 底部要留 pady：滚动容器的画布是不透明的，没有这个间距它会正好压在组框
    # 那 1px 下边框上，把边框盖掉（左右靠 padx 让开，所以只有下边会消失）
    holder.grid(
        row=2, column=0, columnspan=4, sticky="nsew", padx=GROUP_PADX, pady=(0, 4)
    )
    holder.grid_columnconfigure(0, weight=1)

    def add_extra_row() -> dict:
        """末尾加一行额外层级，返回该行控件（启动回填存档时要逐个 `set`）。"""
        i = len(extra_rows)
        item = _extra_level_row(holder, _default_level(i), ctx)
        extra_rows.append(item)
        item["frame"].grid(row=i, column=0, sticky="ew", pady=4)
        del_btn.configure(state="normal")
        return item

    def remove_extra_rule() -> None:
        """去掉最后一行；空了就禁用按钮。"""
        if not extra_rows:
            return
        extra_rows.pop()["frame"].destroy()
        del_btn.configure(state="normal" if extra_rows else "disabled")

    def clear_extra_rows() -> None:
        """清空所有额外层级行（启动回填存档前用，避免和默认的两行叠加）。"""
        for row in extra_rows:
            row["frame"].destroy()
        extra_rows.clear()
        del_btn.configure(state="disabled")

    # row=1：按钮条，全左对齐
    btns = ctk.CTkFrame(a, fg_color="transparent")
    btns.grid(row=1, column=0, columnspan=4, sticky="w", padx=GROUP_PADX, pady=(0, 4))

    ctk.CTkButton(
        btns,
        text="＋ 添加",
        width=BTN_W_XL,
        font=font,
        command=add_extra_row,
    ).pack(side="left", padx=(0, BTN_GAP))

    del_btn = ctk.CTkButton(
        btns,
        text="－ 删除",
        width=BTN_W_XL,
        font=font,
        command=remove_extra_rule,
    )
    del_btn.pack(side="left")

    add_extra_row()
    add_extra_row()

    return {
        "rule_entries": rule_entries,
        "extra_rows": extra_rows,
        "add_extra_row": add_extra_row,
        "clear_extra_rows": clear_extra_rows,
    }


def _extra_level_row(
    parent: ctk.CTkBaseClass, level: str, ctx: GuiContext
) -> dict[str, ctk.CTkBaseClass]:
    """一行额外层级：级别选项 + class 输入 + 正则输入。

    级别与 class 可以留空：级别决定成 hN，class 决定挂哪个 CSS 选择器。
    """
    row = ctk.CTkFrame(parent, fg_color="transparent")
    row.grid_columnconfigure(2, weight=1)
    font = ctx.fonts.base

    menu = ctk.CTkOptionMenu(
        row,
        values=HEADINGS,
        width=OPTION_W_S,
        anchor="center",
        font=font,
        dropdown_font=font,
    )
    menu.set(level)
    menu.grid(row=0, column=0, padx=(0, 6))

    cls = ctk.CTkEntry(row, width=ENTRY_W_M, placeholder_text="class", font=font)
    cls.grid(row=0, column=1, padx=(0, 6))
    _bind_placeholder_restore(cls)

    regex = ctk.CTkEntry(row, placeholder_text="正则", font=font)
    regex.grid(row=0, column=2, sticky="ew")
    _bind_placeholder_restore(regex)

    return {"frame": row, "level": menu, "class": cls, "regex": regex}
