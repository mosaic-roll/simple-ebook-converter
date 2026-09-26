import re

import pytest

from simple_ebook_converter.core.config import default_levels
from simple_ebook_converter.core.levels import build_levels, check_pattern, parse_level_spec
from simple_ebook_converter.core.replace import Rule, rules_from_json


def test_parse_level_spec():
    assert parse_level_spec("h5:^注解") == (5, "^注解", "")
    assert parse_level_spec("h1.volume:^卷") == (1, "^卷", "volume")
    # 冒号后整段都是正则，所以正则里可以有冒号
    assert parse_level_spec("h2:^甲:带:冒号") == (2, "^甲:带:冒号", "")


@pytest.mark.parametrize("spec", ["^没有级别号", "h7:^x", "h0:^x", "x2:^x", "h2", "h2.类名:^x"])
def test_parse_level_spec_rejects_bad_input(spec):
    with pytest.raises(ValueError):
        parse_level_spec(spec)


def test_check_pattern_reports_the_label():
    check_pattern("^正常", "章标题")
    with pytest.raises(ValueError, match="章标题正则非法"):
        check_pattern("(", "章标题")


def test_build_levels_keeps_builtin_when_spec_missing():
    levels = build_levels()
    assert [(r.level, r.class_name) for r in levels] == [
        (2, "volume"),
        (3, "chapter"),
        (4, "section"),
    ]
    assert next(r for r in levels if r.level == 2).pattern != ""
    assert next(r for r in levels if r.level == 4).pattern == ""


def test_build_levels_spec_overrides_builtin():
    levels = build_levels(["h2.volume:^第[0-9]+[卷]", "h3.chapter:^第[0-9]+[章]"])
    assert len(levels) == len(default_levels())
    assert next(r for r in levels if r.level == 2).pattern == "^第[0-9]+[卷]"
    assert next(r for r in levels if r.level == 3).pattern == "^第[0-9]+[章]"
    section = next(r for r in levels if r.level == 4)
    assert section.active is False


def test_build_levels_blank_pattern_disables_that_level():
    """空正则 = 不识别该层级（`--no-volume` 与 GUI 清空输入框都走这条路）。"""
    levels = build_levels(["h2.volume:", "h3.chapter:^第.章", "h4.section:"])
    assert [r.active for r in levels] == [False, True, False]


def test_build_levels_extra_specs_append_and_override():
    levels = build_levels(["h5.note:^注解", "h2:^第[0-9]+卷"])
    by_level = {r.level: r for r in levels}
    assert set(by_level) == {2, 3, 4, 5}
    assert (by_level[5].pattern, by_level[5].class_name) == ("^注解", "note")
    # class 省略 = 不给该标题加 class
    assert (by_level[2].pattern, by_level[2].class_name) == ("^第[0-9]+卷", "")


def test_build_levels_does_not_share_default_rules():
    build_levels(["h2.volume:^改了"])[0].pattern = "^又改了"
    assert default_levels()[0].pattern != "^又改了"


@pytest.mark.parametrize(
    ("specs", "label"),
    [
        (["h2.volume:("], "卷标题"),
        (["h3.chapter:["], "章标题"),
        (["h4.section:(?:"], "节标题"),
        (["h5.note:^ok", "h2:("], "额外层级 h2"),
    ],
)
def test_build_levels_rejects_invalid_pattern(specs, label):
    with pytest.raises(ValueError, match=re.escape(label)):
        build_levels(specs)


def test_rules_from_json():
    assert rules_from_json('[{"pattern": "甲", "replace": "乙"}]') == [Rule("甲", "乙")]


@pytest.mark.parametrize(
    "text", ['{"pattern": "甲"}', '[{"replace": "乙"}]', "not json", '[{"pattern": 1}]']
)
def test_rules_from_json_rejects_invalid(text):
    with pytest.raises(ValueError):
        rules_from_json(text)


def test_rules_from_json_accepts_empty_list():
    assert rules_from_json("[]") == []


def test_rules_from_json_rejects_invalid_pattern():
    with pytest.raises(ValueError, match="第 2 条替换规则正则非法"):
        rules_from_json('[{"pattern": "甲", "replace": "乙"}, {"pattern": "("}]')
