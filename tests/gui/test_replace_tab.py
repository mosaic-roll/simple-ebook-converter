"""替换 Tab 的纯逻辑：卡片 → `Rule`，以及「规则是否变了」的快照判断。

不起 Tk：卡片用桩对象冒充（只要有 `.get()`），够读出快照要的那四个字段。
真正建控件的路径（勾选框有没有接回调）测不到，这里只钉住它依赖的判定逻辑。
"""

from simple_ebook_converter.core.replace import (
    Rule,
    rules_from_list,
    rules_to_list,
)
from simple_ebook_converter.gui.tabs.replace import collect_rules, rules_snapshot


class _Val:
    """冒充 CTkEntry / CTkOptionMenu / BooleanVar：都只有 `.get()`。"""

    def __init__(self, value):
        self._value = value

    def get(self):
        return self._value


def _card(pattern="a", replace="b", stage="原文", enabled=True):
    return {
        "pattern_entry": _Val(pattern),
        "replace_entry": _Val(replace),
        "stage_menu": _Val(stage),
        "enabled_var": _Val(enabled),
    }


def test_collect_keeps_enabled_state():
    """enabled 要透传进 Rule：core 的 replacers_by_stage() 靠它决定跳过谁。"""
    rules = collect_rules([_card(enabled=False), _card(enabled=True)])
    assert [r.enabled for r in rules] == [False, True]


def test_collect_keeps_blank_cards():
    """空 pattern 的卡片照样收：那是用户自己的半成品，存进配置下次打开还在。

    丢掉等于替用户删了想写的东西。空规则不生效由 core 的 replacers_by_stage() 负责。
    """
    rules = collect_rules([_card(pattern=""), _card(pattern="a")])
    assert [r.pattern for r in rules] == ["", "a"]


def test_blank_rules_round_trip_through_the_config_payload():
    """存档 → 读回：空卡片还在，用户下次打开能接着改。"""
    saved = rules_to_list(collect_rules([_card(pattern=""), _card(pattern="a")]))
    assert [r["pattern"] for r in saved] == ["", "a"]
    assert [r.pattern for r in rules_from_list(saved)] == ["", "a"]


def test_snapshot_changes_when_enabled_toggles():
    """勾选/取消启用必须改变快照，否则勾选框的刷新回调不起作用。"""
    on = rules_snapshot([_card(enabled=True)])
    off = rules_snapshot([_card(enabled=False)])
    assert on != off


def test_snapshot_ignores_blank_cards():
    """空规则不生效，改它不该触发预览重算——但填上 pattern 就要触发。"""
    blank = rules_snapshot([_card(pattern="")])
    assert blank == ()
    # 只改 replace 字段：卡片还是空的，快照不变
    assert rules_snapshot([_card(pattern="", replace="写了一半")]) == blank
    # 填上 pattern：立刻计入并触发
    assert rules_snapshot([_card(pattern="甲", replace="写了一半")]) != blank


def test_snapshot_changes_on_pattern_replace_stage():
    """其余三个字段同样参与比较。"""
    base = rules_snapshot([_card()])
    assert rules_snapshot([_card(pattern="x")]) != base
    assert rules_snapshot([_card(replace="x")]) != base
    assert rules_snapshot([_card(stage="HTML")]) != base


def test_snapshot_is_stable_for_identical_cards():
    """没改动时快照相同——这是「不重复刷新」的前提。"""
    assert rules_snapshot([_card(), _card(pattern="c")]) == rules_snapshot(
        [_card(), _card(pattern="c")]
    )


def test_disabled_rule_is_skipped_by_core():
    """快照变化能生效的前提：core 真的按 enabled 跳过规则。

    勾选框触发刷新只是让预览重算；重算后要不要应用这条规则，由 core 说了算。
    """
    from simple_ebook_converter.core.replace import replacers_by_stage

    raw_on, _html_on = replacers_by_stage([Rule("甲", "X", enabled=True)])
    raw_off, _html_off = replacers_by_stage([Rule("甲", "X", enabled=False)])
    assert raw_on.apply("甲乙") == ("X乙", True)
    assert raw_off.apply("甲乙") == ("甲乙", False)
