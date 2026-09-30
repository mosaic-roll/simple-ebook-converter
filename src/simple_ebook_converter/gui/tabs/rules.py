"""规则 Tab：内置层级正则 + 额外层级行。

内置层级只是预填项：整条正则可编辑，恢复默认时回填 `DEFAULTS` 里的原值。

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
from ..widgets import make_field_btn, make_group

#: 预置行标签 → DEFAULTS 的键；TODO: 接 core 后由 core.config.DEFAULTS 补全
BUILTIN_ROWS = ("卷", "章", "排除", "字数上限", "无标题章节")

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

    def restore_default(label: str) -> None:
        # TODO: 接 core 后回填 core.config.option_default(<该行的键>) 而不是清空
        entry = rule_entries.get(label)
        if entry is not None:
            entry.delete(0, "end")

    # row=0 组标题，字段从 row=1 起
    for i, label in enumerate(BUILTIN_ROWS, start=1):
        rule_entries[label] = make_field_btn(
            b,
            i,
            label,
            ctx,
            command=lambda lbl=label: restore_default(lbl),
            btn_text="恢复默认",
            btn_width=BTN_W_L,
        )

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

    def add_extra_rule() -> None:
        i = len(extra_rows)
        item = _extra_level_row(holder, _default_level(i), ctx)
        extra_rows.append(item)
        item["frame"].grid(row=i, column=0, sticky="ew", pady=4)
        del_btn.configure(state="normal")

    def remove_extra_rule() -> None:
        if not extra_rows:
            return
        extra_rows.pop()["frame"].destroy()
        del_btn.configure(state="normal" if extra_rows else "disabled")

    # row=1：按钮条，全左对齐
    btns = ctk.CTkFrame(a, fg_color="transparent")
    btns.grid(row=1, column=0, columnspan=4, sticky="w", padx=GROUP_PADX, pady=(0, 4))

    ctk.CTkButton(
        btns,
        text="＋ 添加",
        width=BTN_W_XL,
        font=font,
        command=add_extra_rule,
    ).pack(side="left", padx=(0, BTN_GAP))

    del_btn = ctk.CTkButton(
        btns,
        text="－ 删除",
        width=BTN_W_XL,
        font=font,
        command=remove_extra_rule,
    )
    del_btn.pack(side="left")

    add_extra_rule()
    add_extra_rule()

    return {
        "rule_entries": rule_entries,
        "extra_rows": extra_rows,
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

    regex = ctk.CTkEntry(row, placeholder_text="正则", font=font)
    regex.grid(row=0, column=2, sticky="ew")

    return {"frame": row, "level": menu, "class": cls, "regex": regex}
