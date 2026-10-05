"""`gui.toc_panel` 的纯函数：预览结果 → 表格条目、条目 → tag。

只测不碰 Tk 的那两段（`populate_toc` / `set_deleted` 要真 Treeview，另说）。
模块顶层 import 了 customtkinter，但这里不建根窗口，所以无头环境也能跑。
"""

import json

from simple_ebook_converter.core.config import default_levels
from simple_ebook_converter.core.parser import parse
from simple_ebook_converter.core.pipeline import preview_titles
from simple_ebook_converter.core.replace import Rule
from simple_ebook_converter.core.toc import load_entries
from simple_ebook_converter.gui.constants import TAG_DELETED, TAG_HTML, TAG_HTML_DELETED
from simple_ebook_converter.gui.toc_panel import (
    _tags_for,
    entries_from_preview,
    import_toc_json,
)


def _preview(replacements=()):
    tree, _stats = parse(
        ["第一章 甲", "正文", "第二章 乙<一>", "正文"],
        default_levels(),
        fallback_title="测试书",
    )
    return preview_titles(tree, list(replacements))


def test_plain_rows_show_unescaped_title():
    """没命中 html 规则时显示未转义的 `title`，否则满屏 `&amp;` 噪声。"""
    entries = entries_from_preview(_preview())
    assert [e["level"] for e in entries] == [3, 3]
    assert entries[0]["result"] == "第一章 甲"
    assert entries[0]["html_hit"] is False
    assert entries[1]["raw_title"] == "第二章 乙<一>"


def test_html_hit_shows_the_markup_source():
    """命中 html 规则时结果列取 `title_html`（那段 HTML 源码），整行可染蓝。"""
    entries = entries_from_preview(
        _preview(
            [
                Rule(
                    pattern=r"第(.)章",
                    replace=r'第<span class="n">\1</span>章',
                    stage="html",
                )
            ]
        )
    )
    assert entries[0]["html_hit"] is True
    assert '第<span class="n">一</span>章' in entries[0]["result"]


def test_tags_give_deleted_priority_over_html():
    """删除优先：命中 + 删除走灰字删除线，蓝色等恢复后才回来。"""
    assert _tags_for(deleted=True, html_hit=True) == (TAG_HTML_DELETED,)
    assert _tags_for(deleted=True, html_hit=False) == (TAG_DELETED,)
    assert _tags_for(deleted=False, html_hit=True) == (TAG_HTML,)
    assert _tags_for(deleted=False, html_hit=False) == ()


def test_import_toc_json_delegates_to_core(tmp_path):
    """导入就是转发给 `core.toc.load_entries`——条目形状由 core 定，GUI 不解释。

    字段规则本身在 `tests/core/test_toc.py`，这里只钉住「GUI 没有自己那一份」。
    """
    p = tmp_path / "toc.json"
    p.write_text(
        json.dumps(
            [{"raw_title": "前言", "level": 0, "class_name": "volume", "line": 1}]
        ),
        encoding="utf-8",
    )
    assert import_toc_json(p) == load_entries(p)
