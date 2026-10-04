"""替换 Tab：有序规则卡片列表。

替换规则**只作用于标题**。每张卡片是一条规则：启用开关、阶段、pattern、replace，
卡片顺序即执行顺序（↑ ↓ 调序，✕ 删除）。
"""

from __future__ import annotations

import tkinter as tk
import traceback
from collections.abc import Callable
from pathlib import Path
from typing import Any

import customtkinter as ctk

from ...core.replace import Rule, check_stage, rules_from_file, rules_to_json
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
    # 存引用而非值快照：app 层后续 append 的回调必须被 _fire 感知到，
    # 因为回调链是在 build() 之后才由 app 注册的。
    _triggers = ctx.rules_changed if on_rules_changed is None else [on_rules_changed]
    # 规则字段快照：用于在 _fire 里做「规则是否真的变了」的比较。
    # 基于 collect_rules 的输出：空 pattern 的卡片不计入，
    # 增删空卡不会误触发刷新。
    _last_snapshot: tuple = ()

    def _fire() -> None:
        nonlocal _last_snapshot
        snap = rules_snapshot(rule_cards)
        if snap == _last_snapshot:
            return
        _last_snapshot = snap
        for cb in _triggers:
            try:
                cb()
            except Exception:  # noqa: BLE001
                traceback.print_exc()

    def add_rule() -> None:
        """用户点「添加规则」按钮：追加一张空卡片。"""
        _add_card()

    # 供 import_rules_json() 复用：不依赖 build 闭包直接建卡片。
    # `fire=False` 用于批量导入——逐卡触发会让 N 条规则刷 N 次，攒到最后统一 fire 一次。
    def _add_card(
        pattern: str = "",
        replace: str = "",
        stage: str = "原文",
        enabled: bool = True,
        fire: bool = True,
    ) -> dict[str, Any]:
        card = _make_card(
            holder, ctx, on_move=_move_rule, on_remove=_remove_rule, on_change=_fire
        )
        if pattern:
            card["pattern_entry"].insert(0, pattern)
        if replace:
            card["replace_entry"].insert(0, replace)
        card["stage_menu"].set(stage)
        card["enabled_var"].set(enabled)
        rule_cards.append(card)
        _relayout(rule_cards)
        if fire:
            _fire()
        return card

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
        "add_card": _add_card,
        "fire": _fire,
    }


def collect_rules(cards: list[dict[str, Any]]) -> list[Rule]:
    """卡片列表 → core 的 `Rule` 列表。

    **空 pattern 的卡片照样返回**：那张卡是用户自己留的半成品，存进配置里下次打开还在，
    丢掉等于替用户删了想写的东西。空规则不会真的生效——`core.replacers_by_stage()`
    在那边把空 pattern 一起跳掉，配置文件被手改也拦得住。

    阶段标签「原文/HTML」由 `check_stage()` 自动转成 raw/html，未知值抛 ValueError
    （只可能来自手改的控件值，选项菜单本身给不了非法值）。
    """
    return [
        Rule(
            pattern=card["pattern_entry"].get(),
            replace=card["replace_entry"].get(),
            stage=check_stage(card["stage_menu"].get()),
            enabled=bool(card["enabled_var"].get()),
        )
        for card in cards
    ]


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
    # 勾选/取消都要刷新：enabled 进了 _snapshot 的比较，规则非空时勾选状态一变，
    # 预览就得按新的启用集合重算。漏了这个回调，预览会一直停在改动前的样子。
    ctk.CTkCheckBox(
        head,
        text="启用",
        variable=enabled_var,
        font=font,
        command=lambda: on_change(),
    ).grid(row=0, column=0, sticky="w")

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
    #
    # 使用 _is_focused / _activate_placeholder() 是因为 CTkEntry 没有公开 API 来
    # 「手动激活 placeholder」。这两个是 CTkEntry 实例上真实存在的方法/属性（可
    # 通过 hasattr(type(e), '_activate_placeholder') 验证），但属于内部实现细节，
    # 前缀下划线只是约定而非 Python 强制限制。若 customtkinter 升级时重命名或移
    # 除，这里会静默失效——届时需要回到该类源码确认新路径。
    #
    # CTkEntry 内部 _entry_focus_out 依赖 _is_focused 判断是否激活 placeholder，
    # 但我们的 FocusOut 绑定比内部绑定先运行，_is_focused 此时仍为 True，导致占
    # 位符在字段为空时无法恢复。修复：临时设 _is_focused=False 再调 _activate_placeholder()，
    # 走与内部相同的激活路径。
    def _on_pattern_focusout(_event=None) -> None:
        on_change()
        if pattern_entry._entry.get() == "":
            pattern_entry._is_focused = False
            pattern_entry._activate_placeholder()

    def _on_replace_focusout(_event=None) -> None:
        on_change()
        if replace_entry._entry.get() == "":
            replace_entry._is_focused = False
            replace_entry._activate_placeholder()

    pattern_entry._entry.bind("<FocusOut>", _on_pattern_focusout)  # type: ignore[attr-defined]
    replace_entry._entry.bind("<FocusOut>", _on_replace_focusout)  # type: ignore[attr-defined]

    ref.update(
        frame=card,
        enabled_var=enabled_var,
        pattern_entry=pattern_entry,
        replace_entry=replace_entry,
        stage_menu=stage_menu,
    )
    return ref


def rules_snapshot(cards: list[dict[str, Any]]) -> tuple:
    """卡片列表 → 可比较的规则快照，供 `_fire()` 判断「规则是否真的变了」。

    四个字段齐了才触发刷新：pattern / replace / stage / **enabled**。少一个都会漏刷新
    ——`enabled` 曾经就漏了，勾选框没接回调，预览一直停在改动前的样子。

    空 pattern 的卡片不计入（与 `collect_rules()` 不同，那条为了存档保留空卡片）：
    空规则不生效，改它不该触发预览重算。但它一旦填上 pattern 就立刻计入并触发。
    """
    return tuple(
        (r.pattern, r.replace, r.stage, r.enabled)
        for r in collect_rules(cards)
        if r.pattern
    )


def _relayout(cards: list[dict[str, Any]]) -> None:
    """按列表顺序重排卡片行号（调序、删除后都要重来一遍）。"""
    for i, card in enumerate(cards):
        card["frame"].grid(row=i, column=0, sticky="ew", pady=CARD_PADY)


def export_rules_json(cards: list[dict[str, Any]], path: Path) -> None:
    """把当前规则卡片序列化为 JSON 文件（与 core.replace.rules_to_json 同格式）。"""
    rules = collect_rules(cards)
    Path(path).write_text(rules_to_json(rules), encoding="utf-8")


def import_rules_json(
    cards: list[dict[str, Any]],
    path: Path,
    add_card=None,
    fire=None,
) -> None:
    """从 JSON 文件加载替换规则并填充到卡片。

    读不了或格式非法抛 `ValueError`。填充细节见 `fill_rules()`。
    """

    fill_rules(cards, rules_from_file(path), add_card, fire)


def fill_rules(
    cards: list[dict[str, Any]],
    rules: list[Rule],
    add_card=None,
    fire=None,
) -> None:
    """用 `rules` 重建卡片：清空现有卡片后按顺序创建。

    `add_card` 由 app 层传入（build() 中定义的 _add_card 闭包），为空时仅清空。
    传了 `fire`（app 层传 build 交回的 `_fire`）时走批量模式：逐卡不触发，重建完
    统一调一次 `fire()`，避免 N 条规则触发 N 次预览刷新；不传则退回逐卡触发。
    """
    # 清空现有卡片
    for card in list(cards):
        card["frame"].destroy()
    cards.clear()
    if add_card is None:
        # 防御性分支：app 侧永远从 build() 的返回值里传 add_card，正常不会走到。
        return
    immediate = fire is None  # 非批量模式：逐卡触发；批量模式攒到最后统一 fire()
    # 按规则重建卡片；没有规则时保留一张空卡方便用户立即开始编辑
    if not rules:
        add_card(fire=immediate)
    else:
        for r in rules:
            add_card(
                pattern=r.pattern,
                replace=r.replace,
                stage=r.stage_label,
                enabled=r.enabled,
                fire=immediate,
            )
    if fire is not None:
        fire()
