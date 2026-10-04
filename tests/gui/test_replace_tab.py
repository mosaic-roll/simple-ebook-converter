"""替换 Tab 的纯逻辑：卡片 → `Rule`，以及「规则是否变了」的快照判断。

不起 Tk：卡片用桩对象冒充（只要有 `.get()`），够读出快照要的那四个字段。
真正建控件的路径（勾选框有没有接回调）测不到，这里只钉住它依赖的判定逻辑。
"""

from simple_ebook_converter.core.replace import Rule
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


def test_snapshot_changes_when_enabled_toggles():
    """勾选/取消启用必须改变快照，否则勾选框的刷新回调不起作用。"""
    on = rules_snapshot([_card(enabled=True)])
    off = rules_snapshot([_card(enabled=False)])
    assert on != off


def test_snapshot_ignores_empty_pattern_cards():
    """空 pattern 的卡片不计入快照：增删空卡不误触发刷新。"""
    assert rules_snapshot([_card(pattern="")]) == ()
    assert rules_snapshot([_card(), _card(pattern="")]) == rules_snapshot([_card()])


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