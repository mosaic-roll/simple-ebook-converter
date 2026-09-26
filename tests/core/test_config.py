import inspect

import pytest

from sec.core.config import (
    ALIGN_CHOICES,
    DEFAULT_CHAPTER_RE,
    DEFAULT_VOLUME_RE,
    Config,
    config_defaults,
    default_levels,
)


def test_defaults_cover_every_config_field():
    defaults = config_defaults()
    cfg = Config()
    for name in cfg.__dataclass_fields__:
        if name == "levels":
            continue
        assert name in defaults, f"config_defaults() 漏了 {name}"


def test_defaults_match_config_values():
    defaults = config_defaults()
    cfg = Config()
    assert defaults["encoding"] == cfg.encoding
    assert defaults["language"] == cfg.language
    assert defaults["max_title_len"] == cfg.max_title_len
    assert defaults["preface_title"] == cfg.preface_title
    assert defaults["toc_depth"] == cfg.toc_depth
    assert defaults["indent"] == cfg.indent
    assert defaults["line_height"] == cfg.line_height
    assert defaults["para_spacing"] == cfg.para_spacing
    assert defaults["chapter_align"] == cfg.chapter_align
    assert defaults["volume_align"] == cfg.volume_align
    assert defaults["no_volume"] is cfg.no_volume
    assert defaults["no_clean"] is cfg.no_clean
    assert defaults["no_toc"] is cfg.no_toc


def test_defaults_none_fields_become_empty_string():
    defaults = config_defaults()
    assert defaults["title"] == ""
    assert defaults["author"] == ""
    assert defaults["date"] == ""
    assert defaults["cover"] == ""
    assert defaults["font"] == ""
    assert defaults["css_file"] == ""


def test_defaults_split_level_patterns():
    defaults = config_defaults()
    assert defaults["volume"] == DEFAULT_VOLUME_RE
    assert defaults["chapter"] == DEFAULT_CHAPTER_RE
    assert defaults["section"] == ""
    by_level = {r.level: r.pattern for r in default_levels()}
    assert defaults["volume"] == by_level[2]
    assert defaults["chapter"] == by_level[3]


def test_defaults_no_overwrite_is_inverse_of_overwrite():
    defaults = config_defaults()
    assert defaults["overwrite"] is True
    assert defaults["no_overwrite"] is False


def test_defaults_are_derived_not_hardcoded():
    """逐字段比对，任何一个默认值写死而非从 Config 派生都会被发现。"""
    defaults = config_defaults()
    cfg = Config()
    for name in cfg.__dataclass_fields__:
        if name in ("levels", "overwrite"):
            continue
        value = getattr(cfg, name)
        expected = "" if value is None else value
        assert defaults[name] == expected, f"{name} 与 Config() 默认值不一致"


def test_defaults_returns_fresh_dict():
    first = config_defaults()
    first["max_title_len"] = 1234
    assert config_defaults()["max_title_len"] != 1234


def test_validate_accepts_defaults():
    Config().validate()  # 默认值必须全部合法


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


def test_library_function_defaults_come_from_config():
    """parse()/to_json()/to_text() 的缺省值也必须跟着 Config 走，不能另写一份。"""
    from sec.core import parser, toc

    defaults = config_defaults()
    parse_params = inspect.signature(parser.parse).parameters
    assert parse_params["max_title_len"].default == defaults["max_title_len"]
    assert parse_params["preface_title"].default == defaults["preface_title"]
    for fn in (toc.to_json, toc.to_text):
        assert inspect.signature(fn).parameters["depth"].default == defaults["toc_depth"]
