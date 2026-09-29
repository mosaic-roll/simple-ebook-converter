"""规则 Tab：内置层级正则 + 额外层级行。

内置层级只是预填项：整条正则可编辑，恢复默认时回填 `DEFAULTS` 里的原值。
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

_MIN_EXTRA_ROWS = 1


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
        extra_rows.append(_extra_level_row(a, len(extra_rows) + 1, ctx))
        _relayout_extra_rows(a, extra_rows)

    def remove_extra_rule() -> None:
        # TODO: 改成按选中行删除；现在没有选中态，只能去最后一行
        if len(extra_rows) <= _MIN_EXTRA_ROWS:
            return
        extra_rows.pop().destroy()
        _relayout_extra_rows(a, extra_rows)

    add_extra_rule()
    add_extra_rule()

    btns = ctk.CTkFrame(a, fg_color="transparent")
    btns.grid(row=99, column=0, columnspan=4, pady=(4, 10))
    ctk.CTkButton(
        btns,
        text="＋ 添加",
        width=BTN_W_XL,
        font=font,
        command=add_extra_rule,
    ).pack(side="left", padx=BTN_GAP)
    ctk.CTkButton(
        btns,
        text="－ 删除",
        width=BTN_W_XL,
        font=font,
        command=remove_extra_rule,
    ).pack(side="left", padx=BTN_GAP)

    return {
        "rule_entries": rule_entries,
        "extra_rows": extra_rows,
    }


def _extra_level_row(
    parent: ctk.CTkBaseClass, r: int, ctx: GuiContext
) -> dict[str, ctk.CTkBaseClass]:
    """一行额外层级：级别选项 + class 输入 + 正则输入。

    级别与 class 可以留空：级别决定成 hN，class 决定挂哪个 CSS 选择器。
    """
    row = ctk.CTkFrame(parent, fg_color="transparent")
    row.grid(row=r, column=0, columnspan=4, sticky="ew", padx=GROUP_PADX, pady=4)
    row.grid_columnconfigure(2, weight=1)
    font = ctx.fonts.base

    level = ctk.CTkOptionMenu(
        row,
        values=HEADINGS,
        width=OPTION_W_S,
        anchor="center",
        font=font,
        dropdown_font=font,
    )
    level.set("h2")
    level.grid(row=0, column=0, padx=(0, 6))

    cls = ctk.CTkEntry(row, width=ENTRY_W_M, placeholder_text="class", font=font)
    cls.grid(row=0, column=1, padx=(0, 6))

    regex = ctk.CTkEntry(row, placeholder_text="正则", font=font)
    regex.grid(row=0, column=2, sticky="ew")

    return {"frame": row, "level": level, "class": cls, "regex": regex}


def _relayout_extra_rows(parent: ctk.CTkBaseClass, rows: list) -> None:
    """删除后行号会留洞，重排一遍。"""
    for i, item in enumerate(rows, start=1):
        item["frame"].grid(
            row=i, column=0, columnspan=4, sticky="ew", padx=GROUP_PADX, pady=4
        )
