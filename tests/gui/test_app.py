"""纯数据层的单测：`build_config_from_ui` 与 `settings`。

这两个模块**不 import tkinter**，所以这里不用起窗口就能测转换与持久化的正确性。
需要控件的逻辑（滚轮、行高、内联编辑）不在本文件覆盖范围内。
"""

from __future__ import annotations

import json

import pytest

from simple_ebook_converter.core.config import DEFAULTS
from simple_ebook_converter.gui import settings as S
from simple_ebook_converter.gui.build_config_from_ui import (
    BasicValues,
    IdentifyValues,
    TocSettings,
    TypographyValues,
    UiValues,
    entry_id,
    option_values,
    preview_replacements,
    write_temp_css,
)


# ---------- 目录条目稳定键 ----------


def test_entry_id_includes_span_and_title() -> None:
    """稳定键 = 起:止:raw_title。单用行号或单用标题都不够。"""
    entry = {"raw_title": "第一章", "level": 3, "lines": [10, 40]}
    assert entry_id(entry) == "10:40:第一章"


def test_entry_id_changes_when_lines_drift() -> None:
    """识别设置变了行号会漂，所以键必须跟着变 —— 否则重扫后勾选会错位到别的条目。"""
    a = {"raw_title": "第一章", "level": 3, "lines": [10, 40]}
    b = {"raw_title": "第一章", "level": 3, "lines": [12, 44]}
    assert entry_id(a) != entry_id(b)


def test_entry_id_tolerates_missing_fields() -> None:
    assert entry_id({}) == "0:0:"


# ---------- 替换预览 ----------


def test_preview_applies_raw_rules() -> None:
    from simple_ebook_converter.core.replace import rules_from_rows

    entries = [{"raw_title": "第一章 楔子", "level": 3, "lines": [1, 9]}]
    rules = rules_from_rows([(r"第(.+?)章\s*", r"第\1章 ", "原文")])
    preview = preview_replacements(entries, rules)
    assert preview[entry_id(entries[0])] == "第一章 楔子"


def test_preview_ignores_html_stage() -> None:
    """`html` 阶段是要塞标签给阅读器渲染的，纯文本目录里没意义。"""
    from simple_ebook_converter.core.replace import rules_from_rows

    entries = [{"raw_title": "第一章", "level": 3, "lines": [1, 9]}]
    rules = rules_from_rows([(r"一", "<span>一</span>", "HTML")])
    assert preview_replacements(entries, rules)[entry_id(entries[0])] == "第一章"


def test_preview_empty_when_no_rules() -> None:
    entries = [{"raw_title": "第一章", "level": 3, "lines": [1, 9]}]
    assert preview_replacements(entries, []) == {entry_id(entries[0]): "第一章"}


# ---------- 临时 CSS ----------


def test_temp_css_is_written_readable_and_later_deletable() -> None:
    """落盘的文件要能被 core 按路径重新打开（所以必须真正 close）。"""
    path = write_temp_css("p{color:red}")
    try:
        assert path.read_text(encoding="utf-8") == "p{color:red}"
    finally:
        path.unlink(missing_ok=True)


def test_temp_css_lands_in_temp_dir() -> None:
    path = write_temp_css("x")
    try:
        assert path.suffix == ".css"
    finally:
        path.unlink(missing_ok=True)


# ---------- 设置往返 ----------


def test_settings_round_trip() -> None:
    values = UiValues(
        basic=BasicValues(overwrite=False, clean=False, language="ja", text_cover=False),
        identify=IdentifyValues(
            levels={"volume": "", "chapter": "^序", "section": None},
            level_rows=[{"h": "h5", "class_name": "scene", "regex": "^场景"}],
            max_title_len=20,
            preface_title="序言",
        ),
        typography=TypographyValues(
            indent=0, line_height="150%", para_spacing="12px",
            volume_align="left", chapter_align="right", font="f.ttf",
            css_mode="append", css_path="a.css",
        ),
        toc=TocSettings(toc_depth=3, toc_in_spine=False),
        rules=[("a", "b", "原文")],
    )
    data = S.Settings.from_values(values)
    back, damaged = S.Settings.from_dict(json.loads(data.to_json()))
    assert not damaged
    restored = back.to_values()
    assert restored.identify.levels == values.identify.levels
    assert restored.identify.level_rows == values.identify.level_rows
    assert restored.typography.line_height == "150%"
    assert restored.toc.toc_depth == 3
    assert restored.toc.toc_in_spine is False
    assert restored.rules == [("a", "b", "原文")]


def test_settings_does_not_persist_input_paths() -> None:
    """输入/输出路径不记 —— 换一本书就该重来。"""
    values = UiValues(basic=BasicValues(input="C:/a.txt", out="C:/b.epub", title="某书"))
    data = S.Settings.from_values(values)
    assert "a.txt" not in data.to_json()
    assert "b.epub" not in data.to_json()
    assert "某书" not in data.to_json()


def test_settings_levels_stay_three_state() -> None:
    """三态必须原样存回来：None / "" / 正则。"""
    values = UiValues(
        identify=IdentifyValues(levels={"volume": None, "chapter": "", "section": "^x"})
    )
    data = S.Settings.from_values(values)
    back, _ = S.Settings.from_dict(json.loads(data.to_json()))
    assert back.levels == {"volume": None, "chapter": "", "section": "^x"}


def test_settings_legacy_levels_object_form() -> None:
    """旧版把 `levels` 存成 `{name: {pattern: ...}}`，读回时降级成字符串。"""
    back, damaged = S.Settings.from_dict(
        {"version": S.VERSION, "levels": {"volume": {"pattern": "^x"}, "chapter": ""}}
    )
    assert not damaged, "旧结构能被识别降级，不必整份作废"
    assert back.levels == {"volume": "^x", "chapter": ""}


def test_settings_drops_unknown_level_names() -> None:
    """`levels` 里没见过的键丢掉 —— 留着会让 IdentifyTab 查表 KeyError。"""
    back, damaged = S.Settings.from_dict(
        {"version": S.VERSION, "levels": {"volume": "^x", "section2": "^y"}}
    )
    assert damaged, "不认识的内置层级名应报损坏"
    assert back.levels == {"volume": "^x"}


# ---------- 损坏降级 ----------


@pytest.mark.parametrize(
    "data",
    [
        None,
        [],
        "not a dict",
        123,
    ],
)
def test_broken_settings_fall_back(data) -> None:
    settings, damaged = S.Settings.from_dict(data)
    assert damaged
    assert settings == S.Settings()


def test_unparseable_json_falls_back(tmp_path, monkeypatch) -> None:
    """解不开的 JSON 用缺省启动，不抛 —— 设置文件坏了不该让 GUI 起不来。"""
    monkeypatch.setattr(S, "config_path", lambda: tmp_path / "settings.json")
    (tmp_path / "settings.json").write_text("{not json", encoding="utf-8")
    settings, damaged = S.Settings.load()
    assert damaged
    assert settings == S.Settings()


def test_missing_file_is_not_damage(tmp_path, monkeypatch) -> None:
    """没有设置文件是正常情况（首次启动），不算损坏。"""
    monkeypatch.setattr(S, "config_path", lambda: tmp_path / "absent.json")
    settings, damaged = S.Settings.load()
    assert not damaged
    assert settings == S.Settings()


def test_single_bad_field_does_not_void_whole_file() -> None:
    """一个坏字段只降级该字段，其余照常读回。"""
    settings, damaged = S.Settings.from_dict(
        {"version": S.VERSION, "toc_depth": "六", "indent": 0, "clean": False}
    )
    assert damaged
    assert settings.toc_depth == DEFAULTS.toc_depth
    assert settings.indent == 0
    assert settings.clean is False


def test_bool_in_int_field_is_damage() -> None:
    """`True` 是 `int` 的子类，混进 int 字段要判损坏。"""
    settings, damaged = S.Settings.from_dict({"version": S.VERSION, "indent": True})
    assert damaged
    assert settings.indent == DEFAULTS.indent


def test_version_mismatch_discards_whole_file() -> None:
    """版本对不上不硬猜，直接按缺省。"""
    settings, damaged = S.Settings.from_dict({"version": S.VERSION + 99, "indent": 0})
    assert damaged
    assert settings == S.Settings()


def test_unknown_key_is_damage_not_silent_drop() -> None:
    """来自更新版本的键要报损坏，否则用户升级后旧版会静默丢掉设置。"""
    settings, damaged = S.Settings.from_dict(
        {"version": S.VERSION, "indent": 0, "future_option": True}
    )
    assert damaged
    assert settings.indent == 0


# ---------- 配置路径 ----------


def test_config_path_is_under_app_name() -> None:
    assert S.config_path().name == "settings.json"
    assert S.config_path().parent.name == "simple-ebook-converter"
