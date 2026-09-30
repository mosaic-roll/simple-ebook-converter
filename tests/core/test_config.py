import inspect
import re

import pytest

from simple_ebook_converter.core.config import (
    ALIGN_CHOICES,
    DEFAULT_CHAPTER_RE,
    DEFAULT_VOLUME_RE,
    DEFAULTS,
    LEVEL_PRESETS,
    Config,
    default_levels,
)
from simple_ebook_converter.core.options import OPTIONS, Option, option_default, option_groups
from simple_ebook_converter.core.parser import parse
from simple_ebook_converter.core.toc import to_json, to_text

#: 不由选项表提供、直接构造 Config 就能设的字段
_DIRECT_FIELDS = {"levels", "replacements"}


def _option(name: str) -> Option:
    return next(opt for opt in OPTIONS if opt.name == name)


def _field_options() -> list[Option]:
    return [opt for opt in OPTIONS if opt.in_config]


def test_every_config_field_is_either_an_option_or_direct():
    """Config 字段要么有对应选项，要么明确属于直接传入的那几个。"""
    covered = {opt.name for opt in _field_options()}
    assert set(Config.__dataclass_fields__) - covered == _DIRECT_FIELDS


def test_option_defaults_come_from_config():
    """选项默认值从 Config 派生：改 Config 的默认值就同时改了 CLI 行为与 --help。"""
    for opt in _field_options():
        assert option_default(opt) == getattr(DEFAULTS, opt.name), opt.name


def test_empty_option_defaults():
    """留空即「未指定」：点击参数里只能是 None 或 ()，不能是空串。"""
    for name in ("title", "date", "out", "dump_css", "cover", "font", "css_file"):
        assert option_default(_option(name)) is None, name


def test_negative_flags_default_to_the_positive_field():
    """反面选项（--no-xxx）默认关掉，等价于正面字段取默认。"""
    for opt in _field_options():
        if opt.negative:
            assert getattr(DEFAULTS, opt.name) is True, opt.name


def test_option_groups_keep_declaration_order():
    groups = [name for name, _items in option_groups()]
    assert groups == list(dict.fromkeys(groups))
    assert set(groups) == {opt.group for opt in OPTIONS}


def test_option_flags_are_derived_from_name():
    assert _option("encoding").flags == ("-e", "--encoding")
    assert _option("overwrite").flags == ("--no-overwrite",)
    assert _option("line_height").flags == ("--line-height",)


def test_library_defaults_come_from_config():
    """`parse()` / `to_json()` / `to_text()` 的缺省值也必须跟着 Config 走。"""
    params = inspect.signature(parse).parameters
    assert params["max_title_len"].default == DEFAULTS.max_title_len
    assert params["preface_title"].default == DEFAULTS.preface_title
    for fn in (to_json, to_text):
        assert inspect.signature(fn).parameters["depth"].default == DEFAULTS.toc_depth


def test_level_presets_match_config_levels():
    """卷/章的默认值与 Config.levels 字段默认一致。"""
    for level, name, _label, pattern in LEVEL_PRESETS:
        assert option_default(_option(name)) == pattern
        assert next(r.pattern for r in DEFAULTS.levels if r.level == level) == pattern


def test_default_chapter_regex_covers_common_headings():
    for heading in (
        "第12章 初遇",
        "第 3 回 风起",
        "第一章",
        "第一节",
        "楔子",
        "序章",
        "Chapter 1",
        "12",
        "1、",
        "番外 后日谈",
        "最终章",
    ):
        assert re.match(DEFAULT_CHAPTER_RE, heading), heading
    assert re.match(DEFAULT_VOLUME_RE, "第一卷 风起")
    # 「篇」不算卷，避免正文里的「第一篇」被误判
    assert not re.match(DEFAULT_VOLUME_RE, "第一篇 习作")


def test_default_regexes_only_match_from_line_start():
    """正文里提到「第12章」不该被当成标题；正则一律从头匹配。"""
    assert re.match(DEFAULT_CHAPTER_RE, "第12章 初遇")
    assert not re.match(DEFAULT_CHAPTER_RE, "他说第12章里提过")


def test_validate_accepts_defaults():
    DEFAULTS.validate()


def test_validate_rejects_out_of_range():
    cases = [
        ({"max_title_len": 0}, "标题最大字数"),
        ({"toc_depth": 0}, "目录深度"),
        ({"toc_depth": 7}, "目录深度"),
        ({"indent": -1}, "段落缩进"),
        ({"chapter_align": "middle"}, "章对齐"),
        ({"volume_align": "MIDDLE"}, "卷对齐"),
        ({"date": "2024/13/05"}, "日期格式错误"),
        ({"date": "not-a-date"}, "日期格式错误"),
    ]
    for kwargs, message in cases:
        with pytest.raises(ValueError, match=message):
            Config(**kwargs).validate()


def test_validate_accepts_edge_values():
    Config(max_title_len=1, toc_depth=1, indent=0, date="2024-05-13 08:30:00").validate()
    Config(toc_depth=6, date="2024-05-13").validate()


def test_css_file_and_css_append_are_mutually_exclusive(tmp_path):
    a, b = tmp_path / "a.css", tmp_path / "b.css"
    a.write_text("", encoding="utf-8")
    b.write_text("", encoding="utf-8")
    Config(css_file=a).validate()
    Config(css_append=b).validate()
    with pytest.raises(ValueError, match="互斥"):
        Config(css_file=a, css_append=b).validate()


def test_align_choices_are_the_only_allowed():
    for value in ALIGN_CHOICES:
        Config(chapter_align=value, volume_align=value).validate()
    assert set(ALIGN_CHOICES) == {"left", "center", "right", "justify"}


def test_book_title_falls_back_to_stem_then_constant(tmp_path):
    assert Config(title="书名", input=tmp_path / "x.txt").book_title == "书名"
    assert Config(input=tmp_path / "我的小说.txt").book_title == "我的小说"
    assert Config().book_title == "未命名"


def test_default_levels_are_independent_copies():
    first, second = default_levels(), default_levels()
    first[0].pattern = "改了"
    assert second[0].pattern == DEFAULT_VOLUME_RE
