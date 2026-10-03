"""`gui.defaults`：界面读到的 core 默认值。

关键是「不手抄第二份」：GUI 显示/预填的默认值必须等于 `core.config.DEFAULTS`，
core 改了界面跟着改。
"""

import pytest

from simple_ebook_converter.core.config import DEFAULTS
from simple_ebook_converter.core.options import OPTIONS
from simple_ebook_converter.gui.constants import ALIGN_LABELS
from simple_ebook_converter.gui.defaults import default_align_label, default_text
from simple_ebook_converter.gui.tabs import rules


def _level_pattern(level: int) -> str:
    return next(rule.pattern for rule in DEFAULTS.levels if rule.level == level)


def test_scalar_defaults_follow_config():
    """界面显示的默认值就是 `Config` 字段值，不是手抄的字面量。"""
    assert default_text("max_title_len") == str(DEFAULTS.max_title_len)
    assert default_text("preface_title") == DEFAULTS.preface_title
    assert default_text("indent") == str(DEFAULTS.indent)
    assert default_text("line_height") == DEFAULTS.line_height
    assert default_text("para_spacing") == DEFAULTS.para_spacing
    assert default_text("exclude") == DEFAULTS.exclude


def test_level_regex_defaults_follow_config():
    """卷/章的预填正则来自 `DEFAULTS.levels`，不是另抄一份 `DEFAULT_*_RE`。"""
    assert default_text("volume") == _level_pattern(2)
    assert default_text("chapter") == _level_pattern(3)


def test_align_defaults_map_back_to_config():
    """对齐菜单的默认中文标签能换回 `Config` 的取值。"""
    for name in ("volume_align", "chapter_align", "body_align"):
        label = default_align_label(name)
        assert label in ALIGN_LABELS, f"{name} 的标签 {label!r} 不在 ALIGN_LABELS 里"
        assert ALIGN_LABELS[label] == getattr(DEFAULTS, name)


def test_unknown_option_raises():
    """选项名写错要立刻炸，而不是静默给个空值。"""
    with pytest.raises(KeyError):
        default_text("没有这个选项")


def test_builtin_rows_split_into_prefill_and_hint():
    """卷/章/排除预填进框；字数上限/无标题章节靠 placeholder 提示。"""
    modes = {label: mode for label, _, mode in rules.BUILTIN_ROWS}
    assert modes["卷"] == rules.PREFILL
    assert modes["章"] == rules.PREFILL
    assert modes["排除"] == rules.PREFILL
    assert modes["字数上限"] == rules.HINT
    assert modes["无标题章节"] == rules.HINT


def test_builtin_rows_reference_real_options():
    """每行都指向 core 里真实存在的选项，键名不会被改错。"""
    names = {opt.name for opt in OPTIONS}
    for label, opt_name, _ in rules.BUILTIN_ROWS:
        assert opt_name in names, f"{label} 指向的选项 {opt_name!r} 不存在"


def test_saved_value_overrides_default():
    """有存档值就用存档值，没有才回 core 默认值。"""
    assert default_text("indent", {"indent": "4"}) == "4"
    assert default_text("indent") == str(DEFAULTS.indent)


def test_saved_none_becomes_empty():
    assert default_text("cover", {"cover": None}) == ""


def test_saved_align_label_maps_back():
    assert default_align_label("body_align", {"body_align": "left"}) == "左对齐"


def test_invalid_saved_align_falls_back_to_core_default():
    """配置文件可手改，非法对齐值不该让启动崩掉。"""
    assert default_align_label(
        "body_align", {"body_align": "没有这个值"}
    ) == default_align_label("body_align")
