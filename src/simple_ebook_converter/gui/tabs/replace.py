"""替换 Tab：有序规则卡片列表。

替换规则**只作用于标题**。每张卡片是一条规则：启用开关、阶段、pattern、replace，
卡片顺序即执行顺序（↑ ↓ 调序，✕ 删除）。
"""

from __future__ import annotations

import tkinter as tk
import traceback
from collections.abc import Callable
from typing import Any

import customtkinter as ctk

from ...core.replace import Rule, check_stage
from ..constants import (
    BTN_GAP,
    BTN_W_M,
    BTN_W_XL,
    BTN_W_XS,
    FIELD_PADX,
    GROUP_PADX,
    LABEL_PADX,
    OPTION_W_M,
    ROW_PADY,
    STAGES,
)
from ..context import GuiContext

CARD_PADY = (0, 6)

_STAGE_DEFAULT = STAGES[0]


def build(
    parent: ctk.CTkFrame,
    ctx: GuiContext,
    *,
    on_rules_changed: Callable[[], None] | None = None,
) -> dict:
    """构建替换 Tab，返回控件引用。

    `rule_cards` 是活列表：增删卡片时它就地变更，app 层拿到的就是同一个对象。
    变动时触发 `on_rules_changed`（若提供），app 侧用它刷新目录预览。
    """
    font = ctx.fonts.base
    parent.grid_columnconfigure(0, weight=1)
    parent.grid_rowconfigure(1, weight=1)

    top = ctk.CTkFrame(parent, fg_color="transparent")
    top.grid(row=0, column=0, sticky="ew", padx=GROUP_PADX, pady=(10, 4))
    top.grid_columnconfigure(0, weight=1)

    holder = ctk.CTkScrollableFrame(parent, fg_color="transparent")
    holder.grid(row=1, column=0, sticky="nsew", padx=GROUP_PADX, pady=(0, 10))
    holder.grid_columnconfigure(0, weight=1)

    rule_cards: list[dict[str, Any]] = []
    # 存引用而非值快照：app 层后续 append 的回调必须被 _fire 感知到（§4.1 根因）
    _triggers = ctx._on_rules_changed if on_rules_changed is None else [on_rules_changed]

    def _fire() -> None:
        for cb in _triggers:
            try:
                cb()
            except Exception:  # noqa: BLE001
                traceback.print_exc()

    def add_rule() -> None:
        card = _make_card(
            holder, ctx, on_move=_move_rule, on_remove=_remove_rule, on_change=_fire
        )
        rule_cards.append(card)
        _relayout(rule_cards)
        _fire()

    def _move_rule(card: dict[str, Any], delta: int) -> None:
        if card not in rule_cards:
            return
        i = rule_cards.index(card)
        j = i + delta
        if 0 <= j < len(rule_cards):
            rule_cards[i], rule_cards[j] = rule_cards[j], rule_cards[i]
            _relayout(rule_cards)
            _fire()

    def _remove_rule(card: dict[str, Any]) -> None:
        if card in rule_cards:
            rule_cards.remove(card)
            card["frame"].destroy()
            _relayout(rule_cards)
            _fire()

    add_rule()

    ctk.CTkButton(
        top,
        text="添加规则",
        width=BTN_W_XL,
        font=font,
        command=add_rule,
    ).grid(row=0, column=0, sticky="w")

    right_top = ctk.CTkFrame(top, fg_color="transparent")
    right_top.grid(row=0, column=1, sticky="e")
    ctk.CTkButton(
        right_top,
        text="导入",
        width=BTN_W_M,
        font=font,
        command=ctx.cb("import_rules"),
    ).pack(side="left", padx=(0, BTN_GAP))
    ctk.CTkButton(
        right_top,
        text="导出",
        width=BTN_W_M,
        font=font,
        command=ctx.cb("export_rules"),
    ).pack(side="left")

    return {
        "rule_cards": rule_cards,
        "add_rule": add_rule,
    }


def collect_rules(cards: list[dict[str, Any]]) -> list[Rule]:
    """卡片列表 → core 的 `Rule` 列表。

    保留 `enabled` 状态：core 的 `replacers_by_stage()` 会自动跳过禁用的规则，
    与 CLI 行为一致（禁用规则仍在列表里但不下发）。阶段标签「原文/HTML」由
    `check_stage()` 自动转成 raw/html，未知值抛 ValueError。
    """
    rules: list[Rule] = []
    for card in cards:
        pattern = card["pattern_entry"].get()
        if not pattern:
            continue
        rules.append(
            Rule(
                pattern=pattern,
                replace=card["replace_entry"].get(),
                stage=check_stage(card["stage_menu"].get()),
                enabled=bool(card["enabled_var"].get()),
            )
        )
    return rules


def _make_card(
    holder: ctk.CTkScrollableFrame,
    ctx: GuiContext,
    on_move: Any,
    on_remove: Any,
    on_change: Callable[[], None] | None = None,
) -> dict[str, Any]:
    """一张规则卡片。返回各控件引用，供 `collect_rules()` 读值。"""
    font = ctx.fonts.base
    card = ctk.CTkFrame(holder, border_width=1, corner_radius=4)
    card.grid_columnconfigure(1, weight=1)

    head = ctk.CTkFrame(card, fg_color="transparent")
    head.grid(row=0, column=0, columnspan=2, sticky="ew", padx=GROUP_PADX, pady=(8, 2))
    head.grid_columnconfigure(0, weight=1)

    enabled_var = tk.BooleanVar(master=card, value=True)
    ctk.CTkCheckBox(head, text="启用", variable=enabled_var, font=font).grid(
        row=0, column=0, sticky="w"
    )

    right = ctk.CTkFrame(head, fg_color="transparent")
    right.grid(row=0, column=1, sticky="e")

    stage_menu = ctk.CTkOptionMenu(
        right,
        values=STAGES,
        width=OPTION_W_M,
        anchor="center",
        font=font,
        dropdown_font=font,
        command=lambda _: on_change(),
    )
    stage_menu.set(_STAGE_DEFAULT)
    stage_menu.pack(side="left", padx=(0, 6))

    ref: dict[str, Any] = {}
    for text, delta in (("↑", -1), ("↓", +1)):
        ctk.CTkButton(
            right,
            text=text,
            width=BTN_W_XS,
            font=font,
            command=lambda d=delta: on_move(ref, d),
        ).pack(side="left", padx=(0, 2))
    ctk.CTkButton(
        right,
        text="✕",
        width=BTN_W_XS,
        font=font,
        command=lambda: on_remove(ref),
    ).pack(side="left")

    ctk.CTkLabel(card, text="正则", anchor="w", font=font).grid(
        row=1, column=0, padx=LABEL_PADX, pady=ROW_PADY, sticky="w"
    )
    pattern_entry = ctk.CTkEntry(
        card,
        placeholder_text=r"如 ^#+\s* 或 (第.{1,10}章)\s*",
        font=font,
    )
    pattern_entry.grid(row=1, column=1, padx=FIELD_PADX, pady=ROW_PADY, sticky="ew")

    ctk.CTkLabel(card, text="替换为", anchor="w", font=font).grid(
        row=2, column=0, padx=LABEL_PADX, pady=ROW_PADY, sticky="w"
    )
    replace_entry = ctk.CTkEntry(
        card,
        placeholder_text=r"留空即删除匹配内容；可用 \1 引用分组",
        font=font,
    )
    replace_entry.grid(row=2, column=1, padx=FIELD_PADX, pady=ROW_PADY, sticky="ew")

    # 失焦时刷新预览：用户编辑完规则、移开焦点后应用。
    pattern_entry._entry.bind("<FocusOut>", lambda _: on_change())  # type: ignore[attr-defined]
    replace_entry._entry.bind("<FocusOut>", lambda _: on_change())  # type: ignore[attr-defined]

    ref.update(
        frame=card,
        enabled_var=enabled_var,
        pattern_entry=pattern_entry,
        replace_entry=replace_entry,
        stage_menu=stage_menu,
    )
    return ref


def _relayout(cards: list[dict[str, Any]]) -> None:
    """按列表顺序重排卡片行号（调序、删除后都要重来一遍）。"""
    for i, card in enumerate(cards):
        card["frame"].grid(row=i, column=0, sticky="ew", pady=CARD_PADY)
