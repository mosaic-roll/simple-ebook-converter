import re

import pytest

from simple_ebook_converter.core.config import LevelRule, default_levels
from simple_ebook_converter.core.levels import (
    build_rules,
    check_pattern,
    is_valid_level,
    parse_level_spec,
)

# `hN[.class]:正则` 是 CLI 的 `--level` 参数格式，只由 `parse_level_spec` 解析。
# core 内部一律用 `LevelRule` 三项，所以这里也跟着用 `LevelRule`——测试跟着内部
# 表示走，才不会把 CLI 语法固化成 core 的形状。


# -------------------------------------------------------- parse_level_spec


def test_parse_level_spec():
    assert parse_level_spec("h5:^注解") == LevelRule(5, "^注解")
    assert parse_level_spec("h1.volume:^卷") == LevelRule(1, "^卷", "volume")
    # 冒号后整段都是正则，所以正则里可以有冒号
    assert parse_level_spec("h2:^甲:带:冒号") == LevelRule(2, "^甲:带:冒号")


@pytest.mark.parametrize(
    "spec", ["^没有级别号", "h7:^x", "h0:^x", "x2:^x", "h2", "h2.类名:^x"]
)
def test_parse_level_spec_rejects_bad_input(spec):
    with pytest.raises(ValueError):
        parse_level_spec(spec)


# ------------------------------------------------------------ check_pattern


def test_check_pattern_reports_the_label():
    check_pattern("^正常", "章标题")
    with pytest.raises(ValueError, match="章标题正则非法"):
        check_pattern("(", "章标题")


# --------------------------------------------------------------- build_rules


def test_build_rules_without_rules_has_none():
    """内置默认值不在这里补：`Config` 的字段默认是 `default_levels()`，前端
    （`options._level_rules()`）把卷/章/节三条排在前面传进来。"""
    assert build_rules() == []


def test_build_rules_returns_only_what_it_was_given():
    rules = build_rules(
        [
            LevelRule(3, "^第[0-9]+[章]", "chapter"),
            LevelRule(2, "^第[0-9]+[卷]", "volume"),
        ]
    )
    assert [(r.level, r.class_name, r.pattern) for r in rules] == [
        (2, "volume", "^第[0-9]+[卷]"),
        (3, "chapter", "^第[0-9]+[章]"),
    ]


def test_build_rules_blank_pattern_disables_that_level():
    """空正则 = 不识别该层级（`--no-volume` 与 GUI 清空输入框都走这条路）。"""
    rules = build_rules([LevelRule(2, "", "volume"), LevelRule(3, "^第.章", "chapter")])
    assert [r.active for r in rules] == [False, True]


def test_build_rules_sorts_by_level_keeping_given_order():
    rules = build_rules([LevelRule(5, "^注解", "note"), LevelRule(2, "^第[0-9]+卷")])
    assert [(r.level, r.class_name) for r in rules] == [(2, ""), (5, "note")]


def test_build_rules_keeps_every_rule_in_given_order():
    """同一级、同 class 都照单全收：正则难写就拆成几条，先写的先试。"""
    rules = build_rules(
        [
            LevelRule(5, "^注", "note"),
            LevelRule(5, "^场景", "scene"),
            LevelRule(5, "^注解", "note"),
        ]
    )
    assert [(r.level, r.class_name, r.pattern) for r in rules if r.level == 5] == [
        (5, "note", "^注"),
        (5, "scene", "^场景"),
        (5, "note", "^注解"),
    ]


def test_build_rules_does_not_share_default_rules():
    build_rules([LevelRule(2, "^改了", "volume")])[0].pattern = "^又改了"
    assert default_levels()[0].pattern != "^又改了"


@pytest.mark.parametrize(
    ("rule", "label"),
    [
        (LevelRule(2, "(", "volume"), "卷标题"),
        (LevelRule(3, "[", "chapter"), "章标题"),
        (LevelRule(5, "(?:", "note"), "额外层级 h5"),
    ],
)
def test_build_rules_rejects_invalid_pattern(rule, label):
    with pytest.raises(ValueError, match=re.escape(label)):
        build_rules([rule])


# ------------------------------------------------------------ 级别范围


@pytest.mark.parametrize("level", [0, 7, -1, 99])
def test_build_rules_rejects_a_level_outside_h1_to_h6(level):
    """结构化入口也要查级别——不能只靠 CLI 的 `parse_level_spec()`。

    GUI 直接构造 `LevelRule`，级别框里填坏了会变成 0；不查的话它不报错，只是变成
    一条永远匹配不上任何标题的规则，静默不生效。
    """
    with pytest.raises(ValueError, match="级别需在 1~6 之间"):
        build_rules([LevelRule(level, "^标题")])


@pytest.mark.parametrize("level", [1, 3, 6])
def test_build_rules_accepts_the_range_ends(level):
    assert build_rules([LevelRule(level, "^标题")])[0].level == level


def test_build_rules_rejects_a_bad_level_before_looking_at_the_pattern():
    """级别先查：级别不合法时光看正则挑不出毛病，报错得指向真正的原因。"""
    with pytest.raises(ValueError, match="级别需在 1~6 之间"):
        build_rules([LevelRule(9, "(", "note")])


# ----------------------------------------------------------- is_valid_level


def test_is_valid_level_accepts_a_good_rule():
    assert is_valid_level(LevelRule(4, "^Part", "part")) is True


def test_is_valid_level_rejects_a_bad_pattern():
    assert is_valid_level(LevelRule(4, "(", "part")) is False


def test_is_valid_level_rejects_a_bad_level():
    assert is_valid_level(LevelRule(0, "^标题")) is False
