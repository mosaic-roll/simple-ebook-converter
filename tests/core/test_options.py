"""`build_config()`：前端的原始值 → Config。两个前端共用这一条转换路径。"""

from pathlib import Path

import pytest

from simple_ebook_converter.core.config import (
    DEFAULT_CHAPTER_RE,
    DEFAULT_VOLUME_RE,
    DEFAULTS,
    Config,
    LevelRule,
)
from simple_ebook_converter.core.options import (
    CONFIG_KINDS,
    OPTIONS,
    Option,
    build_config,
    option_default,
)
from simple_ebook_converter.core.replace import Rule


def _values(tmp_path, **overrides) -> dict:
    src = tmp_path / "《测试书》作者：某人.txt"
    src.write_text("第一章 一\n正文\n", encoding="utf-8")
    return {"input": str(src), **overrides}


def _config(tmp_path, **overrides) -> Config:
    return build_config(_values(tmp_path, **overrides))


def _option(name: str) -> Option:
    return next(opt for opt in OPTIONS if opt.name == name)


# ---------- 缺省 ----------


def test_defaults_to_config_is_the_default_config(tmp_path):
    """只给 input，得到的配置与直接 `Config(input=...)` 一致（`levels` 逐条比）。"""
    cfg = _config(tmp_path)
    expected = Config(input=tmp_path / "《测试书》作者：某人.txt")
    for name in expected.__dataclass_fields__:
        if name == "levels":
            assert [(r.level, r.class_name, r.pattern) for r in cfg.levels] == [
                (r.level, r.class_name, r.pattern) for r in expected.levels
            ]
        else:
            assert getattr(cfg, name) == getattr(expected, name), name


def test_missing_input_is_left_to_the_pipeline():
    """`build_config()` 只翻译值：没给输入不算错，读文件时再报「缺少输入文件」。"""
    assert build_config({}) == Config()


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
        out="",
        dump_css="",
    )
    assert (cfg.title, cfg.author, cfg.date) == (None, "", None)
    assert cfg.encoding == "auto"
    assert cfg.language == DEFAULTS.language
    assert cfg.line_height == DEFAULTS.line_height
    assert cfg.para_spacing == DEFAULTS.para_spacing
    assert cfg.chapter_align == DEFAULTS.chapter_align
    assert cfg.volume_align == DEFAULTS.volume_align
    assert cfg.preface_title == DEFAULTS.preface_title
    assert (cfg.out, cfg.dump_css) == (None, None)


def test_numbers_accept_strings(tmp_path):
    """GUI 的 Spinbox 给的是字符串，core 负责转成 int。"""
    cfg = _config(tmp_path, max_title_len="12", toc_depth="3", indent="0")
    assert (cfg.max_title_len, cfg.toc_depth, cfg.indent) == (12, 3, 0)


def test_numbers_fall_back_when_blank(tmp_path):
    cfg = _config(tmp_path, max_title_len="", toc_depth=None, indent="")
    assert (cfg.max_title_len, cfg.toc_depth, cfg.indent) == (DEFAULTS.max_title_len, 6, 2)


def test_bad_number_names_the_option(tmp_path):
    with pytest.raises(ValueError, match="目录深度需为整数"):
        _config(tmp_path, toc_depth="很深")


# ---------- 开关 ----------


def test_switches_take_positive_values(tmp_path):
    """前端收上来的已经是 `Config` 的正面语义，`build_config()` 不做取反。"""
    cfg = _config(tmp_path, overwrite=False, toc_in_spine=False, clean=False, text_cover=False)
    assert cfg.overwrite is False
    assert cfg.toc_in_spine is False
    assert cfg.clean is False
    assert cfg.text_cover is False


def test_switches_default_to_on(tmp_path):
    """`--no-xxx` 关掉的是默认开启的功能，所以缺省都是 True。"""
    cfg = _config(tmp_path)
    for name in ("overwrite", "toc_in_spine", "clean", "text_cover"):
        assert getattr(cfg, name) is True, name


# ---------- 产出开关 ----------


def test_output_switches_land_on_config(tmp_path):
    """产出方式也是 `Config` 字段：前端收完值就直接交回 core。"""
    cfg = _config(tmp_path, toc_only=True, toc_format="json", dump_css=str(tmp_path / "a.css"))
    assert cfg.toc_only is True
    assert cfg.toc_format == "json"
    assert cfg.dump_css == tmp_path / "a.css"


# ---------- 层级 ----------


def test_presets_default_to_builtin_patterns(tmp_path):
    cfg = _config(tmp_path)
    by_level = {r.level: r for r in cfg.levels}
    assert by_level[2].pattern == DEFAULT_VOLUME_RE
    assert by_level[3].pattern == DEFAULT_CHAPTER_RE
    # 不再有无级别的默认节预设；h4 只能通过 --level h4.xxx:正则 显式加
    assert 4 not in by_level


def test_absent_preset_uses_builtin(tmp_path):
    """键缺失（GUI 没建这个控件）时用内置正则，而不是把该层级关掉。"""
    cfg = build_config(_values(tmp_path))
    assert next(r for r in cfg.levels if r.level == 3).pattern == DEFAULT_CHAPTER_RE


def test_blank_preset_disables_level(tmp_path):
    cfg = _config(tmp_path, volume="", chapter="")
    assert [r.active for r in cfg.levels] == [False, False]


def test_extra_levels_from_one_line_per_spec(tmp_path):
    specs = "h1.part:^Part\\s+\\d+\nh5.scene:^\\*\\*\\*\n\n  \nh6.note:^>>\\s"
    cfg = _config(tmp_path, level=specs)
    assert [(r.level, r.class_name) for r in cfg.levels] == [
        (1, "part"),
        (2, "volume"),
        (3, "chapter"),
        (5, "scene"),
        (6, "note"),
    ]


def test_extra_levels_accept_a_tuple(tmp_path):
    """CLI 那边 --level 重复给 click 的就是元组。"""
    cfg = _config(tmp_path, level=("h5.note:^注解",))
    assert next(r for r in cfg.levels if r.level == 5).class_name == "note"


def test_extra_level_without_class_has_no_class(tmp_path):
    cfg = _config(tmp_path, level="h1:^第[0-9]+部")
    assert next(r for r in cfg.levels if r.level == 1).class_name == ""


def test_extra_level_at_preset_level_appends_behind_it(tmp_path):
    """`--level h2:…` 不再顶掉卷，而是同级排在卷后面（内置优先）。"""
    cfg = _config(tmp_path, volume="^甲", level="h2:^乙")
    assert [(r.class_name, r.pattern) for r in cfg.levels if r.level == 2] == [
        ("volume", "^甲"),
        ("", "^乙"),
    ]


def test_extra_level_with_preset_class_joins_the_preset_rule(tmp_path):
    """`--level h2.volume:…` 只新增一条：内置那条已经被 `--volume` 的值顶掉了。"""
    cfg = _config(tmp_path, volume="^甲", level="h2.volume:^丙")
    assert [(r.class_name, r.pattern) for r in cfg.levels if r.level == 2] == [
        ("volume", "^甲"),
        ("volume", "^丙"),
    ]


def test_bad_preset_regex_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="卷标题正则非法"):
        _config(tmp_path, volume="(")


def test_bad_extra_level_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="额外层级"):
        _config(tmp_path, level="h9:^x")


def test_levels_default_to_level_rules():
    assert all(isinstance(r, LevelRule) for r in DEFAULTS.levels)


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


def test_css_append_is_resolved(tmp_path):
    css = tmp_path / "extra.css"
    css.write_text("p{}", encoding="utf-8")
    assert _config(tmp_path, css_append=str(css)).css_append == css


def test_missing_asset_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="封面图不存在"):
        _config(tmp_path, cover=str(tmp_path / "nope.png"))
    with pytest.raises(ValueError, match="正文字体不存在"):
        _config(tmp_path, font=str(tmp_path / "nope.ttf"))
    with pytest.raises(ValueError, match="外部 CSS 文件不存在"):
        _config(tmp_path, css_file=str(tmp_path / "nope.css"))
    with pytest.raises(ValueError, match="附加 CSS 文件不存在"):
        _config(tmp_path, css_append=str(tmp_path / "nope.css"))


def test_output_paths_need_not_exist(tmp_path):
    """输出路径不要求已存在：本来就是要写出来的。"""
    cfg = _config(tmp_path, out=str(tmp_path / "deep" / "a.epub"), dump_css=str(tmp_path / "b.css"))
    assert cfg.out == tmp_path / "deep" / "a.epub"
    assert cfg.dump_css == tmp_path / "b.css"


# ---------- 替换规则 ----------


def test_no_replacement_by_default(tmp_path):
    assert _config(tmp_path).replacements == []


def test_replacements_from_file(tmp_path):
    path = tmp_path / "rules.json"
    path.write_text('[{"pattern": "甲", "replace": "乙", "stage": "html"}]', encoding="utf-8")
    cfg = _config(tmp_path, replace_rules=str(path))
    assert [(r.pattern, r.replace, r.stage) for r in cfg.replacements] == [("甲", "乙", "html")]


def test_core_ignores_gui_table_rows(tmp_path):
    """GUI 的表格不是 core 的输入：core 内部只接受 JSON，别的键一律不认。"""
    cfg = _config(tmp_path, replacements=[("甲", "乙", "正文"), ("", "忽略", "标题")])
    assert cfg.replacements == []


def test_core_ignores_rule_objects(tmp_path):
    assert _config(tmp_path, replacements=[Rule("甲", "乙", "all")]).replacements == []


# ---------- 选项表自身 ----------


def test_every_option_is_documented():
    for opt in OPTIONS:
        assert opt.help, opt.name
        assert opt.label, opt.name
        assert opt.flags[0].startswith("-"), opt.name


def test_option_names_are_unique():
    names = [opt.name for opt in OPTIONS]
    assert len(set(names)) == len(names)


def test_long_flag_comes_from_name_or_explicit_override():
    """长旗标默认按名字推：正面 `--xxx`，反面 `--no-xxx`；个别显式 `flag` 覆盖。"""
    for opt in OPTIONS:
        expected = opt.flag or ("no-" if opt.negative else "") + opt.name.replace("_", "-")
        assert opt.flags[-1] == f"--{expected}", opt.name


def test_documented_flag_names_stay_compatible():
    """`--no-volume` / `--no-toc` 是设计文档写死的旗标，名字与字段不同，不能漂移。"""
    assert _option("no_volume").flags == ("--no-volume",)
    assert _option("toc_in_spine").flags == ("--no-toc",)


def test_no_volume_disables_volume_level(tmp_path):
    """`--no-volume` = 清空卷正则；显式给了 `--volume` 时以正则为准。"""
    cfg = _config(tmp_path, no_volume=True)
    assert next(r for r in cfg.levels if r.level == 2).active is False
    cfg = _config(tmp_path, no_volume=True, volume="^甲")
    assert next(r for r in cfg.levels if r.level == 2).pattern == "^甲"


def test_option_kinds_come_from_config_annotations():
    """取值类型不写第二份：`Config` 字段按注解推，其余看 `value_type`。"""
    assert set(CONFIG_KINDS.values()) <= {str, int, bool, Path}
    for opt in OPTIONS:
        if opt.in_config:
            assert opt.name in CONFIG_KINDS, opt.name
            assert opt.kind is CONFIG_KINDS[opt.name], opt.name
        else:
            assert opt.kind is opt.value_type, opt.name


def test_option_defaults_come_from_config():
    """选项缺省值就是 `Config` 的字段缺省值：改一处，两个前端一起变。"""
    for opt in OPTIONS:
        if opt.in_config:
            assert option_default(opt) == getattr(DEFAULTS, opt.name), opt.name


def test_empty_defaults_for_options_outside_config():
    for name in ("replace_rules",):
        assert option_default(_option(name)) == ""
    assert option_default(_option("no_volume")) is False
    assert option_default(_option("level")) == ()


def test_build_config_never_mutates_the_shared_defaults(tmp_path):
    """`DEFAULTS` 只是缺省值模板：谁都不许改它，否则两次调用会互相污染。"""
    rules = tmp_path / "rules.json"
    rules.write_text('[{"pattern": "甲"}]', encoding="utf-8")
    before = [(r.level, r.pattern) for r in DEFAULTS.levels]
    _config(tmp_path, volume="^甲", clean=False, replace_rules=str(rules))
    assert [(r.level, r.pattern) for r in DEFAULTS.levels] == before
    assert DEFAULTS.clean is True


def test_choices_options_declare_choices():
    for opt in OPTIONS:
        if opt.choices:
            assert option_default(opt) in opt.choices, opt.name


def test_output_options_are_not_required_to_exist():
    for name in ("out", "dump_css"):
        assert _option(name).output, name
    for opt in OPTIONS:
        if opt.kind is Path and not opt.output:
            assert opt.in_config or opt.name == "replace_rules", opt.name


def test_no_option_shadows_another_with_the_same_flag():
    seen: dict[str, str] = {}
    for opt in OPTIONS:
        for flag in opt.flags:
            assert flag not in seen, f"{flag} 同时属于 {seen.get(flag)} 与 {opt.name}"
            seen[flag] = opt.name


def test_negative_options_point_at_boolean_fields():
    """反面选项只对布尔字段有意义（`not` 一下就得到正面取值）。"""
    for opt in OPTIONS:
        if opt.negative:
            assert opt.kind is bool, opt.name


def test_level_presets_are_levels_two_to_three():
    assert [opt.level for opt in OPTIONS if opt.level] == [2, 3]
    assert [opt.name for opt in OPTIONS if opt.level] == ["volume", "chapter"]


def test_every_option_is_optional_except_input(tmp_path):
    """只给 input 就该能构造出与 Config() 等价的配置，两个前端才敢直接用默认值。"""
    src = tmp_path / "a.txt"
    src.write_text("正文", encoding="utf-8")
    assert build_config({"input": str(src)}) == Config(input=src)
