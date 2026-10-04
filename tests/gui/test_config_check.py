"""`gui.config_check`：落盘前的净化——非法值存成空，下次启动用 core 默认。

这一层不做校验逻辑，只做「问 core 一次然后换成空」。合法性判定的真源在
`core.options.is_valid()` 与 `core.levels.is_valid_level()`，这里只测转发与
降级行为对不对。
"""

import pytest

from simple_ebook_converter.core.config import LevelRule
from simple_ebook_converter.gui.config_check import (
    accepts,
    as_stored,
    extra_level,
    level_number,
)
from simple_ebook_converter.gui.tabs.layout import CSS_MODES, CSS_SOURCE_FILE


# --------------------------------------------------- as_stored ---------------------------------------------------
def test_as_stored_turns_an_int_field_into_a_number():
    """`indent` 存成 4 而不是 "4"——`Config` 那边的类型对不上。"""
    assert as_stored("indent", " 4 ") == 4
    assert isinstance(as_stored("indent", "4"), int)


def test_as_stored_maps_blank_int_field_to_none():
    """空文本对 int 字段是 None（= 用 core 默认），不是 0 也不是空串。"""
    assert as_stored("indent", "   ") is None


def test_as_stored_maps_an_unparseable_int_field_to_none():
    """非法输入和留空同等处理：存 None，用 core 默认。

    关窗保存走的就是这条，`_on_close` 只接 `OSError`，抛出去就存不下了。
    """
    assert as_stored("indent", "abc") is None
    assert as_stored("indent", "2.5") is None
    assert as_stored("toc_depth", "六") is None


def test_as_stored_strips_a_non_int_field():
    """非 int 字段只 strip，不转类型。"""
    assert as_stored("line_height", " 1.5 ") == "1.5"
    assert as_stored("para_spacing", "   ") is None


def test_as_stored_rejects_an_int_field_out_of_range():
    """类型对、值域不对的也要换成空。

    `-1` 存得进 JSON，但下一次生成会报「段落缩进字数不能为负」——用户早就忘了
    填过这一栏，存的时候就该清掉。
    """
    assert as_stored("indent", "-1") is None
    assert as_stored("toc_depth", "0") is None
    assert as_stored("toc_depth", "7") is None


def test_as_stored_keeps_a_legal_int_field():
    assert as_stored("indent", "0") == 0
    assert as_stored("toc_depth", "6") == 6


# ----------------------------------------------------- 正则字段的净化 -----------------------------------------------------
def test_as_stored_drops_an_invalid_volume_regex():
    """卷/章的正则非法时存空——否则之后每次生成都在同一条规则上报错。"""
    assert as_stored("volume", "(") is None
    assert as_stored("chapter", "(?:") is None


def test_as_stored_drops_an_invalid_exclude_regex():
    assert as_stored("exclude", "[") is None


def test_as_stored_keeps_a_legal_regex():
    assert as_stored("volume", "^第\\d+卷") == "^第\\d+卷"
    assert as_stored("exclude", "^第\\d+卷") == "^第\\d+卷"


def test_blank_regex_stays_none():
    """留空就是「用内置正则」，不是非法。"""
    assert as_stored("volume", "") is None
    assert as_stored("volume", "   ") is None


def test_as_stored_treats_a_missing_text_as_unset():
    """`text` 是 `None` 等同「用户没填」——调用方可能根本没有文本可取。"""
    assert as_stored("indent", None) is None
    assert as_stored("para_align", None) is None


def test_as_stored_drops_an_unknown_align():
    assert as_stored("para_align", "mid") is None
    assert as_stored("para_align", "justify") == "justify"


# --------------------------------------------------- GUI 自己的字段 ---------------------------------------------------
def test_gui_only_fields_are_checked_against_their_own_values():
    """`css_source` / `css_mode` 不进 `Config`，core 不认这两个名字。"""
    assert accepts("css_source", "text") is True
    assert accepts("css_source", CSS_SOURCE_FILE) is True
    assert accepts("css_source", "nonsense") is False
    assert accepts("css_mode", CSS_MODES[0]) is True
    assert accepts("css_mode", "胡说") is False


def test_gui_only_fields_are_sanitized_too():
    assert as_stored("css_source", "text") == "text"
    assert as_stored("css_mode", "胡说") is None


# ----------------------------------------------------- accepts -----------------------------------------------------
def test_accepts_treats_none_as_always_legal():
    """`None` 是「用 core 默认」，默认本身合法。"""
    assert accepts("indent", None) is True
    assert accepts("volume", None) is True
    assert accepts("css_mode", None) is True


# ------------------------------------------------ level_number ------------------------------------------------
@pytest.mark.parametrize(
    ("text", "expected"), [("h4", 4), ("H4", 4), ("4", 4), (" 6 ", 6)]
)
def test_level_number_reads_the_selector(text, expected):
    assert level_number(text) == expected


@pytest.mark.parametrize("text", ["", "   ", "abc", "h", "四点五"])
def test_level_number_returns_none_when_unreadable(text):
    """填不出来返 `None`，不是 `0`。

    `0` 看着像个合法整数，混进规则里会变成一条永远匹配不上任何标题的死规则：
    不报错，只是静默不生效。
    """
    assert level_number(text) is None


# ------------------------------------------------- extra_level -------------------------------------------------
def test_extra_level_keeps_a_legal_row():
    assert extra_level("h5", "note", "^Part") == {
        "level": "h5",
        "class": "note",
        "regex": "^Part",
    }


def test_extra_level_strips_every_field():
    assert extra_level(" h5 ", " note ", " ^Part ")["class"] == "note"


def test_extra_level_clears_a_bad_regex_but_keeps_the_row():
    """正则非法只清正则：级别与 class 是用户填的，整行丢掉等于替用户做决定。"""
    assert extra_level("h5", "note", "(") == {
        "level": "h5",
        "class": "note",
        "regex": "",
    }


def test_extra_level_clears_a_bad_regex_on_a_blank_row():
    """空正则本来就清空——那一行等于没填。"""
    assert extra_level("h5", "note", "")["regex"] == ""


def test_extra_level_clears_the_regex_when_the_level_is_unreadable():
    """级别填不出来时正则也保不住：core 那边会拒这条规则。"""
    assert extra_level("abc", "note", "^Part") == {
        "level": "abc",
        "class": "note",
        "regex": "",
    }


def test_extra_level_agrees_with_core():
    """净化后的行一定能喂给 core——不能出现「存得下、生成时才炸」的中间态。"""
    from simple_ebook_converter.core.levels import build_rules

    for level, class_name, regex in [("h5", "note", "^Part"), ("abc", "note", "^P"), ("h5", "n", "(")]:
        row = extra_level(level, class_name, regex)
        number = level_number(row["level"])
        if number is None or not row["regex"]:
            continue
        build_rules([LevelRule(number, row["regex"], row["class"])])
