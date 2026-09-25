from sec_core.config import (
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
