import re

import pytest

from simple_ebook_converter.core.config import default_levels
from simple_ebook_converter.core.levels import (
    build_levels,
    check_pattern,
    parse_level_spec,
)


def test_parse_level_spec():
    assert parse_level_spec("h5:^注解") == (5, "^注解", "")
    assert parse_level_spec("h1.volume:^卷") == (1, "^卷", "volume")
    # 冒号后整段都是正则，所以正则里可以有冒号
    assert parse_level_spec("h2:^甲:带:冒号") == (2, "^甲:带:冒号", "")


@pytest.mark.parametrize(
    "spec", ["^没有级别号", "h7:^x", "h0:^x", "x2:^x", "h2", "h2.类名:^x"]
)
def test_parse_level_spec_rejects_bad_input(spec):
    with pytest.raises(ValueError):
        parse_level_spec(spec)


def test_check_pattern_reports_the_label():
    check_pattern("^正常", "章标题")
    with pytest.raises(ValueError, match="章标题正则非法"):
        check_pattern("(", "章标题")


def test_build_levels_without_specs_has_no_rules():
    """内置默认值不在这里补：`Config` 的字段默认是 `default_levels()`，前端
    （`options._level_specs()`）会把卷/章/节三条规格排在前面传进来。"""
    assert build_levels() == []


def test_build_levels_returns_only_the_specs():
    levels = build_levels(["h3.chapter:^第[0-9]+[章]", "h2.volume:^第[0-9]+[卷]"])
    assert [(r.level, r.class_name, r.pattern) for r in levels] == [
        (2, "volume", "^第[0-9]+[卷]"),
        (3, "chapter", "^第[0-9]+[章]"),
    ]


def test_build_levels_blank_pattern_disables_that_level():
    """空正则 = 不识别该层级（`--no-volume` 与 GUI 清空输入框都走这条路）。"""
    levels = build_levels(["h2.volume:", "h3.chapter:^第.章"])
    assert [r.active for r in levels] == [False, True]


def test_build_levels_sorts_by_level_keeping_written_order():
    levels = build_levels(["h5.note:^注解", "h2:^第[0-9]+卷"])
    assert [(r.level, r.class_name) for r in levels] == [(2, ""), (5, "note")]


def test_build_levels_keeps_every_spec_in_written_order():
    """同一级、同 class 都照单全收：正则难写就拆成几条，先写的先试。"""
    levels = build_levels(["h5.note:^注", "h5.scene:^场景", "h5.note:^注解"])
    assert [(r.level, r.class_name, r.pattern) for r in levels if r.level == 5] == [
        (5, "note", "^注"),
        (5, "scene", "^场景"),
        (5, "note", "^注解"),
    ]


def test_build_levels_does_not_share_default_rules():
    build_levels(["h2.volume:^改了"])[0].pattern = "^又改了"
    assert default_levels()[0].pattern != "^又改了"


@pytest.mark.parametrize(
    ("specs", "label"),
    [
        (["h2.volume:("], "卷标题"),
        (["h3.chapter:["], "章标题"),
        (["h5.note:(?:"], "额外层级 h5"),
        (["h5.note:^ok", "h2:("], "额外层级 h2"),
    ],
)
def test_build_levels_rejects_invalid_pattern(specs, label):
    with pytest.raises(ValueError, match=re.escape(label)):
        build_levels(specs)
