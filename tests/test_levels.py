import pytest

from sec.config import default_levels
from sec.levels import build_levels, parse_level_spec
from sec.replace import Rule, rules_from_json


def test_parse_level_spec():
    assert parse_level_spec("5:^注解") == (5, "^注解", "level5")
    assert parse_level_spec("1:^卷:volume") == (1, "^卷", "volume")


@pytest.mark.parametrize("spec", ["^没有级别号", "abc:^x", "7:^x", "0:^x"])
def test_parse_level_spec_rejects_bad_input(spec):
    with pytest.raises(ValueError):
        parse_level_spec(spec)


def test_build_levels_presets_override_default():
    levels = build_levels("^第[0-9]+[卷]", "^第[0-9]+[章]", None, ())
    assert len(levels) == len(default_levels())
    assert next(r for r in levels if r.level == 2).pattern == "^第[0-9]+[卷]"
    assert next(r for r in levels if r.level == 3).pattern == "^第[0-9]+[章]"
    assert next(r for r in levels if r.level == 4).pattern != None


def test_build_levels_extra_rule_list():
    levels = build_levels(None, None, None, ("5:^注解:note",))
    new = [r for r in levels if r.level == 5]
    assert len(new) == 1
    assert new[0].pattern == "^注解"
    assert new[0].class_name == "note"


def test_rules_from_json():
    rules = rules_from_json('[{"pattern": "甲", "replace": "乙"}]')
    assert rules == [Rule("甲", "乙")]


def test_rules_from_json_rejects_invalid():
    with pytest.raises(ValueError):
        rules_from_json('{"pattern": "甲"}')
    with pytest.raises(ValueError):
        rules_from_json('[{"replace": "乙"}]')
    with pytest.raises(ValueError):
        rules_from_json("not json")