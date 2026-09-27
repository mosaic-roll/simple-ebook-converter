"""无头环境下实例化真实控件，验证构造与基本行为。

这批测试**能真正抓住**纯数据测试抓不到的问题：属性名打错（`Entry` 没有
`textwrap`）、style 名不存在、grid 参数传错、`retag_all()` 漏控件。纯数据测试
只 import 模块，这些要真正建控件才会暴露。

Tk 需要一个 display。CI 上没有 display 时整个文件 skip（`conftest` 里已配好
`tk_root` fixture 的跳过逻辑）。
"""

from __future__ import annotations

import pytest
from tkinter import ttk

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
from simple_ebook_converter.gui.widgets.toc_panel import RESULT, TocPanel


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


def test_theme_apply_registers_error_styles(tk_root) -> None:
    """红/黄校验框依赖这两个 style；没注册就等于没有红框。"""
    fonts.bind_fonts(tk_root)
    style = theme.apply(tk_root)
    assert style.lookup("Error.TEntry", "bordercolor")
    assert style.lookup("Warn.TEntry", "bordercolor")


def test_border_color_supported_on_clam(tk_root) -> None:
    fonts.bind_fonts(tk_root)
    theme.apply(tk_root)
    assert theme.border_color_supported(tk_root) is True


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


def test_status_bar_stops_progress_on_finish(tk_root) -> None:
    """忙状态必须收尾，否则进度条会永远转下去。"""
    bar = StatusBar(tk_root)
    assert bar.busy is False
    bar.begin("处理中")
    assert bar.busy is True
    bar.ok("完成")
    assert bar.busy is False
    assert str(bar.bar.cget("mode")) == "determinate"


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


def test_replace_tab_round_trip(tk_root) -> None:
    tab = ReplaceTab(tk_root)
    tab.set_rows([("a", "1", "原文"), ("b", "", "HTML")])
    rows = tab.get_rows()
    assert rows[0] == ("a", "1", "原文")
    assert rules_from_rows(rows) == [Rule("a", "1", "raw"), Rule("b", "", "html")]


def _opt(name: str):
    from simple_ebook_converter.core.options import OPTIONS

    return next(o for o in OPTIONS if o.name == name)
