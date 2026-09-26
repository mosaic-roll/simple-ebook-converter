import re

import pytest

from simple_ebook_converter.core.config import default_levels
from simple_ebook_converter.core.levels import build_levels, check_pattern, parse_level_spec
from simple_ebook_converter.core.replace import Rule, rules_from_json


def test_parse_level_spec():
    assert parse_level_spec("5:^注解") == (5, "^注解", "level5")
    assert parse_level_spec("1:^卷:volume") == (1, "^卷", "volume")
    assert parse_level_spec("2:^甲:带:冒号") == (2, "^甲", "带:冒号")


@pytest.mark.parametrize("spec", ["^没有级别号", "abc:^x", "7:^x", "0:^x", "1:"])
def test_parse_level_spec_rejects_bad_input(spec):
    with pytest.raises(ValueError):
        parse_level_spec(spec)


def test_check_pattern_reports_the_label():
    check_pattern("^正常", "章标题")
    with pytest.raises(ValueError, match="章标题正则非法"):
        check_pattern("(", "章标题")


def test_build_levels_keeps_builtin_when_preset_missing():
    levels = build_levels({})
    assert [(r.level, r.class_name) for r in levels] == [(2, "volume"), (3, "chapter"), (4, "section")]
    assert next(r for r in levels if r.level == 2).pattern != ""
    assert next(r for r in levels if r.level == 4).pattern == ""


def test_build_levels_preset_overrides_builtin():
    levels = build_levels({"volume": "^第[0-9]+[卷]", "chapter": "^第[0-9]+[章]"})
    assert len(levels) == len(default_levels())
    assert next(r for r in levels if r.level == 2).pattern == "^第[0-9]+[卷]"
    assert next(r for r in levels if r.level == 3).pattern == "^第[0-9]+[章]"
    section = next(r for r in levels if r.level == 4)
    assert section.active is False


def test_build_levels_blank_preset_disables_that_level():
    """三个预设留空 = 不识别该层级（与 GUI 清空输入框一致）。"""
    levels = build_levels({"volume": "", "chapter": "^第.章", "section": ""})
    assert [r.active for r in levels] == [False, True, False]


def test_build_levels_extra_specs_append_and_override():
    levels = build_levels({}, ["5:^注解:note", "2:^第[0-9]+卷"])
    by_level = {r.level: r for r in levels}
    assert set(by_level) == {2, 3, 4, 5}
    assert (by_level[5].pattern, by_level[5].class_name) == ("^注解", "note")
    assert (by_level[2].pattern, by_level[2].class_name) == ("^第[0-9]+卷", "level2")


def test_build_levels_does_not_share_default_rules():
    build_levels({"volume": "^改了"})[0].pattern = "^又改了"
    assert default_levels()[0].pattern != "^又改了"


@pytest.mark.parametrize(
    ("presets", "extra", "label"),
    [
        ({"volume": "("}, [], "卷标题"),
        ({"chapter": "["}, [], "章标题"),
        ({"section": "(?"}, [], "节标题"),
        ({}, ["5:^ok", "2:("], "额外层级 2"),
    ],
)
def test_build_levels_rejects_invalid_pattern(presets, extra, label):
    with pytest.raises(ValueError, match=re.escape(label)):
        build_levels(presets, extra)


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
