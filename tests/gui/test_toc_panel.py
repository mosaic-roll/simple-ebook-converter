"""`gui.toc_panel` 的纯函数：预览结果 → 表格条目、条目 → tag。

只测不碰 Tk 的那两段（`populate_toc` / `set_deleted` 要真 Treeview，另说）。
模块顶层 import 了 customtkinter，但这里不建根窗口，所以无头环境也能跑。
"""

import json

import pytest

from simple_ebook_converter.core.config import default_levels
from simple_ebook_converter.core.parser import parse
from simple_ebook_converter.core.pipeline import preview_titles
from simple_ebook_converter.core.replace import Rule
from simple_ebook_converter.core.toc import tree_from_json
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


# ---------- import_toc_json：字段规则与 core 同一份 ----------


def _write(tmp_path, data):
    p = tmp_path / "toc.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


def test_import_normalizes_level0_class_like_core(tmp_path):
    """level 0 的 class 归一成 chapter：core 建树时这么改，导入时也要，
    否则回填再导出会把 core 规范化过的值退回去。"""
    entries = import_toc_json(
        _write(
            tmp_path,
            [{"raw_title": "前言", "level": 0, "class_name": "volume", "line": 1}],
        )
    )
    assert entries[0]["class_name"] == "chapter"


def test_import_keeps_deleted_row_visible(tmp_path):
    """deleted 条目仍要带回标题：删除线划在哪一行是用户要看的。"""
    entries = import_toc_json(
        _write(
            tmp_path,
            [
                {"raw_title": " 第一章 ", "level": 2, "line": 1},
                {"raw_title": "第二章", "level": 2, "line": 9, "deleted": True},
            ],
        )
    )
    assert [e["deleted"] for e in entries] == [False, True]
    assert entries[1]["raw_title"] == "第二章"


def test_import_tolerates_non_string_title_on_deleted_row(tmp_path):
    """core 不校验 deleted 条目的 raw_title，界面要自己兜住非字符串。"""
    entries = import_toc_json(
        _write(tmp_path, [{"raw_title": None, "level": 2, "deleted": True}])
    )
    assert entries[0]["raw_title"] == ""


def test_import_rejects_out_of_range_level(tmp_path):
    """层级范围与 core 一致：0~6。"""
    with pytest.raises(ValueError, match="层级不合法"):
        import_toc_json(_write(tmp_path, [{"raw_title": "甲", "level": 9, "line": 1}]))


def test_import_does_not_range_check_line(tmp_path):
    """导入时没有正文文件，行号上界查不了，只查是不是正整数。

    反过来记：core 的 `tree_from_json` 拿到 `lines` 会查上界，导入这条路不查。
    """
    entries = import_toc_json(
        _write(tmp_path, [{"raw_title": "甲", "level": 2, "line": 99999}])
    )
    assert entries[0]["line"] == 99999
    with pytest.raises(ValueError, match="超出输入范围"):
        tree_from_json(
            [{"raw_title": "甲", "level": 2, "line": 99999}], ["只有一行"]
        )
