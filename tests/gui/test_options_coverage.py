"""GUI 与 CLI 的双向覆盖：两边发出的键必须完全对得上。

`build_config()` 对**不认识的键静默忽略**，所以「界面里改了、生成没变化」这种 bug
在界面上完全看不出来。这里从两个方向夹住它：

* **正向**（`test_all_options_covered`）：`OPTIONS` 里的每个选项名都要能在
  `option_values()` 产出的字典里找到。少一个 = 界面上有个开关完全没用。
* **反向**（`test_no_unknown_keys`）：`option_values()` 产出的键必须都被 `build_config()`
  认得。多一个 = 有个设置被静默丢弃。

再加一条 CLI 往返：同一组值分别走 CLI 的 `parse()` 和 GUI 的 `build_config_from_ui()`，
两边产出的 `Config` 必须逐字段相等。这条最容易挂，而且挂了就是真 bug。
"""

from __future__ import annotations

import pytest

from click.testing import CliRunner

from simple_ebook_converter.cli.cli import convert
from simple_ebook_converter.core.config import DEFAULTS, Config
from simple_ebook_converter.core.options import CONFIG_KINDS, OPTIONS, build_config
from simple_ebook_converter.gui.build_config_from_ui import (
    LEVEL_NAMES,
    BasicValues,
    IdentifyValues,
    TocSettings,
    TypographyValues,
    UiValues,
    build_config_from_ui,
    option_values,
)


@pytest.fixture
def ui() -> UiValues:
    return UiValues(
        basic=BasicValues(input="", out=""),
        identify=IdentifyValues(levels=dict.fromkeys(LEVEL_NAMES, "")),
        typography=TypographyValues(),
        toc=TocSettings(),
    )


#: **刻意不进界面**的选项，及原因。
#:
#: 界面不是 CLI 的镜像：有些选项在 GUI 里以「按钮/模式」表达而不是常驻字段，有些
#: 根本没有对应的交互。列在这里是为了让「漏了」和「故意不做」可区分 ——
#: 一旦某个条目不再需要，直接从这张表删掉，`test_all_options_covered` 就会因为
#: 它仍不在产出里而失败。
_GUI_ONLY_EXCLUSIONS = {
    # 界面是「替代 / 附加」二选一模式，不同时给两个键（core 判互斥）
    "css_file": "由 CssEditor 的 override 模式产出",
    "css_append": "由 CssEditor 的 append 模式产出",
    # 只在有额外层级/替换规则时才产出，见 option_values()
    "level": "有 level_rows 时才产出",
    "replace_json": "有规则行时才产出",
    "replace_file": "界面用表格编辑规则，不走文件",
    # 三个内置层级是「条件产出」：未动过（None）不写键，显式给了才写。
    # 放在这张表里是为了 test_exclusions_stay_excluded 能守住「默认界面不写它们」。
    "volume": "未动过（None）时不写键，交给 core 缺省",
    "chapter": "未动过（None）时不写键，交给 core 缺省",
    "section": "未动过（None）时不写键，交给 core 缺省",
    "no_volume": "界面用显式空串表达，不用这个旗标",
    # 这些是「一次性动作」，不是设置项
    "dump_css": "界面是「导出内置 CSS」按钮",
    "toc_only": "界面只做生成，不做只输出目录",
    "toc_format": "同上，目录格式不在界面选",
    "toc_file": "界面直接持有目录树，不必经文件往返",
}


def test_all_options_covered(ui: UiValues) -> None:
    """`OPTIONS` 里每个选项，要么被界面收上来，要么在「刻意不做」表里有理由。

    默认产出的 `values` 里 `level` / `replace_json` / `css_*` 不会出现（它们是有条件
    的），所以这里用一张**塞满条件值**的 `UiValues` 来取覆盖面。
    """
    rich = UiValues(
        basic=BasicValues(),
        identify=IdentifyValues(
            levels=dict.fromkeys(LEVEL_NAMES, "^x"),
            level_rows=[{"h": "h5", "class_name": "", "regex": "^x"}],
        ),
        typography=TypographyValues(css_mode="append", css_path="x.css"),
        rules=[("a", "b", "原文")],
    )
    produced = set(option_values(rich))
    unexplained = sorted(
        opt.name for opt in OPTIONS if opt.name not in produced and opt.name not in _GUI_ONLY_EXCLUSIONS
    )
    assert not unexplained, (
        f"这些选项既没被界面收上来、也没在 _GUI_ONLY_EXCLUSIONS 里说明理由：{unexplained}"
    )
    # 反向：排除表里不该有「其实已经产出了」的名字（防止表里留着过时的条目）
    stale = sorted(
        name
        for name in _GUI_ONLY_EXCLUSIONS
        if name in set(option_values(UiValues())) and name not in LEVEL_NAMES
    )
    assert not stale, f"这些键在默认界面就产出了，该从 _GUI_ONLY_EXCLUSIONS 移除：{stale}"


#: `Config` 字段里**没有界面字段**的，及原因。
#:
#: 与 `_GUI_ONLY_EXCLUSIONS` 的区别：那张表说的是「`OPTIONS` 里的选项没有对应控件」，
#: 这张说的是「`Config` 的字段不由用户设置」。两者有重叠（`css_file` 等既是选项也是
#: 字段），是同一件事的两种问法。
_NO_UI_FIELD = {
    # 界面持有目录树对象，生成时直接给 core，不经文件
    # 与 css_append 互斥：界面是二选一模式，override 模式才产出这个键
    "css_file": "由 CssEditor 的 override 模式产出（与 css_append 二选一）",
    "toc_file": "目录在内存里，不走 --toc-file",
    # 「一次性动作」而非设置
    "dump_css": "界面是「导出内置 CSS」按钮",
    "toc_only": "界面只做生成",
    "toc_format": "目录格式不在界面选",
}


def test_all_config_fields_covered() -> None:
    """`Config` 的每个字段都要有来源：界面字段、core 合成，或「没有界面字段」表里有理由。"""
    # 覆盖面要用「塞满条件值」的界面取：条件键在空界面下不产出
    rich = UiValues(
        basic=BasicValues(),
        identify=IdentifyValues(
            levels=dict.fromkeys(LEVEL_NAMES, "^x"),
            level_rows=[{"h": "h5", "class_name": "", "regex": "^x"}],
        ),
        typography=TypographyValues(css_mode="append", css_path="x.css"),
        rules=[("a", "b", "原文")],
    )
    produced = set(option_values(rich))
    # levels / replacements 由 core 从 level / replace_json 合成，不直接出现在 values 里
    synthesized = {"levels", "replacements"}
    unexplained = sorted(set(CONFIG_KINDS) - produced - synthesized - set(_NO_UI_FIELD))
    assert not unexplained, f"这些 Config 字段既没界面来源、也没在 _NO_UI_FIELD 说明：{unexplained}"


# ---------- 反向：不能有多余的键 ----------


def test_no_unknown_keys(ui: UiValues) -> None:
    """`build_config()` 认识的键 = `option_values()` 允许产出的键。"""
    # 三条内置层级的 class 名（volume/chapter/section）不在 CONFIG_KINDS 里 ——
    # 它们由 core 的 _level_specs() 拼进 level，但 GUI 直接用这三个键名传正则
    recognized = {opt.name for opt in OPTIONS if opt.in_config}
    recognized |= {"level", "replace_json", "replace_file", "no_volume", *LEVEL_NAMES}
    extra = sorted(set(option_values(ui)) - recognized)
    assert not extra, f"这些键 core 不会读，等于静默丢弃：{extra}"


# ---------- 键名别写错（`build_config` 静默忽略，所以要显式钉住）----------


def test_toc_key_is_positive(ui: UiValues) -> None:
    """`toc_in_spine` 是正面表述。写成 `no_toc` 会被静默丢弃。"""
    assert "toc_in_spine" in option_values(ui)
    assert "no_toc" not in option_values(ui)


def test_extra_level_key_is_singular(ui: UiValues) -> None:
    """额外层级走单数 `level`；`levels` 是 `Config` 的字段名，不是输入键。"""
    ui.identify.level_rows = [{"h": "h5", "class_name": "", "regex": "^番外"}]
    produced = option_values(ui)
    assert produced["level"] == ["h5:^番外"]
    assert "levels" not in produced


# ---------- 层级三态 ----------


def test_untouched_level_is_omitted() -> None:
    """`None` = 没动过：不写这个键，core 用自己的缺省正则。"""
    values = UiValues(identify=IdentifyValues(levels={"volume": None}))
    assert "volume" not in option_values(values)
    # core 拿到的确实是内置正则
    assert build_config(option_values(values)).levels == DEFAULTS.levels


def test_disabled_level_is_explicit_empty_string() -> None:
    """`""` = 显式关闭：必须写出空串，core 才会用空正则。"""
    values = UiValues(identify=IdentifyValues(levels={"volume": ""}))
    assert option_values(values)["volume"] == ""
    cfg = build_config(option_values(values))
    volume = next(rule for rule in cfg.levels if rule.class_name == "volume")
    assert not volume.active


def test_explicit_level_regex() -> None:
    values = UiValues(identify=IdentifyValues(levels={"chapter": "^序"}))
    cfg = build_config(option_values(values))
    chapter = next(rule for rule in cfg.levels if rule.class_name == "chapter")
    assert chapter.pattern == "^序"


# ---------- `hN[.class]:正则` 规格往返 ----------


@pytest.mark.parametrize(
    "row, expected",
    [
        ({"h": "h1", "class_name": "", "regex": "^Part"}, "h1:^Part"),
        ({"h": "h2", "class_name": "part", "regex": "^Part"}, "h2.part:^Part"),
        # 冒号后整段都是正则，正则里可以自带冒号
        ({"h": "h3", "class_name": "", "regex": "^a:b"}, "h3:^a:b"),
    ],
)
def test_level_spec_format(row: dict, expected: str) -> None:
    """界面拼的规格串必须正是 core 认的格式。"""
    values = UiValues(identify=IdentifyValues(level_rows=[row]))
    assert values.identify.level_specs == [expected]


def test_level_spec_round_trip_through_core() -> None:
    """界面 → core 规格 → `build_levels`：额外层级真的生效了。

    这是最容易坏的一条：core 拼错就静默忽略该层，界面上看不出任何异常。
    """
    values = UiValues(identify=IdentifyValues(level_rows=[{"h": "h5", "class_name": "scene", "regex": "^场景"}]))
    cfg = build_config(option_values(values))
    extra = [rule for rule in cfg.levels if rule.class_name == "scene"]
    assert len(extra) == 1, "额外层级没被 core 认下"
    assert extra[0].level == 5
    assert extra[0].pattern == "^场景"


def test_unfilled_level_row_is_skipped() -> None:
    """空正则的行 = 没填完，跳过（而不是拼出一个 `h1:` 让 core 去猜）。"""
    values = UiValues(identify=IdentifyValues(level_rows=[{"h": "h1", "class_name": "", "regex": "  "}]))
    assert values.identify.level_specs == []


# ---------- CSS 互斥 ----------


def test_css_modes_pick_exactly_one_key() -> None:
    """core 里 `css_file` / `css_append` 互斥，所以任何时候只能产出一个键。"""
    for mode, key in (("append", "css_append"), ("override", "css_file")):
        values = UiValues(typography=TypographyValues(css_mode=mode, css_path="x.css"))
        produced = option_values(values)
        assert key in produced
        assert "css_file" not in produced or key == "css_file"


def test_css_none_produces_no_key() -> None:
    produced = option_values(UiValues(typography=TypographyValues(css_mode="none", css_path="x.css")))
    assert "css_file" not in produced and "css_append" not in produced


def test_css_text_writes_temp_file() -> None:
    """只改内联文本没给路径：落临时文件，core 只认路径。"""
    written: list[str] = []
    values = UiValues(typography=TypographyValues(css_mode="append", css_text="p{margin:0}"))
    produced = option_values(values, write_temp_css=lambda text: written.append(text) or "C:/tmp/x.css")
    assert written == ["p{margin:0}"]
    assert produced["css_append"] == "C:/tmp/x.css"


# ---------- GUI / CLI 逐字段对齐 ----------


def _cli_config(argv: list[str]) -> Config:
    """跑一遍真 CLI，把它交给 `_produce` 的 `Config` 截下来。

    截在 `_produce` 而不是重新实现一遍参数翻译：这里的全部意义就是「CLI 那条路真的
    产出这个」，自己重写一遍等于拿自己当基准，测不出两边分叉。
    """
    from simple_ebook_converter.cli import cli as cli_mod

    captured: list[Config] = []
    original = cli_mod._produce
    cli_mod._produce = captured.append
    try:
        result = CliRunner().invoke(convert, argv)
    finally:
        cli_mod._produce = original
    assert result.exit_code == 0, f"CLI 调用失败：{result.output}"
    assert len(captured) == 1, "CLI 没有产出 Config"
    return captured[0]


def _gui_config(ui: UiValues) -> Config:
    return build_config_from_ui(ui)


#: 逐字段比对的字段名（排除路径类：两边给的形态不同）
_COMPARED = (
    "encoding", "title", "author", "clean", "overwrite", "text_cover", "language",
    "max_title_len", "preface_title", "indent", "line_height", "para_spacing",
    "volume_align", "chapter_align", "toc_depth", "toc_in_spine",
)


def test_defaults_match_cli(ui: UiValues, tmp_path) -> None:
    """空界面 ≈ CLI 的缺省行为。"""
    book = tmp_path / "书.txt"
    book.write_text("第一章\n正文\n", encoding="utf-8")
    # 用「未动过层级」的界面：默认界面必须是 core 的缺省正则
    untouched = UiValues(
        basic=BasicValues(), identify=IdentifyValues(levels=dict.fromkeys(LEVEL_NAMES))
    )
    gui = _gui_config(untouched)
    cli = _cli_config(["--dump-css", str(tmp_path / "x.css")])
    for name in _COMPARED:
        assert getattr(gui, name) == getattr(cli, name), (
            f"{name}: GUI={getattr(gui, name)!r} CLI={getattr(cli, name)!r}"
        )
    assert gui.levels == cli.levels


def test_explicit_values_match_cli(tmp_path) -> None:
    """一组非缺省值，两条路径产出同一个 `Config`。"""
    gui = _gui_config(
        UiValues(
            basic=BasicValues(encoding="gb18030", title="书名", author="作者", clean=False,
                              overwrite=False, text_cover=False, language="ja"),
            identify=IdentifyValues(
                levels={"volume": "", "chapter": "^序", "section": None},
                level_rows=[{"h": "h5", "class_name": "scene", "regex": "^场景"}],
                max_title_len=20,
                preface_title="序言",
            ),
            typography=TypographyValues(
                indent=0, line_height="150%", para_spacing="12px",
                volume_align="left", chapter_align="right",
            ),
            toc=TocSettings(toc_depth=3, toc_in_spine=False),
            rules=[("第(.+?)章", r"第\1节", "原文")],
        )
    )
    cli = _cli_config([
        "--dump-css", str(tmp_path / "x.css"),
        "--encoding", "gb18030", "--title", "书名", "--author", "作者",
        "--no-clean", "--no-overwrite", "--no-text-cover", "--language", "ja",
        "--volume", "", "--chapter", "^序",
        "--level", "h5.scene:^场景",
        "--max-title-len", "20", "--preface-title", "序言",
        "--indent", "0", "--line-height", "150%", "--para-spacing", "12px",
        "--volume-align", "left", "--chapter-align", "right",
        "--toc-depth", "3", "--no-toc",
        "--replace-json", '[{"pattern": "第(.+?)章", "replace": "第\\\\1节", "stage": "raw"}]',
    ])
    for name in _COMPARED:
        assert getattr(gui, name) == getattr(cli, name), (
            f"{name}: GUI={getattr(gui, name)!r} CLI={getattr(cli, name)!r}"
        )
    assert gui.levels == cli.levels
    assert [r.pattern for r in gui.replacements] == [r.pattern for r in cli.replacements]
    assert [r.replace for r in gui.replacements] == [r.replace for r in cli.replacements]
    assert [r.stage for r in gui.replacements] == [r.stage for r in cli.replacements]


# ---------- 校验透传 ----------


def test_bad_date_message_passes_through() -> None:
    """core 的 `ValueError` 消息要能直接展示，所以原样透传。"""
    from simple_ebook_converter.gui.build_config_from_ui import build_config_from_ui as build

    with pytest.raises(ValueError, match="日期格式错误"):
        build(UiValues(basic=BasicValues(date="去年")))


def test_missing_input_path_message_passes_through() -> None:
    with pytest.raises(ValueError, match="输入文件不存在"):
        build_config_from_ui(UiValues(basic=BasicValues(input="C:/绝对不存在/x.txt")))
