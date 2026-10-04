"""`core.validation`：`field_error`（单字段）与 `validate_config`（整份配置）。"""

import dataclasses

import pytest

from simple_ebook_converter.core.config import ALIGN_CHOICES, DEFAULTS, Config
from simple_ebook_converter.core.validation import (
    _CHECKS,
    _CROSS_CHECKS,
    field_error,
    validate_config,
)

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
    ("date", "not-a-date", "日期格式错误"),
    ("exclude", "(?", "排除规则正则非法"),
]


# ------------------------------------------------- field_error -------------------------------------------------
@pytest.mark.parametrize(("name", "value", "message"), BAD_FIELDS)
def test_field_error_reports_bad_values(name, value, message):
    assert message in (field_error(name, value) or "")


@pytest.mark.parametrize("name", sorted({name for name, _, _ in BAD_FIELDS}))
def test_field_error_is_quiet_on_the_default(name):
    """默认值一律合法——`validate_config(DEFAULTS)` 能过就是这条的推论。"""
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


def test_field_error_requires_typed_values():
    """`field_error` 的约定：收已类型化的值，不是前端原始文本。

    真传错类型该崩还是崩（`field_error("encoding", 123)` 会在 `.lower()` 上炸），
    兜住它得在 `_CHECKS` 那一层统一包 `try`，不值。这里钉的是约定本身。
    """
    assert field_error("indent", 2) is None
    assert field_error("indent", -1) is not None
    assert field_error("chapter_align", "center") is None


# ------------------------------------------------------ 注册表的形状 ------------------------------------------------------
def test_every_checked_field_is_a_config_field():
    """`_CHECKS` 里不该出现不存在的字段名——打错字会静默变成「无约束」。"""
    names = {f.name for f in dataclasses.fields(Config)}
    assert set(_CHECKS) <= names


def test_cross_checks_are_not_in_the_field_table():
    """跨字段规则不进 `_CHECKS`——它的键是字段名，而跨字段约束没有归属的字段。

    单字段入口对这两个字段一律返回 None（各自单独给都合法），这是设计如此。
    """
    assert _CROSS_CHECKS
    assert "css_file" not in _CHECKS
    assert "css_append" not in _CHECKS
    assert field_error("css_file", "a.css") is None
    assert field_error("css_append", "a.css") is None


def test_cross_checks_are_named_functions():
    """收命名函数不收 lambda：第二条进来时，一堆 lambda 里嵌消息字符串会很难读。"""
    for cross in _CROSS_CHECKS:
        assert cross.__name__ != "<lambda>"
        assert cross.__module__ == "simple_ebook_converter.core.validation"


# --------------------------------------------- validate_config ---------------------------------------------
def test_validate_accepts_defaults():
    validate_config(DEFAULTS)


def test_validate_rejects_out_of_range():
    for kwargs, value, message in BAD_FIELDS:
        with pytest.raises(ValueError, match=message):
            validate_config(Config(**{kwargs: value}))


def test_validate_accepts_a_legal_exclude_regex():
    """`exclude` 走的是同一套正则合法性，合法就放行。"""
    validate_config(Config(exclude="^第\\d+卷"))
    validate_config(Config(exclude=""))


def test_exclude_error_is_a_value_error_not_a_re_error():
    """报错必须是 `ValueError`。

    `re.error` 不继承 `ValueError`，两个前端的 `except ValueError` 都接不住，
    非法正则就会以裸栈的形式从回调里飞出去。
    """
    with pytest.raises(ValueError):
        validate_config(Config(exclude="("))


def test_validate_reports_the_first_bad_field_in_table_order():
    """`_CHECKS` 的插入顺序就是校验顺序，第一个错先冒出来。"""
    with pytest.raises(ValueError, match="标题最大字数"):
        validate_config(Config(max_title_len=0, toc_depth=99, indent=-1))


def test_validate_accepts_edge_values():
    validate_config(
        Config(max_title_len=1, toc_depth=1, indent=0, date="2024-05-13 08:30:00")
    )
    validate_config(Config(toc_depth=6, date="2024-05-13"))


def test_validate_accepts_any_codec_python_resolves():
    """不在任何名单里的合法编码照样放行——名单管显示，不管能不能用。

    chardet 能报出 `FALLBACK_ENCODINGS` 之外的名字（cp1252 / koi8-r…），
    `windows-1252` 这种非规范写法也认，所以这里只查 `codecs.lookup()` 解不解析得开。
    """
    for encoding in ("auto", "cp1252", "windows-1252", "koi8-r", "euc_kr"):
        validate_config(Config(encoding=encoding))


def test_align_choices_are_the_only_allowed():
    for value in ALIGN_CHOICES:
        validate_config(
            Config(chapter_align=value, volume_align=value, para_align=value)
        )
    assert set(ALIGN_CHOICES) == {"left", "center", "right", "justify"}


def test_css_file_and_css_append_are_mutually_exclusive(tmp_path):
    a, b = tmp_path / "a.css", tmp_path / "b.css"
    a.write_text("", encoding="utf-8")
    b.write_text("", encoding="utf-8")
    validate_config(Config(css_file=a))
    validate_config(Config(css_append=b))
    with pytest.raises(ValueError, match="互斥"):
        validate_config(Config(css_file=a, css_append=b))


def test_cross_field_errors_come_after_the_field_ones():
    """字段值域先查，跨字段后查——两个错都在时先报字段那个。"""
    with pytest.raises(ValueError, match="段落缩进"):
        validate_config(Config(indent=-1, css_file="a.css", css_append="b.css"))