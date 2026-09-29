"""规则 Tab：内置层级正则 + 额外层级行。

内置层级只是预填项：整条正则可编辑，恢复默认时回填 `DEFAULTS` 里的原值。

额外层级行没有选中态：添加就是往末尾加一行，删除就是去掉最后一行，因此
永远不会出现行号空洞，也就不需要重排。默认 hN 见 `EXTRA_LEVEL_DEFAULTS`。
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
BUILTIN_ROWS = ("卷", "章", "节", "字数上限", "无标题章节")

#: 额外层级的默认 hN：第 1 行 h5、第 2 行 h6，之后新增的行都 h6
EXTRA_LEVEL_DEFAULTS = ("h5", "h6")

#: 「额外规则」组内：0 是组标题，1 是按钮条，额外层级行从 2 开始
_FIRST_EXTRA_ROW = 2


def _default_level(index: int) -> str:
    """第 `index` 行（0 起）该预填的 hN。"""
    if index < len(EXTRA_LEVEL_DEFAULTS):
        return EXTRA_LEVEL_DEFAULTS[index]
    return EXTRA_LEVEL_DEFAULTS[-1]


def build(parent: ctk.CTkFrame, ctx: GuiContext) -> dict:
    """构建规则 Tab，返回控件引用。"""
    parent.grid_columnconfigure(0, weight=1)
    font = ctx.fonts.base

    b = make_group(parent, "基础规则", 0, ctx)
    rule_entries: dict[str, ctk.CTkEntry] = {}

    def restore_default(label: str) -> None:
        # TODO: 接 core 后回填 core.config.option_default(<该行的键>) 而不是清空
        entry = rule_entries.get(label)
        if entry is not None:
            entry.delete(0, "end")

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

    a = make_group(parent, "额外规则", 1, ctx)
    extra_rows: list[dict[str, ctk.CTkBaseClass]] = []

    def add_extra_rule() -> None:
        i = len(extra_rows)
        extra_rows.append(
            _extra_level_row(a, _FIRST_EXTRA_ROW + i, ctx, _default_level(i))
        )
        del_btn.configure(state="normal")

    def remove_extra_rule() -> None:
        if not extra_rows:
            return
        extra_rows.pop()["frame"].destroy()
        del_btn.configure(state="normal" if extra_rows else "disabled")

    # 按钮放在组标题下面而不是末尾：行往下长，末尾的按钮会被顶得从鼠标底下滑走
    btns = ctk.CTkFrame(a, fg_color="transparent")
    btns.grid(row=1, column=0, columnspan=4, sticky="w", padx=GROUP_PADX)
    ctk.CTkButton(
        btns,
        text="＋ 添加",
        width=BTN_W_XL,
        font=font,
        command=add_extra_rule,
    ).pack(side="left", padx=BTN_GAP)
    del_btn = ctk.CTkButton(
        btns,
        text="－ 删除",
        width=BTN_W_XL,
        font=font,
        command=remove_extra_rule,
    )
    del_btn.pack(side="left", padx=BTN_GAP)

    add_extra_rule()
    add_extra_rule()

    return {
        "rule_entries": rule_entries,
        "extra_rows": extra_rows,
    }


def _extra_level_row(
    parent: ctk.CTkBaseClass, r: int, ctx: GuiContext, level: str
) -> dict[str, ctk.CTkBaseClass]:
    """一行额外层级：级别选项 + class 输入 + 正则输入。

    级别与 class 可以留空：级别决定成 hN，class 决定挂哪个 CSS 选择器。
    """
    row = ctk.CTkFrame(parent, fg_color="transparent")
    row.grid(row=r, column=0, columnspan=4, sticky="ew", padx=GROUP_PADX, pady=4)
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
