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
from simple_ebook_converter.core.levels import parse_level_spec
from simple_ebook_converter.core.options import (
    CONFIG_KINDS,
    OPTIONS,
    Option,
    build_config,
    is_valid,
    option_default,
    option_groups,
)
from simple_ebook_converter.core.pipeline import resolve
from simple_ebook_converter.core.replace import Rule


def _values(tmp_path, **overrides) -> dict:
    src = tmp_path / "《测试书》作者：某人.txt"
    src.write_text("第一章 一\n正文\n", encoding="utf-8")
    return {"input": str(src), **overrides}


def _config(tmp_path, **overrides) -> Config:
    return build_config(_values(tmp_path, **overrides))


def _option(name: str) -> Option:
    return next(opt for opt in OPTIONS if opt.name == name)


def _field_options() -> list[Option]:
    return [opt for opt in OPTIONS if opt.in_config]


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


# ---------- 默认 ----------


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
        para_align="",
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
    assert cfg.para_align == DEFAULTS.para_align
    assert cfg.preface_title == DEFAULTS.preface_title
    assert (cfg.out, cfg.dump_css) == (None, None)


def test_numbers_accept_strings(tmp_path):
    """GUI 的 Spinbox 给的是字符串，core 负责转成 int。"""
    cfg = _config(tmp_path, max_title_len="12", toc_depth="3", indent="0")
    assert (cfg.max_title_len, cfg.toc_depth, cfg.indent) == (12, 3, 0)


def test_numbers_fall_back_when_blank(tmp_path):
    cfg = _config(tmp_path, max_title_len="", toc_depth=None, indent="")
    assert (cfg.max_title_len, cfg.toc_depth, cfg.indent) == (
        DEFAULTS.max_title_len,
        6,
        2,
    )


def test_bad_number_names_the_option(tmp_path):
    with pytest.raises(ValueError, match="目录深度需为整数"):
        _config(tmp_path, toc_depth="很深")


# ---------- 开关 ----------


def test_switches_take_positive_values(tmp_path):
    """前端收上来的已经是 `Config` 的正面语义，`build_config()` 不做取反。"""
    cfg = _config(
        tmp_path, overwrite=False, toc_in_spine=False, clean=False, text_cover=False
    )
    assert cfg.overwrite is False
    assert cfg.toc_in_spine is False
    assert cfg.clean is False
    assert cfg.text_cover is False


def test_switches_default_to_on(tmp_path):
    """`--no-xxx` 关掉的是默认开启的功能，所以默认都是 True。"""
    cfg = _config(tmp_path)
    for name in ("overwrite", "toc_in_spine", "clean", "text_cover"):
        assert getattr(cfg, name) is True, name


# ---------- 产出开关 ----------


def test_output_switches_land_on_config(tmp_path):
    """产出方式也是 `Config` 字段：前端收完值就直接交回 core。"""
    cfg = _config(
        tmp_path, toc_only=True, toc_format="json", dump_css=str(tmp_path / "a.css")
    )
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


def test_extra_levels_are_all_kept_in_order(tmp_path):
    """额外层级给多少条就收多少条，按级别排、同级按给的顺序。"""
    cfg = _config(
        tmp_path,
        level=[
            LevelRule(1, r"^Part\s+\d+", "part"),
            LevelRule(5, r"^\*\*\*", "scene"),
            LevelRule(6, r"^>>\s", "note"),
        ],
    )
    assert [(r.level, r.class_name) for r in cfg.levels] == [
        (1, "part"),
        (2, "volume"),
        (3, "chapter"),
        (5, "scene"),
        (6, "note"),
    ]


def test_extra_levels_accept_a_tuple(tmp_path):
    """CLI 那边 `--level` 重复给 click 的就是元组，拆完传进来还是元组。"""
    rules = tuple(parse_level_spec(s) for s in ("h5.note:^注解",))
    cfg = _config(tmp_path, level=rules)
    assert next(r for r in cfg.levels if r.level == 5).class_name == "note"


def test_extra_level_without_class_has_no_class(tmp_path):
    cfg = _config(tmp_path, level=[parse_level_spec("h1:^第[0-9]+部")])
    assert next(r for r in cfg.levels if r.level == 1).class_name == ""


def test_extra_level_at_preset_level_appends_behind_it(tmp_path):
    """额外层级写在 h2 不顶掉卷，而是同级排在卷后面（内置优先）。"""
    cfg = _config(tmp_path, volume="^甲", level=[parse_level_spec("h2:^乙")])
    assert [(r.class_name, r.pattern) for r in cfg.levels if r.level == 2] == [
        ("volume", "^甲"),
        ("", "^乙"),
    ]


def test_extra_level_with_preset_class_joins_the_preset_rule(tmp_path):
    """class 撞上预设的也只新增一条：内置那条已经被 `--volume` 的值顶掉了。"""
    cfg = _config(tmp_path, volume="^甲", level=[parse_level_spec("h2.volume:^丙")])
    assert [(r.class_name, r.pattern) for r in cfg.levels if r.level == 2] == [
        ("volume", "^甲"),
        ("volume", "^丙"),
    ]


def test_bad_extra_level_is_rejected(tmp_path):
    """层级正则在 `build_rules()` 就拦下，不留到 `parse()`。"""
    with pytest.raises(ValueError, match="额外层级"):
        _config(tmp_path, level=[LevelRule(4, "(", "part")])


def test_bad_preset_regex_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="卷标题正则非法"):
        _config(tmp_path, volume="(")


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


def test_empty_cover_path_turns_discovery_off(tmp_path):
    """`--cover ""` 与 GUI 清空封面框同义：显式说不要封面。

    `_path()` 会把空串归一成 `None`（`Config.cover` 的类型要求），不在这儿记一笔的话
    「显式不要」就被抹成了「没给」，自动发现又去同目录翻一张 cover.png 出来。
    """
    assert _config(tmp_path, cover="").cover_discovery is False


def test_absent_cover_keeps_discovery_on(tmp_path):
    """没给 `--cover` 不碰发现开关——那才是「没指定，该去找」。"""
    assert _config(tmp_path).cover_discovery is True


def test_empty_cover_path_beats_the_discovery_switch(tmp_path):
    """空路径压过发现开关，与 GUI 一致。

    GUI 那边封面框清空时，`cover_for("")` 在看 `discovery` 之前就返回 None 了——
    显式的路径状态比开关更具体。命令行不能有另一种解释。
    """
    assert _config(tmp_path, cover="", cover_discovery=True).cover_discovery is False


def test_output_paths_need_not_exist(tmp_path):
    cfg = _config(
        tmp_path,
        out=str(tmp_path / "deep" / "a.epub"),
        dump_css=str(tmp_path / "b.css"),
    )
    assert cfg.out == tmp_path / "deep" / "a.epub"
    assert cfg.dump_css == tmp_path / "b.css"


# ---------- 替换规则 ----------


def test_no_replacement_by_default(tmp_path):
    assert _config(tmp_path).replacements == []


def test_replacements_from_file(tmp_path):
    path = tmp_path / "rules.json"
    path.write_text(
        '[{"pattern": "甲", "replace": "乙", "stage": "html"}]', encoding="utf-8"
    )
    cfg = _config(tmp_path, replace_rules=str(path))
    assert [(r.pattern, r.replace, r.stage) for r in cfg.replacements] == [
        ("甲", "乙", "html")
    ]


def test_core_ignores_gui_table_rows(tmp_path):
    """GUI 的表格不是 core 的输入：core 内部只接受 JSON，别的键一律不认。"""
    cfg = _config(tmp_path, replacements=[("甲", "乙", "正文"), ("", "忽略", "标题")])
    assert cfg.replacements == []


def test_core_ignores_rule_objects(tmp_path):
    assert _config(tmp_path, replacements=[Rule("甲", "乙", "all")]).replacements == []


def test_replacements_kwarg_wins_over_replace_rules(tmp_path):
    """GUI 走表格，不读 `--replace-rules`；给了关键字参数就不该再碰那个文件。"""
    path = tmp_path / "rules.json"
    path.write_text('[{"pattern": "丙", "replace": "丁"}]', encoding="utf-8")
    cfg = build_config(
        _values(tmp_path, replace_rules=str(path)),
        replacements=[Rule("甲", "乙", "html")],
    )
    assert [(r.pattern, r.replace) for r in cfg.replacements] == [("甲", "乙")]


def test_replacements_kwarg_accepts_an_empty_list(tmp_path):
    """空列表是"确实没有规则"，与"没给，去读文件"要分得开。"""
    cfg = build_config(_values(tmp_path), replacements=[])
    assert cfg.replacements == []


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
        expected = opt.flag or ("no-" if opt.negative else "") + opt.name.replace(
            "_", "-"
        )
        assert opt.flags[-1] == f"--{expected}", opt.name


def test_flag_names_differ_from_field_names():
    """`--no-volume` / `--no-toc-page` 的旗标与字段不同名，显式写死，改名要连测试一起改。"""
    assert _option("no_volume").flags == ("--no-volume",)
    assert _option("toc_in_spine").flags == ("--no-toc-page",)


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
    """选项默认值就是 `Config` 的字段默认值：改一处，两个前端一起变。"""
    for opt in OPTIONS:
        if opt.in_config:
            assert option_default(opt) == getattr(DEFAULTS, opt.name), opt.name


def test_empty_defaults_for_options_outside_config():
    for name in ("replace_rules",):
        assert option_default(_option(name)) == ""
    assert option_default(_option("no_volume")) is False
    assert option_default(_option("level")) == ()


def test_build_config_never_mutates_the_shared_defaults(tmp_path):
    """`DEFAULTS` 只是默认值模板：谁都不许改它，否则两次调用会互相污染。"""
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
    assert [opt.preset_level for opt in OPTIONS if opt.preset_level] == [2, 3]
    assert [opt.name for opt in OPTIONS if opt.preset_level] == ["volume", "chapter"]


def test_every_option_is_optional_except_input(tmp_path):
    """只给 input 就该能构造出与 Config() 等价的配置，两个前端才敢直接用默认值。"""
    src = tmp_path / "a.txt"
    src.write_text("正文", encoding="utf-8")
    assert build_config({"input": str(src)}) == Config(input=src)


# ------------------------------------------------------------------ is_valid

#: (字段, 合法值, 非法值)。空值一律合法——留空就是「用默认值」，没有第三种意思。
VALIDITY = [
    ("toc_depth", 3, 99),
    ("indent", 2, -1),
    ("max_title_len", 35, 0),
    ("volume_align", "center", "中间"),
    ("chapter_align", "justify", "中间"),
    ("para_align", "left", "中间"),
    ("volume", "第.{1,10}卷", "("),
    ("chapter", "第.{1,10}章", "["),
    ("exclude", "目录", "(?"),
    ("date", "2024-05-13", "瞎写"),
]


@pytest.mark.parametrize(("name", "good", "bad"), VALIDITY)
def test_is_valid_accepts_a_good_value(name, good, bad):
    assert is_valid(name, good) is True


@pytest.mark.parametrize(("name", "good", "bad"), VALIDITY)
def test_is_valid_rejects_a_bad_value(name, good, bad):
    assert is_valid(name, bad) is False


@pytest.mark.parametrize("name", [name for name, _, _ in VALIDITY])
def test_is_valid_treats_none_as_the_default(name):
    """空就是「用默认值」，合法。"""
    assert is_valid(name, None) is True


def test_is_valid_uses_the_builtin_pattern_for_an_unset_level_option():
    """层级选项给 `None` 要按内置正则判，不能拿 `None` 当正则去编译。

    `_level_rules()` 遇到没指定会用内置正则填上，所以「没指定」必然合法——
    直接 `re.compile(None)` 会误报成非法。
    """
    assert is_valid("volume", None) is True
    assert is_valid("chapter", None) is True


@pytest.mark.parametrize(("name", "good", "bad"), VALIDITY)
def test_is_valid_agrees_with_resolve(name, good, bad, tmp_path):
    """同一个值，`is_valid` 与 `resolve` 必须给同一个结论。

    存盘和生成对同一个值看法不一致是最坏的组合：配置存下了却生成不了，或反过来。
    这条断言把「同一套规则」钉住——不是比对硬编码的期望值，而是比对两条真实路径。

    比的是 `resolve()` 而不是 `build_config()`：后者只做翻译，不取值域校验
    （那是 `pipeline.resolve()` 的职责），拿它当基准会把 `toc_depth=99` 误判成放行。
    """
    for value, expected in ((good, True), (bad, False)):
        assert is_valid(name, value) is expected
        try:
            resolve(build_config({"input": _any_input(tmp_path), name: value}))
        except ValueError:
            assert expected is False, (
                f"{name}={value!r} 被 is_valid 放行却被 resolve 拒"
            )
        else:
            assert expected is True, f"{name}={value!r} 被 resolve 放行却被 is_valid 拒"


def test_is_valid_ignores_a_non_config_option():
    """不进 `Config` 的选项没有字段级约束，恒为合法。

    多值项 `--level` 不归它管——那是一条规则一条校验，走 `levels.is_valid_level()`。
    """
    assert is_valid("replace_rules", "任意路径") is True


def _any_input(tmp_path: Path) -> str:
    src = tmp_path / "in.txt"
    src.write_text("正文", encoding="utf-8")
    return str(src)
