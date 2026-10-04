import inspect
import re
from pathlib import Path

from simple_ebook_converter.core.config import (
    DEFAULT_CHAPTER_RE,
    DEFAULT_VOLUME_RE,
    DEFAULTS,
    LEVEL_PRESETS,
    Config,
    default_levels,
)
from simple_ebook_converter.core.options import (
    OPTIONS,
    Option,
    option_default,
)
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


def test_empty_option_defaults():
    """留空即「未指定」：点击参数里只能是 None 或 ()，不能是空串。"""
    for name in ("title", "date", "out", "dump_css", "cover", "font", "css_file"):
        assert option_default(_option(name)) is None, name


def test_library_defaults_come_from_config():
    """`parse()` / `to_json()` / `to_text()` 的默认值也必须跟着 Config 走。"""
    params = inspect.signature(parse).parameters
    assert params["max_title_len"].default == DEFAULTS.max_title_len
    assert params["preface_title"].default == DEFAULTS.preface_title
    assert params["exclude"].default == DEFAULTS.exclude
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
        "第一章",
        "第一节",
        "楔子",
        "序章",
        "Chapter 1",
        "番外 后日谈",
        "最终章",
        "终章",
        "引子",
        "前言",
    ):
        assert re.match(DEFAULT_CHAPTER_RE, heading), heading
    assert re.match(DEFAULT_VOLUME_RE, "第一卷 风起")
    # 「篇」不算卷，避免正文里的「第一篇」被误判
    assert not re.match(DEFAULT_VOLUME_RE, "第一篇 习作")
    # 纯数字和数字+标点不再匹配（太容易误报）
    assert not re.match(DEFAULT_CHAPTER_RE, "12")
    assert not re.match(DEFAULT_CHAPTER_RE, "1、")
    # 冒号分隔符也不再匹配（用户改用了空格/无分隔）
    assert not re.match(DEFAULT_CHAPTER_RE, "第100章:副标题")


def test_default_regexes_only_match_from_line_start():
    """正文里提到「第12章」不该被当成标题；正则一律从头匹配。"""
    assert re.match(DEFAULT_CHAPTER_RE, "第12章 初遇")
    assert not re.match(DEFAULT_CHAPTER_RE, "他说第12章里提过")


# 值域与整份配置的校验都在 `tests/core/test_validation.py`——规则跟着
# `core/validation.py` 走，这个文件只留数据模型本身的行为。


def test_volume_align_defaults_to_center():
    """卷和章都默认居中，与 GUI「对齐方式」的默认项一致。

    core 和 GUI 的默认值不同时，界面看到的与 CLI 直接跑出来的排版会有差。
    """
    assert DEFAULTS.volume_align == "center"
    assert DEFAULTS.chapter_align == "center"


def test_book_title_falls_back_to_stem_then_constant():
    assert Config(title="书名", input=Path("x.txt")).book_title == "书名"
    assert Config(input=Path("我的小说.txt")).book_title == "我的小说"
    assert Config().book_title == "未命名"


def test_default_levels_are_independent_copies():
    first, second = default_levels(), default_levels()
    first[0].pattern = "改了"
    assert second[0].pattern == DEFAULT_VOLUME_RE
