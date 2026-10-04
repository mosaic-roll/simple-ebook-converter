"""无状态 UI 工厂：表单行、分组框、下拉框。

这些函数只管把控件摆出来并返回引用，不记任何状态、不做校验、不碰业务。
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

import customtkinter as ctk

from .constants import (
    BTN_W_S,
    FIELD_PADX,
    GROUP_PADX,
    GROUP_PADY,
    GROUP_TITLE_PADY,
    LABEL_PADX,
    ROW_PADY,
)
from .context import GuiContext


def make_group(
    parent: ctk.CTkBaseClass, title: str, row: int, ctx: GuiContext
) -> ctk.CTkFrame:
    """分组框。内部 4 列：0/1 左半区，2/3 右半区。"""
    frame = ctk.CTkFrame(parent, border_width=1, corner_radius=4)
    frame.grid(row=row, column=0, sticky="ew", padx=GROUP_PADX, pady=GROUP_PADY)
    frame.grid_columnconfigure(0, weight=0)
    frame.grid_columnconfigure(1, weight=1)
    frame.grid_columnconfigure(2, weight=0)
    frame.grid_columnconfigure(3, weight=1)
    ctk.CTkLabel(
        frame,
        text=title,
        font=ctx.fonts.bold,
        text_color=("gray30", "gray70"),
    ).grid(
        row=0,
        column=0,
        columnspan=4,
        sticky="w",
        padx=GROUP_PADX,
        pady=GROUP_TITLE_PADY,
    )
    return frame


def _bind_placeholder_restore(entry: ctk.CTkEntry) -> None:
    """给 CTkEntry 绑上 placeholder 自动恢复：清空后失去焦点时重新显示。

    直接调 tk 的 `delete` + `insert` 会绕过 CTkEntry 内部状态机，空值时
    placeholder 不会恢复；需要补调 `_activate_placeholder()`。失焦时
    `_is_focused` 仍为 True（外部绑定比内部先跑），临时设 False 再调即可走通
    内部路径。两个都是 CTkEntry 实例上的真实方法/属性，customtkinter 升级时若
    改名会静默失效——届时需回到该类源码确认新路径。
    """
    if not hasattr(type(entry), "_activate_placeholder"):
        return

    def _on_focusin(_event: Any | None = None) -> None:
        entry._is_focused = True  # type: ignore[attr-defined]

    def _on_focusout(_event: Any | None = None) -> None:
        if entry._entry.get() == "":
            entry._is_focused = False  # type: ignore[attr-defined]
            entry._activate_placeholder()  # type: ignore[attr-defined]

    entry._entry.bind("<FocusIn>", _on_focusin, add="+")  # type: ignore[attr-defined]
    entry._entry.bind("<FocusOut>", _on_focusout, add="+")  # type: ignore[attr-defined]


def make_field(
    parent: ctk.CTkBaseClass,
    r: int,
    label: str,
    ctx: GuiContext,
    placeholder: str = "",
    col: int = 0,
    span: int = 1,
) -> ctk.CTkEntry:
    """一行：标签 + 单行输入框。

    `col` 为 0 或 2（左半区 / 右半区）；`span` 是输入框横向占几列，占满整行传 3。
    """
    font = ctx.fonts.base
    ctk.CTkLabel(parent, text=label, anchor="w", font=font).grid(
        row=r, column=col, padx=LABEL_PADX, pady=ROW_PADY, sticky="w"
    )
    entry = ctk.CTkEntry(parent, placeholder_text=placeholder, font=font)
    if placeholder:
        _bind_placeholder_restore(entry)
    entry.grid(
        row=r,
        column=col + 1,
        columnspan=span,
        padx=FIELD_PADX,
        pady=ROW_PADY,
        sticky="ew",
    )
    return entry


def make_text_field(
    parent: ctk.CTkBaseClass,
    r: int,
    label: str,
    ctx: GuiContext,
    placeholder: str = "",
    col: int = 0,
    span: int = 1,
    height: int = 3,
    pady: tuple[int, int] | int = ROW_PADY,
) -> ctk.CTkTextbox:
    """一行：标签 + 多行文本框。

    `height` 是文本框占几行字高（默认 3）。`col` / `span` 同 `make_field`。
    `pady` 是上下间距，默认 `ROW_PADY`；放在组最后一行时传 `CHECK_PADY_LAST`。
    """
    font = ctx.fonts.base
    ctk.CTkLabel(parent, text=label, anchor="nw", font=font).grid(
        row=r,
        column=col,
        padx=LABEL_PADX,
        pady=pady,
        sticky="nw",
    )
    tb = ctk.CTkTextbox(
        parent,
        height=font.metrics("linespace") * height + 12,
        font=font,
        corner_radius=4,
        border_width=1,
    )
    tb.grid(
        row=r,
        column=col + 1,
        columnspan=span,
        padx=FIELD_PADX,
        pady=pady,
        sticky="nsew",
    )
    return tb


def make_field_btn(
    parent: ctk.CTkBaseClass,
    r: int,
    label: str,
    ctx: GuiContext,
    command: Callable[[], None],
    placeholder: str = "",
    extra_btns: Sequence[tuple[str, Callable[[], None]]] | None = None,
    btn_text: str = "浏览",
    btn_width: int = BTN_W_S,
) -> ctk.CTkEntry:
    """一行：标签 + 可输入路径的框 + 右侧按钮。

    `command` 是主按钮（文字 `btn_text`，默认「浏览」）的回调；`extra_btns` 是
    排在主按钮右边的 `(文字, 回调)` 列表，如 `[("查看", open_cover)]`。
    同一行所有按钮宽度都用 `btn_width`，`placeholder` 同 `make_field`。
    """
    font = ctx.fonts.base
    ctk.CTkLabel(parent, text=label, anchor="w", font=font).grid(
        row=r, column=0, padx=LABEL_PADX, pady=ROW_PADY, sticky="w"
    )
    box = ctk.CTkFrame(parent, fg_color="transparent")
    box.grid(
        row=r,
        column=1,
        columnspan=3,
        padx=FIELD_PADX,
        pady=ROW_PADY,
        sticky="ew",
    )
    entry = ctk.CTkEntry(box, font=font, placeholder_text=placeholder)
    if placeholder:
        _bind_placeholder_restore(entry)
    entry.pack(side="left", fill="x", expand=True)

    btn_box = ctk.CTkFrame(box, fg_color="transparent")
    btn_box.pack(side="right", padx=(8, 0))
    ctk.CTkButton(
        btn_box,
        text=btn_text,
        width=btn_width,
        font=font,
        command=command,
    ).pack(side="left")
    for text, cmd in extra_btns or []:
        ctk.CTkButton(
            btn_box,
            text=text,
            width=btn_width,
            font=font,
            command=cmd,
        ).pack(side="left", padx=(6, 0))
    return entry


def make_field_combo(
    parent: ctk.CTkBaseClass,
    r: int,
    label: str,
    values: Sequence[str],
    ctx: GuiContext,
    default: str | None = None,
    col: int = 0,
) -> ctk.CTkComboBox:
    """一行：标签 + 可输入的组合框。"""
    font = ctx.fonts.base
    ctk.CTkLabel(parent, text=label, anchor="w", font=font).grid(
        row=r, column=col, padx=LABEL_PADX, pady=ROW_PADY, sticky="w"
    )
    combo = ctk.CTkComboBox(
        parent,
        values=list(values),
        font=font,
        dropdown_font=font,
    )
    combo.set(default if default is not None else values[0])
    combo.grid(row=r, column=col + 1, padx=FIELD_PADX, pady=ROW_PADY, sticky="ew")
    return combo


def make_field_menu(
    parent: ctk.CTkBaseClass,
    r: int,
    label: str,
    values: Sequence[str],
    ctx: GuiContext,
    default: str | None = None,
    col: int = 0,
) -> ctk.CTkOptionMenu:
    """一行：标签 + 只能选的选项菜单。"""
    font = ctx.fonts.base
    ctk.CTkLabel(parent, text=label, anchor="w", font=font).grid(
        row=r, column=col, padx=LABEL_PADX, pady=ROW_PADY, sticky="w"
    )
    menu = ctk.CTkOptionMenu(
        parent,
        values=list(values),
        anchor="center",
        font=font,
        dropdown_font=font,
    )
    menu.set(default if default is not None else values[0])
    menu.grid(row=r, column=col + 1, padx=FIELD_PADX, pady=ROW_PADY, sticky="ew")
    return menu
