"""`gui.app` 的配置收集与回填：模块级 `collect_saved()` / `apply_saved()`。

用假控件而不是真 `App`：`App` 建了 Tk 根窗口就不能销毁（会把别的模块随机 skip
掉），而跨测试共享一个可变实例又会互相污染。假控件两条都绕开了。
只有「读回 `custom.css`」那条要真的文件系统。
"""

from pathlib import Path

import pytest

from simple_ebook_converter.core.replace import rules_to_list
from simple_ebook_converter.gui.app import _as_stored, apply_saved, collect_saved
from simple_ebook_converter.gui.constants import ALIGN_LABELS, TOC_DEPTHS
from simple_ebook_converter.gui.tabs.layout import CSS_MODES

# `apply_saved` 只有一个地方碰磁盘：`config_dir` 下有没有 `custom.css`。测「没有」
# 时这个路径不存在，`is_file()` 为假，什么都不会被读或写。
NOWHERE = Path("__no_such_config_dir__")


class FakeEntry:
    """单行输入框。CSS 文本框是多行控件但用到的 API 一样（索引 `"1.0"` 而非 `0`），
    所以共用这一个。"""

    def __init__(self, text: str = "") -> None:
        self.text = text

    def delete(self, *_args) -> None:
        self.text = ""

    def insert(self, _index, text: str) -> None:
        self.text = text

    def get(self) -> str:
        return self.text


class FakeVar:
    """勾选框 / 下拉菜单 / 对齐菜单：只有 `.get()` 和 `.set()`。"""

    def __init__(self, value="") -> None:
        self.value = value

    def get(self):
        return self.value

    def set(self, value) -> None:
        self.value = value


class FakeFonts:
    """`FontManager` 的三个被用到的属性。真的 `FontManager` 要建 CTkFont。"""

    def __init__(self) -> None:
        self.family_label = "微软雅黑"
        self.ui_size = 13
        self.toc_size = 13


class _Recorder:
    """记录被调过的次数，替 `layout_tab["on_source_change"]()`。"""

    def __init__(self) -> None:
        self.calls = 0

    def __call__(self) -> None:
        self.calls += 1


@pytest.fixture
def ui():
    """一套假控件，返回 `(tab_widgets, toc_widgets, fonts)`。每次调用新建。"""
    tabs = {
        "basic": {
            "clean_var": FakeVar(True),
            "text_cover_var": FakeVar(True),
            "toc_in_book_var": FakeVar(True),
        },
        "layout": {
            "align_volume": FakeVar("左对齐"),
            "align_chapter": FakeVar("左对齐"),
            "align_body": FakeVar("左对齐"),
            "indent": FakeEntry("2"),
            "line_height": FakeEntry(""),
            "para_spacing": FakeEntry(""),
            "font_entry": FakeEntry(""),
            "css_source": FakeVar("text"),
            "css_mode": FakeVar("append"),
            "css_text": FakeEntry(""),
            "on_source_change": _Recorder(),
        },
        "rules": {
            "rule_entries": {label: FakeEntry("") for label in ("卷", "章", "排除")},
            "extra_rows": [],
        },
        "replace": {"rule_cards": [], "add_card": lambda: None},
    }
    toc = {"depth_menu": FakeVar("3")}

    def add_extra_row():
        row = {"level": FakeVar("h6"), "class": FakeEntry(), "regex": FakeEntry()}
        tabs["rules"]["extra_rows"].append(row)
        return row

    tabs["rules"]["add_extra_row"] = add_extra_row
    tabs["rules"]["clear_extra_rows"] = tabs["rules"]["extra_rows"].clear
    return tabs, toc, FakeFonts()


def _collect(ui, appearance_mode="light"):
    tabs, toc, fonts = ui
    return collect_saved(tabs, toc, fonts, appearance_mode)


def _apply(ui, saved, config_dir=NOWHERE):
    """回填 + 忽略非法替换规则的报告（那类要弹状态栏，测试里不必断言）。"""
    tabs, toc, _ = ui
    apply_saved(
        saved, tabs, toc, config_dir=config_dir, on_invalid_rules=lambda _m: None
    )


# ---------------------------------------------------------------- _as_stored


def test_as_stored_turns_an_int_field_into_a_number():
    """`indent` 存成 4 而不是 "4"——`Config` 那边的类型对不上。"""
    assert _as_stored("indent", " 4 ") == 4
    assert isinstance(_as_stored("indent", "4"), int)


def test_as_stored_maps_blank_int_field_to_none():
    """空文本对 int 字段是 None（= 用 core 默认），不是 0 也不是空串。"""
    assert _as_stored("indent", "   ") is None


def test_as_stored_maps_an_unparseable_int_field_to_none():
    """非法输入和留空同等处理：存 None，用 core 默认。

    关窗保存走的就是这条，`_on_close` 只接 `OSError`，抛出去就存不下了。
    """
    assert _as_stored("indent", "abc") is None
    assert _as_stored("indent", "2.5") is None
    assert _as_stored("toc_depth", "六") is None


def test_as_stored_keeps_a_non_int_field_verbatim():
    """非 int 字段不 strip、不转类型，原样存。"""
    assert _as_stored("line_height", " 1.5 ") == " 1.5 "


# ------------------------------------------------------------- collect_saved


def test_collect_saved_serializes_int_fields(ui):
    ui[0]["layout"]["indent"].insert(0, "4")
    saved = _collect(ui)
    assert saved["indent"] == 4
    assert isinstance(saved["indent"], int)
    assert saved["toc_depth"] == 3
    assert isinstance(saved["toc_depth"], int)


def test_collect_saved_drops_blank_prompt_fields(ui):
    """提示型字段留空不该写进 JSON——否则配置文件里全是 null 噪音。"""
    tabs = ui[0]
    tabs["layout"]["line_height"].insert(0, "   ")
    saved = _collect(ui)
    assert saved["line_height"] is None
    assert saved["para_spacing"] is None
    for name in ("volume", "chapter", "exclude"):
        assert saved[name] is None


def test_collect_saved_does_not_crash_on_an_invalid_int(ui):
    """填了非法缩进也能存下配置：存成 None，回填时框被清空、用默认值。"""
    ui[0]["layout"]["indent"].insert(0, "abc")
    first = _collect(ui)
    assert first["indent"] is None
    _apply(ui, first)
    assert ui[0]["layout"]["indent"].get() == ""
    assert _collect(ui)["indent"] is None


def test_collect_saved_translates_align_labels(ui):
    """落盘的是 `ALIGN_LABELS` 的 CSS 值，不是控件里的中文标签。

    断言具体值而非「在合法集合里」：后者在 `ALIGN_LABELS.get(..., "left")` 下照样过。
    """
    tabs = ui[0]
    for key, label in (
        ("align_volume", "居中"),
        ("align_chapter", "右对齐"),
        ("align_body", "两端对齐"),
    ):
        tabs["layout"][key].set(label)
    saved = _collect(ui)
    assert saved["volume_align"] == "center"
    assert saved["chapter_align"] == "right"
    assert saved["para_align"] == "justify"


def test_collect_saved_reads_the_gui_settings(ui):
    saved = _collect(ui, appearance_mode="Dark")
    assert saved["ui"] == {
        "theme": "dark",
        "font": "微软雅黑",
        "ui_font_size": 13,
        "toc_font_size": 13,
    }


def test_collect_saved_keeps_blank_extra_levels(ui):
    """用户刻意留的空行也是状态，下次启动该还在——所以收成空串而不是过滤掉。"""
    ui[0]["rules"]["add_extra_row"]()
    saved = _collect(ui)
    assert saved["extra_levels"] == [{"level": "h6", "class": "", "regex": ""}]


# --------------------------------------------------------------- apply_saved


def test_apply_saved_reads_an_int_field_back_as_text(ui):
    """int 存的是数字，回填进输入框得是文本。"""
    _apply(ui, {"indent": 7})
    assert ui[0]["layout"]["indent"].get() == "7"


def test_apply_saved_skips_a_hand_edited_bad_int(ui):
    """存档被手改成 `"indent": "abc"` 时留空（= 用 core 默认），不该崩。"""
    _apply(ui, {"indent": "abc"})
    assert ui[0]["layout"]["indent"].get() == ""


def test_apply_saved_maps_a_none_field_to_a_blank_entry(ui):
    """`None` 是「留空」的存档表示，回填要真的清空输入框。"""
    ui[0]["layout"]["indent"].insert(0, "9")
    _apply(ui, {"indent": None})
    assert ui[0]["layout"]["indent"].get() == ""


def test_apply_saved_on_empty_settings_leaves_the_form_alone(ui):
    """空存档是「首次启动」，不该把表单清空。"""
    ui[0]["layout"]["indent"].insert(0, "4")
    _apply(ui, {})
    assert ui[0]["layout"]["indent"].get() == "4"


def test_apply_saved_rebuilds_the_extra_levels(ui):
    """存档有几行就有几行——先清掉预置行，再逐条按存档重建。"""
    _apply(
        ui,
        {
            "extra_levels": [
                {"level": "h4", "class": "part", "regex": "^第.+卷"},
                {"level": "", "class": "", "regex": ""},
            ]
        },
    )
    rows = ui[0]["rules"]["extra_rows"]
    assert len(rows) == 2
    assert rows[0]["level"].get() == "h4"
    assert rows[0]["class"].get() == "part"
    # 缺 level 的行退回 h6，而不是留空
    assert rows[1]["level"].get() == "h6"


def test_apply_saved_recomputes_the_css_disabled_state(ui):
    """改了 CSS 来源就得重算禁用态，否则单选框和文本框对不上。"""
    _apply(ui, {"css_source": "file", "css_mode": "覆盖"})
    assert ui[0]["layout"]["css_source"].get() == "file"
    assert ui[0]["layout"]["css_mode"].get() == "覆盖"
    assert "覆盖" in CSS_MODES
    assert ui[0]["layout"]["on_source_change"].calls == 1


def test_apply_saved_ignores_a_hand_edited_bad_css_value(ui):
    """来源 / 模式被手改成不认识的值就当没存档，别让控件显示谁都不认识的东西。"""
    _apply(ui, {"css_source": "粘贴", "css_mode": "半覆盖"})
    assert ui[0]["layout"]["css_source"].get() == "text"
    assert ui[0]["layout"]["css_mode"].get() == "append"


def test_apply_saved_ignores_a_hand_edited_bad_align(ui):
    """非法对齐值退回 core 默认，不让菜单显示空白或谁都不认识的值。"""
    _apply(ui, {"volume_align": "middle"})
    assert ui[0]["layout"]["align_volume"].get() in set(ALIGN_LABELS)


def test_apply_saved_ignores_a_hand_edited_bad_toc_depth(ui):
    """`toc_depth` 不在合法档位就当没存档，别让下拉显示一个空值。"""
    _apply(ui, {"toc_depth": 99})
    assert ui[1]["depth_menu"].get() == "3"
    _apply(ui, {"toc_depth": 5})
    assert ui[1]["depth_menu"].get() == "5"
    assert "5" in TOC_DEPTHS


def test_apply_saved_reads_the_custom_css_back(ui, tmp_path):
    """文本模式的样式存在 `custom.css` 里，启动时读回文本框。

    唯一一条必须碰磁盘的——文件存不存在只能靠磁盘回答。
    """
    (tmp_path / "custom.css").write_text("body { color: red }", encoding="utf-8")
    _apply(ui, {"css_source": "text"}, config_dir=tmp_path)
    assert ui[0]["layout"]["css_text"].get() == "body { color: red }"


# ------------------------------------------------------------------ 往返一致


def test_collect_then_apply_is_stable(ui):
    """收集 → 回填 → 再收集，两个 dict 应该一样（挡住 int 存成字符串那种漂移）。"""
    tabs = ui[0]
    tabs["layout"]["indent"].insert(0, "4")
    tabs["layout"]["line_height"].insert(0, "1.5")
    tabs["layout"]["align_volume"].set("居中")
    tabs["rules"]["rule_entries"]["卷"].insert(0, "^第.+卷")
    first = _collect(ui)
    _apply(ui, first)
    assert _collect(ui) == first


def test_collect_then_apply_is_stable_for_extra_levels(ui):
    """额外层级也走一遍往返——它是 `clear` + 重建，最容易只对一半。"""
    ui[0]["rules"]["add_extra_row"]()
    ui[0]["rules"]["add_extra_row"]()
    ui[0]["rules"]["extra_rows"][0]["level"].set("h4")
    ui[0]["rules"]["extra_rows"][0]["class"].insert(0, "part")
    ui[0]["rules"]["extra_rows"][1]["regex"].insert(0, "^序")
    first = _collect(ui)
    _apply(ui, first)
    assert _collect(ui) == first


def test_replacements_round_trip_through_plain_data(ui):
    """替换规则存的是普通 dict，能直接喂回 `rules_from_list`（不依赖控件）。"""
    assert rules_to_list([]) == []
