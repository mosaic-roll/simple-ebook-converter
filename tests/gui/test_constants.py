"""`gui.constants`：界面侧的纯数据。这里不 import core、也不 import customtkinter，
所以只装 CLI 也能跑这些测试。"""

import codecs

import pytest

from simple_ebook_converter.core.config import ALIGN_CHOICES
from simple_ebook_converter.core.encoding import AUTO_ENCODING
from simple_ebook_converter.gui.constants import (
    ALIGN_LABELS,
    ENCODING_LABELS,
    TAG_DELETED,
    TAG_HTML,
    TAG_HTML_DELETED,
)


def test_encoding_presets_are_all_real_codecs():
    """这份表是手抄的，抄错一个 codec 名要到解码失败才看出来——这里先兜住。

    OptionMenu 只能选表里的，所以表里的每一个都得真的能被 `bytes.decode()` 用。
    """
    for label, value in ENCODING_LABELS.items():
        if value == AUTO_ENCODING:
            continue
        try:
            codecs.lookup(value)
        except LookupError:
            pytest.fail(f"编码预设「{label}」的 {value} 不是 Python codec")


def test_encoding_presets_keep_the_four_char_names_distinct():
    """cp932 与 shift_jis 是两个 codec，微软扩展那个能多解一批 NEC/IBM 字符，
    两个都要在表里，OptionMenu 才选得到。"""
    values = set(ENCODING_LABELS.values())
    assert {"cp932", "shift_jis"} <= values


def test_align_labels_cover_every_core_choice():
    """对齐的显示名反查要能覆盖 core 的取值集合，否则收集时会漏。"""
    assert set(ALIGN_LABELS.values()) == set(ALIGN_CHOICES)


def test_toc_tag_names_are_distinct():
    """三个 tag 各自独立配色（尤其 html_deleted），重名会互相覆盖。"""
    assert len({TAG_DELETED, TAG_HTML, TAG_HTML_DELETED}) == 3
