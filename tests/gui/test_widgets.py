"""无头环境下实例化真实控件，验证构造与基本行为。

这批测试**能真正抓住**纯数据测试抓不到的问题：属性名打错（`Entry` 没有
`textwrap`）、style 名不存在、grid 参数传错、`retag_all()` 漏控件。纯数据测试
只 import 模块，这些要真正建控件才会暴露。

Tk 需要一个 display。CI 上没有 display 时整个文件 skip（`conftest` 里已配好
`tk_root` fixture 的跳过逻辑）。
"""

from __future__ import annotations

from pathlib import Path

import tkinter as tk

import pytest
from tkinter import ttk

# 没装 GUI 可选依赖时整文件跳过（必须在导入 GUI 模块之前）
pytest.importorskip("sv_ttk")

from simple_ebook_converter.core.replace import Rule, rules_from_rows
from simple_ebook_converter.gui import fonts, theme
from simple_ebook_converter.gui.build_config_from_ui import (
    CSS_APPEND,
    CSS_NONE,
    CSS_OVERRIDE,
    LEVEL_NAMES,
    BasicValues,
    IdentifyValues,
    TocSettings,
    TypographyValues,
    UiValues,
    entry_id,
)
from simple_ebook_converter.gui.settings import Settings
from simple_ebook_converter.gui.tabs.basic import BasicTab
from simple_ebook_converter.gui.tabs.identify import IdentifyTab
from simple_ebook_converter.gui.tabs.replace import ReplaceTab
from simple_ebook_converter.gui.tabs.typography import TypographyTab
from simple_ebook_converter.gui.widgets.css_editor import CssEditor
from simple_ebook_converter.gui.widgets.extra_levels import ExtraLevelsEditor
from simple_ebook_converter.gui.widgets.path_entry import PathEntry
from simple_ebook_converter.gui.widgets.regex_entry import regex_entry
from simple_ebook_converter.gui.widgets.replacement_editor import ReplacementEditor
from simple_ebook_converter.gui.widgets.scroll_frame import BINDTAG, ScrollFrame
from simple_ebook_converter.gui.widgets.status_bar import StatusBar
from simple_ebook_converter.gui.widgets.toc_panel import CHECK, RESULT, TITLE, TocPanel


# ---------- 字体 / 主题 ----------


def test_bind_fonts_resolves_both_chains(tk_root) -> None:
    """两条链都要解析出真实族名，否则界面静默退回 Tk 默认。"""
    fonts.bind_fonts(tk_root)
    for key in ("ui", "mono"):
        family = fonts.actual_family(key)
        assert family and isinstance(family, str)
        assert len(family) > 1


def test_font_returns_tuple_not_none(tk_root) -> None:
    """`font()` 永远给可用的元组：塞 `None` 进 ttk 会画出一片空白。"""
    fonts.bind_fonts(tk_root)
    assert fonts.font("ui")[0]
    assert fonts.font("mono")[0]


def test_theme_uses_sv_ttk(tk_root) -> None:
    """主题走 sv_ttk，不再自己配一堆 `TButton`/`TLabel`。"""
    from simple_ebook_converter.gui import theme as theme_mod

    fonts.bind_fonts(tk_root)
    style = theme.apply(tk_root)
    assert style.theme_use() == theme_mod.THEME


def test_theme_configures_mono_fonts(tk_root) -> None:
    """等宽 style 必须真的挂上字体：正则/CSS/替换表格都靠它。"""
    fonts.bind_fonts(tk_root)
    style = theme.apply(tk_root)
    assert style.lookup("Mono.TEntry", "font")
    assert style.lookup("Mono.Treeview", "font")


# ---------- ScrollFrame ----------


def test_scroll_frame_tags_all_descendants(tk_root) -> None:
    """滚轮靠 bindtag，深层控件也必须挂上 —— 只扫两层会让第四层以下滚不动。"""
    sf = ScrollFrame(tk_root)
    outer = ttk.Frame(sf.inner)
    inner = ttk.Frame(outer)
    deepest = ttk.Entry(inner)
    deepest.pack()
    sf.retag_all()
    # 递归到底：canvas / vbar / inner / outer / inner / Entry 六层都要有 tag
    for widget in (sf.canvas, sf.vbar, sf.inner, outer, inner, deepest):
        assert BINDTAG in widget.bindtags()


def test_scroll_frame_wheel_delta_signs() -> None:
    """滚轮归一：往上 = +1，往下 = -1；X11 的 Button-4/5 没有 delta 属性。"""
    from simple_ebook_converter.gui.widgets.scroll_frame import _wheel_delta

    class Ev:
        def __init__(self, **kw):
            self.__dict__.update(kw)

    assert _wheel_delta(Ev(delta=120)) == 1
    assert _wheel_delta(Ev(delta=-120)) == -1
    assert _wheel_delta(Ev(delta=1)) == 1  # macOS 小步长也走一格
    assert _wheel_delta(Ev(num=4)) == 1
    assert _wheel_delta(Ev(num=5)) == -1
    assert _wheel_delta(Ev(num=4, delta=120)) == 1  # num 优先
    assert _wheel_delta(Ev()) == 0


def test_scroll_frame_wheel_shifts_to_pass_through() -> None:
    """Shift 要放行给焦点控件（X11 上带 Shift 的 Button-4 事件类型不变）。"""
    from simple_ebook_converter.gui.widgets.scroll_frame import _is_shift

    class Ev:
        def __init__(self, state):
            self.state = state

    assert _is_shift(Ev(1)) is True
    assert _is_shift(Ev(0)) is False


# ---------- RegexEntry ----------


def test_regex_entry_is_single_line_with_horizontal_scroll(tk_root) -> None:
    """正则要能不折行地看：`Text` 做不到，Entry 内容超出时内建横滚。"""
    entry = regex_entry(tk_root)
    assert entry.get() == ""
    # Entry 有 xview，Text 没有 —— 这正是选它的理由
    assert hasattr(entry, "xview")


# ---------- PathEntry ----------


def test_path_entry_flags_missing_input(tk_root) -> None:
    """输入文件不存在 = 红（必须先准备好）。"""
    from simple_ebook_converter.gui.widgets.path_entry import ERROR

    entry = PathEntry(tk_root, kind="input")
    entry.insert(0, "C:/绝对不存在/x.txt")
    entry.validate()
    assert entry.hint.cget("text")
    assert not entry.is_valid()
    del ERROR


def test_path_entry_warns_but_does_not_block_output_dir(tk_root) -> None:
    """输出目录不存在只该黄框：生成时会 mkdir，拦下来是错的。"""
    from simple_ebook_converter.gui.widgets.path_entry import OK

    entry = PathEntry(tk_root, kind="output")
    entry.insert(0, "C:/绝对不存在的目录/x.epub")
    entry.validate()
    assert entry.hint.cget("text"), "应有提示"
    assert entry.is_valid(), "输出目录不存在不该判为无效"
    del OK


def test_path_entry_rejects_directory_as_output(tk_root) -> None:
    entry = PathEntry(tk_root, kind="output")
    entry.insert(0, str(tk_root.tk.call("pwd")) or "C:/")
    entry.validate()
    assert "目录" in entry.hint.cget("text")


def test_path_entry_empty_is_ok(tk_root) -> None:
    """空路径视同未填，不校验（交给生成时拦）。"""
    entry = PathEntry(tk_root, kind="input")
    entry.validate()
    assert entry.hint.cget("text") == ""
    assert entry.get_path() is None


# ---------- ExtraLevelsEditor ----------


def test_extra_levels_builds_specs(tk_root) -> None:
    ed = ExtraLevelsEditor(tk_root)
    ed.set([{"h": "h5", "class_name": "scene", "regex": "^场景"}])
    assert ed.get_specs() == ["h5.scene:^场景"]


def test_extra_levels_skips_unfilled_row(tk_root) -> None:
    """空正则的行跳过，不拼出 `h1:` 让 core 去猜。"""
    ed = ExtraLevelsEditor(tk_root)
    ed.set([{"h": "h1", "class_name": "", "regex": "  "}])
    assert ed.get_specs() == []


def test_extra_levels_rejects_duplicate_hN(tk_root) -> None:
    """hN 唯一：冲突要标红并跳过。"""
    ed = ExtraLevelsEditor(tk_root)
    ed.set([
        {"h": "h1", "class_name": "", "regex": "^a"},
        {"h": "h1", "class_name": "", "regex": "^b"},
    ])
    assert len(ed.get_specs()) == 1, "重复的 hN 应只留一条"


def test_extra_levels_allows_reusing_disabled_builtin_hN(tk_root) -> None:
    """内置层级被关掉时，它的 hN 可以拿来做额外层级。"""
    ed = ExtraLevelsEditor(tk_root, is_builtin_enabled=lambda name: name != "volume")
    ed.set([{"h": "h2", "class_name": "", "regex": "^部"}])
    assert ed.get_specs() == ["h2:^部"]


def test_extra_levels_rejects_bad_class_name(tk_root) -> None:
    ed = ExtraLevelsEditor(tk_root)
    ed.set([{"h": "h1", "class_name": "1bad", "regex": "^a"}])
    assert ed.get_specs() == []


def test_extra_levels_rejects_bad_regex(tk_root) -> None:
    ed = ExtraLevelsEditor(tk_root)
    ed.set([{"h": "h1", "class_name": "", "regex": "([unclosed"}])
    assert ed.get_specs() == []


def test_extra_levels_spec_allows_colon_in_regex(tk_root) -> None:
    """冒号后整段都是正则，正则里可以自带冒号。"""
    ed = ExtraLevelsEditor(tk_root)
    ed.set([{"h": "h1", "class_name": "", "regex": "^a:b"}])
    assert ed.get_specs() == ["h1:^a:b"]


# ---------- ReplacementEditor ----------


def test_replacement_editor_round_trip(tk_root) -> None:
    ed = ReplacementEditor(tk_root)
    ed.set_rows([("第(.+?)章", r"第\1节", "原文")])
    assert ed.get_rows() == [("第(.+?)章", r"第\1节", "原文")]
    rules = ed.get_rules()
    assert rules == [Rule(r"第(.+?)章", r"第\1节", "raw")]


def test_replacement_editor_skips_empty_rows(tk_root) -> None:
    """`查找` 为空的行忽略 —— 删行后不该留下空洞。"""
    ed = ReplacementEditor(tk_root)
    ed.set_rows([("a", "1", "原文"), ("", "2", "原文")])
    assert len(ed.get_rules()) == 1


def test_replacement_editor_json_matches_core_format(tk_root) -> None:
    """表格产出的 JSON 必须是 core 认的形状（`stage` 显式写出）。"""
    import json

    ed = ReplacementEditor(tk_root)
    ed.set_rows([("a", "1", "原文")])
    data = json.loads(ed.get_json())
    assert data == [{"pattern": "a", "replace": "1", "stage": "raw"}]


def test_replacement_editor_preserves_order(tk_root) -> None:
    """顺序即语义：规则按表格显示顺序执行。"""
    ed = ReplacementEditor(tk_root)
    ed.set_rows([("a", "1", "原文"), ("a", "2", "原文")])
    assert [r.replace for r in ed.get_rules()] == ["1", "2"]


def test_replacement_editor_move_requires_selection(tk_root) -> None:
    ed = ReplacementEditor(tk_root)
    ed.set_rows([("a", "1", "原文")])
    assert ed.move_selected(-1) is False, "没选中就不该动"


def test_replacement_editor_stage_accepts_value_or_label(tk_root) -> None:
    """`阶段` 认取值（raw）也认标签（原文）。"""
    ed = ReplacementEditor(tk_root)
    ed.set_rows([("a", "1", "raw")])
    assert ed.get_rows()[0][2] == "原文"


# ---------- CssEditor ----------


def test_css_editor_modes_are_exclusive(tk_root) -> None:
    """`none` / `append` / `override` 三选一，同时只产出一个键。"""
    ed = CssEditor(tk_root)
    ed.set(CSS_APPEND, "a.css")
    mode, path, _text = ed.get()
    assert (mode, path) == (CSS_APPEND, "a.css")
    ed.set(CSS_OVERRIDE, "b.css")
    assert ed.get()[:2] == (CSS_OVERRIDE, "b.css")
    ed.set(CSS_NONE)
    assert ed.get()[0] == CSS_NONE


def test_css_editor_disables_inputs_in_none_mode(tk_root) -> None:
    """`none` 下路径与文本都禁用：留着可编辑只会让人填不生效的值。"""
    ed = CssEditor(tk_root)
    assert str(ed.text.cget("state")) == "disabled"
    ed.set(CSS_APPEND, "a.css")
    assert str(ed.text.cget("state")) == "normal"


def test_css_editor_load_builtin_matches_core(tk_root) -> None:
    """「载入内置模板」用的是 core 的 `builtin_css()`，不是另存一份。"""
    from simple_ebook_converter.core.builder import builtin_css
    from simple_ebook_converter.core.config import DEFAULTS

    ed = CssEditor(tk_root)
    ed.set(CSS_APPEND, "a.css")
    ed.load_builtin()
    assert ed.get()[2] == builtin_css(DEFAULTS)


# ---------- StatusBar ----------


def test_status_bar_busy_transitions(tk_root) -> None:
    """忙状态必须收尾，否则按钮会一直灰着。"""
    bar = StatusBar(tk_root)
    assert bar.busy is False
    bar.begin("处理中")
    assert bar.busy is True
    bar.ok("完成")
    assert bar.busy is False
    assert bar.text.cget("text") == "完成"


def test_status_bar_fail_turns_red(tk_root) -> None:
    bar = StatusBar(tk_root)
    bar.fail("出错了")
    assert bar.busy is False
    assert bar.text.cget("text") == "出错了"


# ---------- TocPanel ----------


def test_toc_panel_result_column_hides_with_no_rules(tk_root) -> None:
    """没有替换规则时「替换后」列收掉。宽度写字面量 0，不用 s(0)。"""
    panel = TocPanel(tk_root)
    panel.set_entries([{"raw_title": "第一章", "level": 3, "lines": [1, 9]}])
    panel.set_result_column(None)
    assert panel.tree.column(RESULT, "width") == 0, "无规则时列宽应为 0"
    panel.set_result_column({entry_id({"raw_title": "第一章", "level": 3, "lines": [1, 9]}): "第一章"})
    assert panel.tree.column(RESULT, "width") > 0, "有规则时列应显示"


def test_toc_panel_keeps_flags_across_rescan(tk_root) -> None:
    """重扫后按稳定键复原划掉状态。"""
    entry = {"raw_title": "第一章", "level": 3, "lines": [1, 9]}
    panel = TocPanel(tk_root)
    panel.set_entries([entry])
    iid = entry_id(entry)
    panel._set_deleted(iid, True)
    assert panel.deleted_count() == 1
    panel.set_entries([entry])  # 重扫
    assert panel.toc_entries_with_flags()[0].get("deleted") is True


def test_toc_panel_toc_settings_use_positive_key(tk_root) -> None:
    """`toc_in_spine` 正面表述，不是 `no_toc`。"""
    panel = TocPanel(tk_root)
    panel.set_toc_settings(TocSettings(toc_depth=3, toc_in_spine=False))
    got = panel.get_toc_settings()
    assert got.toc_depth == 3
    assert got.toc_in_spine is False


def test_toc_panel_clamps_depth(tk_root) -> None:
    """深度越界要夹回 1~6，否则 core 的 validate 会报。"""
    panel = TocPanel(tk_root)
    panel.set_toc_settings(TocSettings(toc_depth=99))
    assert panel.get_toc_settings().toc_depth == 6
    panel.set_toc_settings(TocSettings(toc_depth=0))
    assert panel.get_toc_settings().toc_depth == 1


# ---------- 页签往返 ----------


def test_form_builder_sections_and_values(tk_root) -> None:
    """声明式 Form：按 spec 建分节、能往返取值。"""
    from simple_ebook_converter.gui.widgets.form import (
        Check,
        Choice,
        Field,
        Form,
        Section,
        Text,
    )

    form = Form(
        tk_root,
        (
            Section(
                "第一组",
                (
                    Field("t", "文字", Text()),
                    Field("c", "选项", Choice(("x", "y"), default="x")),
                    Field("b", "开关", Check(default=False)),
                ),
            ),
        ),
    )
    form.pack()
    tk_root.update()

    frames = [str(w.cget("text")) for w in form.winfo_children() if isinstance(w, ttk.LabelFrame)]
    assert frames == ["第一组"]
    assert form.value("t") == ""
    assert form.value("c") == "x"
    assert form.value("b") is False

    form.set_values({"t": "hi", "c": "y", "b": True})
    assert form.values() == {"t": "hi", "c": "y", "b": True}
    form.destroy()


def test_basic_tab_groups_and_core_help(tk_root) -> None:
    """基础页分组为 文件/书籍信息/封面/清理，且日期与语言的帮助文字来自 core。"""
    from simple_ebook_converter.core.options import OPTIONS

    def help_of(name: str) -> str:
        return next(o for o in OPTIONS if o.name == name).help

    tab = BasicTab(tk_root)
    frames: list[str] = []
    labels: list[str] = []

    def walk(w) -> None:
        if isinstance(w, ttk.LabelFrame):
            frames.append(str(w.cget("text")))
        elif isinstance(w, ttk.Label):
            labels.append(str(w.cget("text")))
        for child in w.winfo_children():
            walk(child)

    walk(tab)
    assert frames == ["文件", "书籍信息", "封面", "清理"]
    # 帮助文字必须**逐字**等于 core 的，界面不另写一份（否则迟早和 CLI 分叉）
    assert help_of("date") in labels
    assert help_of("language") in labels


def test_toc_check_column_is_centered_and_narrow(tk_root) -> None:
    """「启用」列要居中对齐、不参与拉伸，且明显窄于标题列。"""
    panel = TocPanel(tk_root)
    assert str(panel.tree.column(CHECK, "anchor")) == "center"
    assert not bool(panel.tree.column(CHECK, "stretch"))
    assert panel.tree.column(CHECK, "width") < panel.tree.column(TITLE, "width")


def test_identify_tab_preserves_regex_whitespace(tk_root) -> None:
    """正则首尾空格有意义，不能被 strip 掉（别把用户写的正则悄悄改短）。"""
    tab = IdentifyTab(tk_root)
    tab._levels["chapter"][1].set("  ^第.章  ")
    assert tab.get().levels["chapter"] == "  ^第.章  "


def test_extra_levels_preserve_regex_whitespace(tk_root) -> None:
    """额外层级的正则同样原样保留。"""
    editor = ExtraLevelsEditor(tk_root)
    editor.set([{"h": "h5", "class_name": "scene", "regex": "  ^序  "}])
    assert editor.get()[0]["regex"] == "  ^序  "
    assert editor.get_specs() == ["h5.scene:  ^序  "]


def test_basic_tab_round_trip(tk_root) -> None:
    tab = BasicTab(tk_root)
    values = BasicValues(
        encoding="gb18030", title="书名", author="作者", date="2024-05-13",
        language="ja", clean=False, overwrite=False, text_cover=False,
    )
    tab.set(values)
    got = tab.get()
    for name in ("encoding", "title", "author", "date", "language", "clean",
                 "overwrite", "text_cover"):
        assert getattr(got, name) == getattr(values, name), name


def test_identify_tab_untouched_level_follows_core(tk_root) -> None:
    """未动过的层级：勾上、框里是 core 缺省正则，且 `levels` 里是 `None`。"""
    from simple_ebook_converter.core.options import option_default

    tab = IdentifyTab(tk_root)
    tab.set(IdentifyValues(levels=dict.fromkeys(LEVEL_NAMES)))
    got = tab.get()
    for name in LEVEL_NAMES:
        assert got.levels[name] is None, f"{name} 应保持「未动过」"
    assert got.max_title_len == option_default(_opt("max_title_len"))


def test_identify_tab_disabled_level_is_empty_string(tk_root) -> None:
    tab = IdentifyTab(tk_root)
    tab.set(IdentifyValues(levels={"volume": ""}))
    assert tab.get().levels["volume"] == ""


def test_identify_tab_extra_levels_round_trip(tk_root) -> None:
    tab = IdentifyTab(tk_root)
    tab.set(IdentifyValues(level_rows=[{"h": "h5", "class_name": "scene", "regex": "^场景"}]))
    got = tab.get()
    assert got.level_specs == ["h5.scene:^场景"]


def test_typography_tab_round_trip(tk_root) -> None:
    tab = TypographyTab(tk_root)
    values = TypographyValues(
        indent=0, line_height="150%", para_spacing="12px",
        volume_align="left", chapter_align="right", css_mode=CSS_APPEND, css_path="a.css",
    )
    tab.set(values)
    got = tab.get()
    assert got.indent == 0
    assert got.line_height == "150%"  # CSS 长度值按字符串存
    assert got.para_spacing == "12px"
    assert got.volume_align == "left"  # 中文标签 → core 取值
    assert got.chapter_align == "right"
    assert got.css_mode == CSS_APPEND
    assert got.css_path == "a.css"


def test_typography_tab_sections_and_align_mapping(tk_root) -> None:
    """排版页分三组；对齐下拉显示中文、取值仍给 core 的英文。"""
    tab = TypographyTab(tk_root)
    frames = [
        str(w.cget("text")) for w in tab.form.winfo_children() if isinstance(w, ttk.LabelFrame)
    ]
    assert frames == ["段落", "对齐", "正文字体"]

    control = tab.form.control("volume_align")
    tab.form.set_value("volume_align", "center")
    assert control.var.get() == "居中"          # 界面显示标签
    assert tab.form.value("volume_align") == "center"  # 返回 core 取值


def test_basic_tab_autofill_only_fills_empty_or_stale(tk_root) -> None:
    """自动填充只碰「空的」或「仍等于上次自动值」的字段（设计 §7.4）。"""
    tab = BasicTab(tk_root)
    assert tab.autofill(
        {"encoding": "gb18030", "title": "猜的书名", "author": "猜的作者", "out": "a.epub"}
    )
    assert tab.get().encoding == "gb18030"
    assert tab.get().title == "猜的书名"
    assert tab.get().out == "a.epub"

    # 用户改了书名 → 再扫不许冲掉；输出仍是上次自动值 → 允许更新
    tab._title.set("用户书名")
    tab._field_changed("title")
    tab.autofill({"title": "又一次猜测", "out": "b.epub"})
    assert tab.get().title == "用户书名", "用户填的书名被自动填充覆盖了"
    assert tab.get().out == "b.epub", "输出仍是上次自动值，应当允许更新"


def test_basic_tab_autofill_does_not_clobber_manual_output(tk_root) -> None:
    """非空且不等于上次自动值的输出路径，绝不覆盖（不管是不是通过 UI 改的）。"""
    tab = BasicTab(tk_root)
    tab.out_row.set("我选的输出.epub")
    tab.autofill({"out": "自动推导.epub"})
    assert tab.get().out == "我选的输出.epub"


def test_basic_tab_explicit_auto_encoding_is_respected(tk_root) -> None:
    """默认 `auto` 会被自动填充填成实际编码；用户**显式**选回 auto 则不许再动。

    `auto` 是个非空串，光看值分不出「默认」还是「用户选的」——靠 `_touched` 区分。
    """
    tab = BasicTab(tk_root)
    assert tab.get().encoding == "auto"
    tab.autofill({"encoding": "gb18030"})
    assert tab.get().encoding == "gb18030"

    tab._encoding.set("auto")
    tab._field_changed("encoding")  # 用户显式选回 auto
    tab.autofill({"encoding": "utf-8"})
    assert tab.get().encoding == "auto", "用户显式选的 auto 被自动填充覆盖了"


def test_replace_tab_round_trip(tk_root) -> None:
    tab = ReplaceTab(tk_root)
    tab.set_rows([("a", "1", "原文"), ("b", "", "HTML")])
    rows = tab.get_rows()
    assert rows[0] == ("a", "1", "原文")
    assert rules_from_rows(rows) == [Rule("a", "1", "raw"), Rule("b", "", "html")]


def _opt(name: str):
    from simple_ebook_converter.core.options import OPTIONS

    return next(o for o in OPTIONS if o.name == name)


# ---------- App 整体 ----------
#
# 这一节的理由：`App` 的问题全部出在**模块之间**（settings 的扁平结构 ↔ 页签要的
# dataclass、控件构造顺序、临时 CSS 的归属），而前面那些测试一次只碰一个模块，
# 结构性地看不到这类问题。下面三条是本轮实际修掉的 bug 的回归测试。


def test_app_constructs_and_survives_settings_round_trip(tk_root, monkeypatch) -> None:
    """建得出 + 灌得进设置。上一版挂在 `data.basic`（settings 早已改扁平）。

    顺带钉住「空串 = 不设」这条约定：`Settings` 默认 `encoding=""`，灌进界面后
    collect() 拿回的还是 `""`，因为它表示「没指定，交给 core 缺省」——不能趁
    restore 的时候偷偷把 core 的缺省值固化进设置，那样用户在 CLI 里改的缺省
    就再也影响不到 GUI 了。
    """
    import simple_ebook_converter.gui.app as app_mod
    import simple_ebook_converter.gui.settings as settings_mod

    saved = settings_mod.Settings(encoding="gb18030", indent=4, toc_in_spine=False)
    monkeypatch.setattr(settings_mod, "load_settings", lambda: saved)
    monkeypatch.setattr(app_mod, "load_settings", lambda: saved)
    monkeypatch.setattr(app_mod, "save_settings", lambda data: None)

    app = app_mod.App(tk_root)
    tk_root.update()

    got = app.collect()
    assert got.basic.encoding == "gb18030", "扁平字段没走到界面上"
    assert got.typography.indent == 4
    assert got.toc.toc_in_spine is False

    # 不设的字段仍是空串，不被 restore 固化成 core 缺省
    assert got.basic.title == ""
    app.destroy()


def test_app_does_not_rescan_on_startup(tk_root, monkeypatch) -> None:
    """输入路径不持久化（settings.py 的决定），所以启动不该触发重扫。

    问界面而不是问设置：写 `if data.input:` 读的是个不存在的字段。
    """
    import simple_ebook_converter.gui.app as app_mod
    import simple_ebook_converter.gui.settings as settings_mod

    monkeypatch.setattr(settings_mod, "load_settings", lambda: settings_mod.Settings())
    monkeypatch.setattr(app_mod, "load_settings", lambda: settings_mod.Settings())

    calls: list[bool] = []
    real = app_mod.App.rescan

    def spy(self) -> None:
        calls.append(True)
        real(self)

    monkeypatch.setattr(app_mod.App, "rescan", spy)
    app = app_mod.App(tk_root)
    tk_root.update()
    assert not app.tabs["basic"].input_row.get()
    assert calls == []
    app.destroy()


def test_app_tracks_temp_css_for_cleanup(tk_root, monkeypatch) -> None:
    """内联 CSS 落出来的临时文件要能被找到并删掉。

    上一版 `generate()` 在 `_try_config()` 之后把 `_temp_css` 重置成 None ——
    文件刚建好就被从账本上划掉，于是永远不删，每扫一次目录在 temp 里多一份。
    """
    import simple_ebook_converter.gui.app as app_mod
    import simple_ebook_converter.gui.settings as settings_mod

    monkeypatch.setattr(settings_mod, "load_settings", lambda: settings_mod.Settings())
    monkeypatch.setattr(app_mod, "load_settings", lambda: settings_mod.Settings())

    app = app_mod.App(tk_root)
    app.tabs["typography"].css.set(CSS_APPEND, "", "h1 { color: red; }")

    cfg = app._try_config()
    assert cfg is not None
    assert cfg.css_append is not None
    # 账本上的路径就是 core 实际要读的那个
    assert app._temp_css is not None
    assert Path(app._temp_css) == Path(cfg.css_append)
    assert Path(app._temp_css).exists()

    app._cleanup_temp_css()
    assert not Path(cfg.css_append).exists()
    assert app._temp_css is None
    app.destroy()


def test_app_rule_edits_refresh_preview_without_rescan(tk_root, monkeypatch) -> None:
    """改替换规则要立刻更新「替换后」列，且**不重扫整本书**。

    替换只改写标题文字，不影响目录识别结果，entries 已经在内存里了。之前这里
    挂的是 _schedule_rescan：改一条规则 → 300ms 后把整本书重读重解析一遍，就为了
    重画一列显示；而且生成期间 status.busy 还会把它挡掉。
    """
    import simple_ebook_converter.gui.app as app_mod
    import simple_ebook_converter.gui.settings as settings_mod
    from simple_ebook_converter.gui.widgets.toc_panel import RESULT

    monkeypatch.setattr(settings_mod, "load_settings", lambda: settings_mod.Settings())
    monkeypatch.setattr(app_mod, "load_settings", lambda: settings_mod.Settings())

    app = app_mod.App(tk_root)
    entries = [
        {"raw_title": "第一章 开始", "level": 3, "class_name": "chapter", "lines": [1, 2]},
        {"raw_title": "第二章 结束", "level": 3, "class_name": "chapter", "lines": [3, 4]},
    ]
    app._show_entries(entries)
    tk_root.update()

    rescans: list[bool] = []
    monkeypatch.setattr(app_mod.App, "rescan", lambda self: rescans.append(True))

    # 无规则：结果列必须收掉（宽度 0）
    assert app.toc.tree.column(RESULT, "width") == 0

    app.tabs["replace"].editor.set_rows([("第一章", "Chapter One", "原文")])
    tk_root.update()
    assert app.toc.tree.column(RESULT, "width") > 0, "有规则了结果列还藏着"
    shown = [app.toc.tree.set(i, RESULT) for i in app.toc.tree.get_children()]
    assert shown[0].startswith("Chapter One")
    assert shown[1].startswith("第二章"), "只该替换命中的那条"

    # 规则清空 → 列重新收掉
    app.tabs["replace"].editor.set_rows([])
    tk_root.update()
    assert app.toc.tree.column(RESULT, "width") == 0

    assert not rescans, "改规则触发了整本书重扫"
    app.destroy()


def test_mainthread_dispatch_survives_real_worker_thread(tk_root) -> None:
    """后台线程 post 的回调必须真的在主线程上跑起来。

    这条是给 `MainThread` 存在本身一个理由：上一版 `StatusBar.on_main()` 直接在
    worker 线程里 `root.after(...)`，而 **`after()` 本身就是一次 Tk 调用**，从非
    主线程调会抛 `RuntimeError: main thread is not in main loop`。后果不是崩，
    是重扫永远收不了尾 —— 状态栏 busy 卡在 True，界面看起来「一直在处理中」。
    """
    import threading
    import time

    from simple_ebook_converter.gui.mainthread import MainThread

    dispatcher = MainThread(tk_root, poll_ms=5)
    done = threading.Event()
    ran_on: list[int] = []

    def work() -> None:
        def touch_widget() -> None:  # 真的碰一下控件：只允许在主线程发生
            tk_root.winfo_exists()
            ran_on.append(threading.get_ident())

        dispatcher.post(touch_widget)
        done.set()

    thread = threading.Thread(target=work)
    thread.start()
    thread.join(timeout=5)
    assert done.wait(timeout=5), "worker 线程没跑完"

    deadline = time.time() + 5
    while not ran_on and time.time() < deadline:
        tk_root.update()
        time.sleep(0.005)

    dispatcher.stop()
    assert ran_on, "回调从没被执行（旧的 root.after 写法会卡在这里）"
    assert ran_on == [threading.get_ident()], "回调不在主线程上跑"


def test_mainthread_survives_raising_callback(tk_root) -> None:
    """一个坏回调不该让整个界面停止响应。"""
    import time

    from simple_ebook_converter.gui.mainthread import MainThread

    dispatcher = MainThread(tk_root, poll_ms=5)
    after_boom: list[bool] = []

    def boom() -> None:
        raise ValueError("故意炸")

    dispatcher.post(boom)
    dispatcher.post(lambda: after_boom.append(True))

    deadline = time.time() + 5
    while not after_boom and time.time() < deadline:
        tk_root.update()
        time.sleep(0.005)

    dispatcher.stop()
    assert after_boom, "前一个回调抛异常后，后面的没被执行（轮询死了）"


def test_app_empty_state_disables_actions(tk_root, monkeypatch) -> None:
    """没输入文件时：生成按钮 + 目录工具条都该是禁用的。

    这一条防的是「按钮亮着但点下去只会弹一句缺少输入」——用户会以为程序坏了。
    """
    import simple_ebook_converter.gui.app as app_mod
    import simple_ebook_converter.gui.settings as settings_mod

    monkeypatch.setattr(settings_mod, "load_settings", lambda: settings_mod.Settings())
    monkeypatch.setattr(app_mod, "load_settings", lambda: settings_mod.Settings())

    app = app_mod.App(tk_root)
    tk_root.update()

    assert app.tabs["basic"].input_row.get() == ""
    assert str(app.btn_generate.cget("state")) == "disabled"

    # 给了输入（哪怕还没扫）→ 生成按钮应放开
    app.tabs["basic"].set_input("novel.txt")
    tk_root.update()
    assert str(app.btn_generate.cget("state")) == "normal"

    # 再清空 → 重新禁用
    app.tabs["basic"].set_input("")
    tk_root.update()
    assert str(app.btn_generate.cget("state")) == "disabled"
    app.destroy()


def test_app_freezes_and_restores_left_pane_exactly(tk_root, monkeypatch) -> None:
    """忙时冻住左栏，解冻要**原样还原**，不能一律设回 normal。

    一律 normal 会把 readonly 的下拉变成可编辑文本框，也会放开 CSS 在 none 模式下
    本该禁用的路径/文本。所以断言冻结前后每个控件的 state 完全一致。
    """
    import simple_ebook_converter.gui.app as app_mod
    import simple_ebook_converter.gui.settings as app_settings

    monkeypatch.setattr(app_settings, "load_settings", lambda: app_settings.Settings())
    monkeypatch.setattr(app_mod, "load_settings", lambda: app_settings.Settings())

    app = app_mod.App(tk_root)
    tk_root.update()

    def snapshot():
        found = {}

        def walk(w):
            if isinstance(
                w,
                (ttk.Button, ttk.Checkbutton, ttk.Radiobutton, ttk.Spinbox, ttk.Entry,
                 ttk.Combobox, tk.Text),
            ):
                found[str(w)] = (w.winfo_class(), str(w.cget("state")))
            for c in w.winfo_children():
                walk(c)

        walk(app._left_pane)
        return found

    before = snapshot()
    assert any(cls == "TCombobox" and st == "readonly" for cls, st in before.values())

    app.status.begin("模拟忙碌")  # 触发 on_busy_change → 冻结
    tk_root.update()
    during = snapshot()
    assert all(st == "disabled" for _cls, st in during.values()), "忙时还有可用控件"

    app.status.ok("收工")  # 解冻
    tk_root.update()
    assert snapshot() == before, "解冻没有原样还原控件状态"
    app.destroy()


def test_rescan_asks_before_discarding_deletions(tk_root, monkeypatch) -> None:
    """有划掉的条目时，主动重扫要先确认；没有时不打扰。"""
    import simple_ebook_converter.gui.app as app_mod
    import simple_ebook_converter.gui.settings as settings_mod

    monkeypatch.setattr(settings_mod, "load_settings", lambda: settings_mod.Settings())
    monkeypatch.setattr(app_mod, "load_settings", lambda: settings_mod.Settings())
    app = app_mod.App(tk_root)

    scans: list[bool] = []
    monkeypatch.setattr(app_mod.App, "rescan", lambda self: scans.append(True))
    prompts: list[bool] = []

    monkeypatch.setattr(
        app_mod.messagebox, "askyesno", lambda *a, **k: (prompts.append(True), False)[1]
    )

    # 没划掉任何东西 → 不弹窗，直接扫
    app._rescan_clicked()
    assert scans == [True]
    assert prompts == []

    # 划掉一条 → 弹窗；这里答「否」→ 不扫
    entries = [
        {"raw_title": "第一章", "level": 3, "class_name": "chapter", "lines": [1, 5]},
        {"raw_title": "第二章", "level": 3, "class_name": "chapter", "lines": [6, 9]},
    ]
    app._show_entries(entries)
    app.toc._set_deleted(app.toc.tree.get_children("")[0], True)
    tk_root.update()
    assert app.toc.deleted_count() == 1

    scans.clear()
    app._rescan_clicked()
    assert prompts == [True], "有划掉的条目却没提示"
    assert scans == [], "用户还没确认就扫了"

    # 答「是」→ 扫
    monkeypatch.setattr(app_mod.messagebox, "askyesno", lambda *a, **k: True)
    app._rescan_clicked()
    assert scans == [True]
    app.destroy()


def test_app_never_deletes_user_chosen_css(tk_root, monkeypatch, tmp_path) -> None:
    """用户自己选的 CSS 文件不能被当成临时文件删掉。"""
    import simple_ebook_converter.gui.app as app_mod
    import simple_ebook_converter.gui.settings as settings_mod

    monkeypatch.setattr(settings_mod, "load_settings", lambda: settings_mod.Settings())
    monkeypatch.setattr(app_mod, "load_settings", lambda: settings_mod.Settings())

    app = app_mod.App(tk_root)
    mine = tmp_path / "mine.css"
    mine.write_text("h1 {}", encoding="utf-8")
    app.tabs["typography"].css.set(CSS_APPEND, str(mine))

    assert app._try_config() is not None
    app._cleanup_temp_css()
    assert mine.exists(), "临时文件清理误伤了用户指定的 CSS"
    app.destroy()
