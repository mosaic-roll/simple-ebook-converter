import dataclasses
import inspect
import re
from pathlib import Path

import pytest

from simple_ebook_converter.core.config import (
    _CHECKS,
    ALIGN_CHOICES,
    DEFAULT_CHAPTER_RE,
    DEFAULT_VOLUME_RE,
    DEFAULTS,
    LEVEL_PRESETS,
    Config,
    default_levels,
    field_error,
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
        "12",
        "1、",
        "番外 后日谈",
        "最终章",
        "终章",
        "第100章:副标题",
        "引子",
        "前言",
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
        ({"toc_format": "md"}, "目录格式"),
        ({"encoding": "bogus-enc"}, "未知编码"),
        ({"indent": -1}, "段落缩进"),
        ({"chapter_align": "middle"}, "章对齐"),
        ({"volume_align": "MIDDLE"}, "卷对齐"),
        ({"para_align": "mid"}, "正文对齐"),
        ({"date": "2024/13/05"}, "日期格式错误"),
        ({"date": "not-a-date"}, "日期格式错误"),
        ({"exclude": "(?"}, "排除规则正则非法"),
    ]
    for kwargs, message in cases:
        with pytest.raises(ValueError, match=message):
            Config(**kwargs).validate()


def test_validate_accepts_a_legal_exclude_regex():
    """`exclude` 走的是同一套正则合法性，合法就放行。"""
    Config(exclude="^第\\d+卷").validate()
    Config(exclude="").validate()


def test_exclude_error_is_a_value_error_not_a_re_error():
    """报错必须是 `ValueError`。

    `re.error` 不继承 `ValueError`，两个前端的 `except ValueError` 都接不住，
    非法正则就会以裸栈的形式从回调里飞出去。
    """
    with pytest.raises(ValueError):
        Config(exclude="(").validate()


# ------------------------------------------------------------- field_error

#: (字段, 非法值, 消息片段)。直接测单字段入口，不必构造 `Config`。
BAD_FIELDS = [
    ("max_title_len", 0, "标题最大字数"),
    ("toc_depth", 0, "目录深度"),
    ("toc_depth", 7, "目录深度"),
    ("toc_format", "md", "目录格式"),
    ("encoding", "bogus-enc", "未知编码"),
    ("indent", -1, "段落缩进"),
    ("chapter_align", "middle", "章对齐"),
    ("volume_align", "MIDDLE", "卷对齐"),
    ("para_align", "mid", "正文对齐"),
    ("date", "2024/13/05", "日期格式错误"),
    ("exclude", "(?", "排除规则正则非法"),
]


@pytest.mark.parametrize(("name", "value", "message"), BAD_FIELDS)
def test_field_error_reports_bad_values(name, value, message):
    assert message in (field_error(name, value) or "")


@pytest.mark.parametrize("name", sorted({name for name, _, _ in BAD_FIELDS}))
def test_field_error_is_quiet_on_the_default(name):
    """默认值一律合法——`DEFAULTS.validate()` 能过就是这条的推论。"""
    assert field_error(name, getattr(DEFAULTS, name)) is None


def test_field_error_ignores_a_field_without_a_constraint():
    """没有值域约束的字段返回 None，不是报错。

    `title` / `language` 之类没有约束（语言码原样写进 `dc:language`），`is_valid()`
    会对它们返回 True 就是靠这一条。
    """
    assert field_error("title", "任意书名") is None
    assert field_error("language", "zh") is None
    assert field_error("根本没有这个字段", 1) is None


def test_field_error_accepts_auto_encoding():
    """`auto` 与空串都跳过查表——空串在 `decode` 里也当 auto 处理。"""
    assert field_error("encoding", "auto") is None
    assert field_error("encoding", "AUTO") is None
    assert field_error("encoding", "") is None


def test_field_error_skips_absent_media():
    assert field_error("font", None) is None
    assert field_error("cover", None) is None


def test_every_checked_field_is_a_config_field():
    """`_CHECKS` 里不该出现不存在的字段名——打错字会静默变成「无约束」。"""
    names = {f.name for f in dataclasses.fields(Config)}
    assert set(_CHECKS) <= names


def test_validate_reports_the_first_bad_field_in_table_order():
    """`_CHECKS` 的插入顺序就是校验顺序，第一个错先冒出来。"""
    with pytest.raises(ValueError, match="标题最大字数"):
        Config(max_title_len=0, toc_depth=99, indent=-1).validate()


def test_validate_accepts_edge_values():
    Config(
        max_title_len=1, toc_depth=1, indent=0, date="2024-05-13 08:30:00"
    ).validate()
    Config(toc_depth=6, date="2024-05-13").validate()


def test_validate_accepts_any_codec_python_resolves():
    """不在任何名单里的合法编码照样放行——名单管显示，不管能不能用。

    chardet 能报出 `FALLBACK_ENCODINGS` 之外的名字（cp1252 / koi8-r…），
    `windows-1252` 这种非规范写法也认，所以这里只查 `codecs.lookup()` 解不解析得开。
    """
    for encoding in ("auto", "cp1252", "windows-1252", "koi8-r", "euc_kr"):
        Config(encoding=encoding).validate()


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
        Config(chapter_align=value, volume_align=value, para_align=value).validate()
    assert set(ALIGN_CHOICES) == {"left", "center", "right", "justify"}


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
