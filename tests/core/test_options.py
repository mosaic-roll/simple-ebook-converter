"""`build_config()`：前端的原始值 → Config。两个前端共用这一条转换路径。"""

import json

import pytest

from simple_ebook_converter.core.config import (
    DEFAULT_CHAPTER_RE,
    DEFAULT_VOLUME_RE,
    Config,
    LevelRule,
)
from simple_ebook_converter.core.options import (
    OPTIONS,
    Option,
    build_config,
    option_default,
    option_defaults,
)
from simple_ebook_converter.core.replace import Rule

DEFAULTS = option_defaults()


def _values(tmp_path, **overrides) -> dict:
    src = tmp_path / "《测试书》作者：某人.txt"
    src.write_text("第一章 一\n正文\n", encoding="utf-8")
    values = {"input": str(src)}
    values.update(overrides)
    return values


def _config(tmp_path, **overrides) -> Config:
    return build_config(_values(tmp_path, **overrides))


# ---------- 缺省 ----------


def test_defaults_to_config_is_the_default_config(tmp_path):
    cfg = _config(tmp_path)
    expected = Config(input=tmp_path / "《测试书》作者：某人.txt")
    for name in expected.__dataclass_fields__:
        if name == "levels":
            assert [(r.level, r.class_name, r.pattern) for r in cfg.levels] == [
                (r.level, r.class_name, r.pattern) for r in expected.levels
            ]
        else:
            assert getattr(cfg, name) == getattr(expected, name), name


def test_missing_input_is_rejected():
    with pytest.raises(ValueError, match="缺少输入文件"):
        build_config({})


def test_missing_input_file_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="输入文件不存在"):
        build_config({"input": str(tmp_path / "nope.txt")})


def test_blank_is_treated_as_absent(tmp_path):
    """GUI 里清空输入框 = 省略该参数，不是把空值塞进 Config。"""
    cfg = _config(
        tmp_path,
        title="  ",
        author="",
        date=" ",
        language="",
        encoding="",
        line_height="",
        para_spacing="",
        chapter_align="",
        volume_align="",
        preface_title="",
    )
    assert (cfg.title, cfg.author, cfg.date) == (None, "", None)
    assert cfg.encoding == "auto"
    assert cfg.language == Config().language
    assert cfg.line_height == Config().line_height
    assert cfg.para_spacing == Config().para_spacing
    assert cfg.chapter_align == Config().chapter_align
    assert cfg.volume_align == Config().volume_align
    assert cfg.preface_title == Config().preface_title


def test_numbers_accept_strings(tmp_path):
    """GUI 的 Spinbox 给的是字符串，core 负责转成 int。"""
    cfg = _config(tmp_path, max_title_len="12", toc_depth="3", indent="0")
    assert (cfg.max_title_len, cfg.toc_depth, cfg.indent) == (12, 3, 0)


def test_numbers_fall_back_when_blank(tmp_path):
    cfg = _config(tmp_path, max_title_len="", toc_depth=None, indent="")
    assert (cfg.max_title_len, cfg.toc_depth, cfg.indent) == (Config().max_title_len, 6, 2)


def test_bad_number_names_the_option(tmp_path):
    with pytest.raises(ValueError, match="目录深度需为整数"):
        _config(tmp_path, toc_depth="很深")


# ---------- 开关 ----------


def test_negative_flags_are_inverted(tmp_path):
    cfg = _config(tmp_path, no_overwrite="1", no_toc=True, no_clean=True, no_text_cover=True, no_volume=True)
    assert cfg.overwrite is False
    assert cfg.toc_in_spine is False
    assert cfg.clean is False
    assert cfg.text_cover is False
    assert cfg.volume_titles is False


def test_positive_fields_come_from_flags(tmp_path):
    assert _config(tmp_path, no_clean=True).clean is False
    assert _config(tmp_path, no_clean=False).clean is True
    assert _config(tmp_path, no_toc=True).toc_in_spine is False


# ---------- 层级 ----------


def test_presets_default_to_builtin_patterns(tmp_path):
    cfg = _config(tmp_path)
    by_level = {r.level: r for r in cfg.levels}
    assert by_level[2].pattern == DEFAULT_VOLUME_RE
    assert by_level[3].pattern == DEFAULT_CHAPTER_RE
    assert by_level[4].pattern == ""


def test_absent_preset_uses_builtin(tmp_path):
    """键缺失（GUI 没建这个控件）时用内置正则，而不是把该层级关掉。"""
    cfg = build_config(_values(tmp_path))
    assert next(r for r in cfg.levels if r.level == 3).pattern == DEFAULT_CHAPTER_RE


def test_blank_preset_disables_level(tmp_path):
    cfg = _config(tmp_path, volume="", chapter="", section="")
    assert [r.active for r in cfg.levels] == [False, False, False]


def test_extra_levels_from_one_line_per_spec(tmp_path):
    cfg = _config(tmp_path, level="1:^Part\\s+\\d+:part\n5:^\\*\\*\\*:scene\n\n  \n6:^>>\\s:note")
    assert [(r.level, r.class_name) for r in cfg.levels] == [
        (1, "part"),
        (2, "volume"),
        (3, "chapter"),
        (4, "section"),
        (5, "scene"),
        (6, "note"),
    ]


def test_extra_levels_accept_a_tuple(tmp_path):
    """CLI 那边 --level 重复给 click 的就是元组。"""
    cfg = _config(tmp_path, level=("5:^注解:note",))
    assert next(r for r in cfg.levels if r.level == 5).class_name == "note"


def test_extra_level_overrides_preset(tmp_path):
    cfg = _config(tmp_path, volume="^甲", level="2:^乙")
    assert next(r for r in cfg.levels if r.level == 2).pattern == "^乙"


def test_bad_preset_regex_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="卷标题正则非法"):
        _config(tmp_path, volume="(")


def test_bad_extra_level_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="额外层级"):
        _config(tmp_path, level="9:^x")


# ---------- 资源文件 ----------


def test_paths_are_resolved(tmp_path):
    cover = tmp_path / "c.png"
    cover.write_bytes(b"\x89PNG")
    font = tmp_path / "f.ttf"
    font.write_bytes(b"\x00")
    css = tmp_path / "x.css"
    css.write_text("p{}", encoding="utf-8")
    cfg = _config(tmp_path, cover=str(cover), font=str(font), css_file=str(css))
    assert (cfg.cover, cfg.font, cfg.css_file) == (cover, font, css)


def test_missing_asset_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="封面图文件不存在"):
        _config(tmp_path, cover=str(tmp_path / "nope.png"))
    with pytest.raises(ValueError, match="字体文件不存在"):
        _config(tmp_path, font=str(tmp_path / "nope.ttf"))


# ---------- 替换规则 ----------


def test_no_replacement_by_default(tmp_path):
    assert _config(tmp_path).replacements == []


def test_replacements_from_json_text(tmp_path):
    cfg = _config(tmp_path, replace_json=json.dumps([{"pattern": "甲", "scope": "body"}]))
    assert [(r.pattern, r.scope) for r in cfg.replacements] == [("甲", "body")]


def test_replacements_from_file(tmp_path):
    path = tmp_path / "rules.json"
    path.write_text('[{"pattern": "甲", "replace": "乙"}]', encoding="utf-8")
    assert _config(tmp_path, replace_file=str(path)).replacements[0].replace == "乙"


def test_core_ignores_gui_table_rows(tmp_path):
    """GUI 的表格不是 core 的输入：core 内部只接受 JSON，别的键一律不认。"""
    cfg = _config(tmp_path, replacements=[("甲", "乙", "正文"), ("", "忽略", "标题")])
    assert cfg.replacements == []


def test_core_ignores_rule_objects(tmp_path):
    assert _config(tmp_path, replacements=[Rule("甲", "乙", "all")]).replacements == []


def test_replace_json_and_file_together_is_rejected(tmp_path):
    path = tmp_path / "rules.json"
    path.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="只能给一处"):
        _config(tmp_path, replace_json="[]", replace_file=str(path))


# ---------- 选项表自身 ----------


def test_every_option_is_documented():
    for opt in OPTIONS:
        assert opt.help, opt.name
        assert opt.label, opt.name
        assert opt.flags[0].startswith("-"), opt.name


def test_option_names_are_unique():
    names = [opt.name for opt in OPTIONS]
    assert len(set(names)) == len(names)


def test_every_flag_is_a_prefix_of_its_name():
    for opt in OPTIONS:
        assert opt.flags[-1] == "--" + opt.name.replace("_", "-"), opt.name


def test_option_kinds_are_known():
    assert {opt.kind for opt in OPTIONS} <= {"text", "int", "bool", "path", "choice", "multi"}


def test_choices_options_declare_choices():
    for opt in OPTIONS:
        if opt.kind == "choice":
            assert opt.choices, opt.name
            assert option_default(opt) in opt.choices, opt.name


def test_path_options_that_must_exist():
    for opt in OPTIONS:
        if opt.exists:
            assert opt.kind == "path", opt.name
    assert not _option("out").exists
    assert not _option("dump_css").exists


def test_no_option_shadows_another_with_the_same_flag():
    seen: dict[str, str] = {}
    for opt in OPTIONS:
        for flag in opt.flags:
            assert flag not in seen, f"{flag} 同时属于 {seen.get(flag)} 与 {opt.name}"
            seen[flag] = opt.name


def test_inverted_flags_point_at_boolean_fields():
    """反面选项只对布尔字段有意义（`not` 一下就得到正面取值）。"""
    for opt in OPTIONS:
        if opt.invert:
            assert isinstance(getattr(Config(), opt.field, None), bool), opt.name


def test_level_presets_are_levels_two_to_four():
    assert [opt.level for opt in OPTIONS if opt.level] == [2, 3, 4]
    assert [opt.name for opt in OPTIONS if opt.level] == ["volume", "chapter", "section"]


def test_every_option_is_optional_except_input(tmp_path):
    """只给 input 就该能构造出与 Config() 等价的配置，两个前端才敢直接用默认值。"""
    src = tmp_path / "a.txt"
    src.write_text("正文", encoding="utf-8")
    assert build_config({"input": str(src)}) == Config(input=src)


def test_levels_default_to_level_rules():
    assert all(isinstance(r, LevelRule) for r in Config().levels)


def _option(name: str) -> Option:
    return next(opt for opt in OPTIONS if opt.name == name)
