import inspect
import re

import pytest

from simple_ebook_converter.core.config import (
    ALIGN_CHOICES,
    DEFAULT_CHAPTER_RE,
    DEFAULT_MAX_TITLE_LEN,
    DEFAULT_PREFACE_TITLE,
    DEFAULT_TOC_DEPTH,
    DEFAULT_VOLUME_RE,
    FALLBACK_TITLE,
    LEVEL_FIELDS,
    LEVEL_PRESETS,
    Config,
    default_levels,
)
from simple_ebook_converter.core.options import (
    BOOL,
    OPTIONS,
    Option,
    option_defaults,
    option_groups,
)
from simple_ebook_converter.core.parser import parse
from simple_ebook_converter.core.toc import to_json, to_text

#: 不由选项表提供、直接构造 Config 就能设的字段
_DIRECT_FIELDS = {"input", "levels", "replacements"}


def _option(name: str) -> Option:
    return next(opt for opt in OPTIONS if opt.name == name)


def _field_options() -> list[Option]:
    return [opt for opt in OPTIONS if opt.field]



def test_every_config_field_is_either_an_option_or_direct():
    """Config 字段要么有对应选项，要么明确属于直接传入的那几个。"""
    covered = {opt.field for opt in _field_options()}
    assert set(Config.__dataclass_fields__) - covered == _DIRECT_FIELDS


def test_option_defaults_come_from_config():
    """选项默认值从 Config 派生：改 Config 的默认值就同时改了 CLI 行为与 --help。"""
    cfg = Config()
    for opt in _field_options():
        if opt.invert:
            continue
        expected = getattr(cfg, opt.field)
        assert option_defaults()[opt.name] == ("" if expected is None else expected), opt.name


def test_flag_defaults_are_off():
    for name, value in option_defaults().items():
        if _option(name).kind == "bool":
            assert value is False, name


def test_empty_option_defaults():
    for name in ("input", "out", "replace_json", "replace_file", "dump_css", "level"):
        assert option_defaults()[name] == (() if name == "level" else ""), name
    assert option_defaults()["toc_format"] == "text"


def test_level_presets_match_config_levels():
    """卷/章/节的默认值就是 Config.levels 里那三条，且预设表与 LEVEL_FIELDS 一致。"""
    defaults = option_defaults()
    for level, name, _label in LEVEL_PRESETS:
        assert defaults[name] == next(r.pattern for r in Config().levels if r.level == level)
        assert LEVEL_FIELDS[level] == name
    assert defaults["section"] == ""


def test_inverted_flags_default_to_the_positive_field():
    """反面选项（--no-xxx）默认关掉，等价于正面字段取默认。"""
    cfg = Config()
    for opt in _field_options():
        if opt.invert:
            assert getattr(cfg, opt.field) is True, opt.name


def test_option_defaults_returns_fresh_dict():
    first = option_defaults()
    first["max_title_len"] = 1234
    assert option_defaults()["max_title_len"] != 1234


def test_option_flags_are_derived_from_name():
    assert _option("encoding").flags == ("-e", "--encoding")
    assert _option("no_text_cover").flags == ("--no-text-cover",)
    assert _option("line_height").flags == ("--line-height",)


def test_option_groups_keep_declaration_order():
    groups = [name for name, _items in option_groups()]
    assert groups == list(dict.fromkeys(groups))
    assert set(groups) == {opt.group for opt in OPTIONS}


def test_library_defaults_come_from_config():
    """`parse()` / `to_json()` / `to_text()` 的缺省值也必须跟着 Config 走。"""
    cfg = Config()
    params = inspect.signature(parse).parameters
    assert params["max_title_len"].default == cfg.max_title_len
    assert params["preface_title"].default == cfg.preface_title
    assert params["fallback_title"].default == FALLBACK_TITLE
    for fn in (to_json, to_text):
        assert inspect.signature(fn).parameters["depth"].default == cfg.toc_depth


def test_default_constants_match_config():
    assert (DEFAULT_MAX_TITLE_LEN, DEFAULT_PREFACE_TITLE, DEFAULT_TOC_DEPTH) == (
        Config().max_title_len,
        Config().preface_title,
        Config().toc_depth,
    )


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
    Config().validate()


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


def test_align_choices_are_the_only_allowed():
    for value in ALIGN_CHOICES:
        Config(chapter_align=value, volume_align=value).validate()
    assert set(ALIGN_CHOICES) == {"left", "center", "right"}


def test_book_title_falls_back_to_stem_then_constant(tmp_path):
    assert Config(title="书名", input=tmp_path / "x.txt").book_title == "书名"
    assert Config(input=tmp_path / "我的小说.txt").book_title == "我的小说"
    assert Config().book_title == FALLBACK_TITLE


def test_default_levels_are_independent_copies():
    first, second = default_levels(), default_levels()
    first[0].pattern = "改了"
    assert second[0].pattern == DEFAULT_VOLUME_RE
