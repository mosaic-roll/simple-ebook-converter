"""`core.toc`：目录树 JSON 的渲染与往返（`--toc-file` 的数据契约）。"""

import json
from pathlib import Path

import pytest

from simple_ebook_converter.core.config import Node
from simple_ebook_converter.core.toc import load_toc, to_json, tree_from_json


def _sample_tree() -> list[Node]:
    body = Node("第一章 一", 3, "chapter", paragraphs=["正文甲"], raw_title="第一章 一", lines=(2, 3))
    volume = Node("第一卷", 2, "volume", children=[body], raw_title="第一卷", lines=(1, 3))
    return [volume]


def test_to_json_and_tree_from_json_round_trip():
    """to_json 只存原始标题与行号；回喂构树后标题与正文与原树一致。"""
    lines = ["第一卷", "第一章 一", "正文甲"]
    data = to_json(_sample_tree())
    assert set(data[0]) == {"raw_title", "level", "class_name", "lines", "children"}
    # Full-span semantics: the volume covers its chapter's lines too.
    assert data[0]["lines"] == [1, 3]
    assert data[0]["children"][0]["lines"] == [2, 3]

    restored = tree_from_json(data, lines)
    volume, body = restored[0], restored[0].children[0]
    assert (volume.raw_title, volume.level, volume.class_name) == ("第一卷", 2, "volume")
    assert volume.paragraphs == []  # direct body stops before the first child title
    assert body.paragraphs == ["正文甲"]  # 标题行本身不进正文


def test_tree_from_json_uses_titles_as_given():
    """标题用 json 现值：界面编辑过就是编辑后的。"""
    lines = ["第一卷", "第一章 一", "正文甲"]
    data = to_json(_sample_tree())
    data[0]["raw_title"] = "手改的卷名"
    assert tree_from_json(data, lines)[0].title == "手改的卷名"


def test_tree_from_json_allows_gaps():
    """编辑时删掉的行是空洞：不报错，只是不进书。"""
    lines = ["第一卷", "多余的行", "第一章 一", "正文甲"]
    data = [
        {
            "raw_title": "第一卷",
            "level": 2,
            "class_name": "volume",
            "lines": [1, 1],  # narrowed below the first child: line 2 becomes a gap
            "children": [
                {
                    "raw_title": "第一章 一",
                    "level": 3,
                    "class_name": "chapter",
                    "lines": [3, 4],
                    "children": [],
                }
            ],
        }
    ]
    restored = tree_from_json(data, lines)
    assert restored[0].paragraphs == []
    assert restored[0].children[0].lines == (3, 4)
    assert restored[0].children[0].paragraphs == ["正文甲"]


def test_tree_from_json_keeps_preface_content():
    """前言（level 0）的标题不在原文里，范围整段都是正文。"""
    lines = ["卷首语", "献给某君", "第一卷", "正文"]
    data = [
        {
            "raw_title": "前言",
            "level": 0,
            "class_name": "preface",
            "lines": [1, 2],
            "children": [],
        },
        {
            "raw_title": "第一卷",
            "level": 2,
            "class_name": "volume",
            "lines": [3, 4],
            "children": [],
        },
    ]
    restored = tree_from_json(data, lines)
    assert restored[0].paragraphs == ["卷首语", "献给某君"]
    assert restored[1].paragraphs == ["正文"]  # 标题行本身不进正文


def test_tree_from_json_dissolves_deleted_into_parent():
    """删除线：被删标题消失，正文并入父章节，其余章节不动。"""
    lines = ["第一卷", "卷首", "第100章 误匹配", "误捕的正文", "第二章 二", "正文二"]
    data = [
        {
            "raw_title": "第一卷",
            "level": 2,
            "class_name": "volume",
            "lines": [1, 2],
            "children": [
                {
                    "raw_title": "第100章 误匹配",
                    "level": 3,
                    "class_name": "chapter",
                    "lines": [3, 4],
                    "deleted": True,
                    "children": [],
                },
                {
                    "raw_title": "第二章 二",
                    "level": 3,
                    "class_name": "chapter",
                    "lines": [5, 6],
                    "children": [],
                },
            ],
        }
    ]
    restored = tree_from_json(data, lines)
    volume = restored[0]
    assert [c.raw_title for c in volume.children] == ["第二章 二"]
    # Body merges in document order; the struck-out title line itself is gone.
    assert volume.paragraphs == ["卷首", "误捕的正文"]
    assert volume.children[0].paragraphs == ["正文二"]


def test_tree_from_json_dissolves_deleted_into_previous_sibling():
    """删除线：有前一个未删除的兄弟时正文接在它后面，保持文档顺序。"""
    lines = [
        "第一卷",
        "第一章 一",
        "正文一",
        "第100章 误匹配",
        "误捕的正文",
        "第二章 二",
        "正文二",
    ]
    data = [
        {
            "raw_title": "第一卷",
            "level": 2,
            "class_name": "volume",
            "lines": [1, 1],
            "children": [
                {
                    "raw_title": "第一章 一",
                    "level": 3,
                    "class_name": "chapter",
                    "lines": [2, 3],
                    "children": [],
                },
                {
                    "raw_title": "第100章 误匹配",
                    "level": 3,
                    "class_name": "chapter",
                    "lines": [4, 5],
                    "deleted": True,
                    "children": [],
                },
                {
                    "raw_title": "第二章 二",
                    "level": 3,
                    "class_name": "chapter",
                    "lines": [6, 7],
                    "children": [],
                },
            ],
        }
    ]
    restored = tree_from_json(data, lines)
    volume = restored[0]
    assert [c.raw_title for c in volume.children] == ["第一章 一", "第二章 二"]
    assert volume.children[0].paragraphs == ["正文一", "误捕的正文"]
    assert volume.children[1].paragraphs == ["正文二"]


def test_tree_from_json_lifts_children_of_deleted_top_node():
    """顶层节点被删：正文并入前一个顶层章节，未删除的子章节原地提升到顶层。"""
    lines = ["第一卷", "误匹配的卷", "卷二的正文", "第一章 x", "正文x"]
    data = [
        {
            "raw_title": "第一卷",
            "level": 2,
            "class_name": "volume",
            "lines": [1, 1],
            "children": [],
        },
        {
            "raw_title": "误匹配的卷",
            "level": 2,
            "class_name": "volume",
            "lines": [2, 3],
            "deleted": True,
            "children": [
                {
                    "raw_title": "第一章 x",
                    "level": 3,
                    "class_name": "chapter",
                    "lines": [4, 5],
                    "children": [],
                }
            ],
        },
    ]
    restored = tree_from_json(data, lines)
    assert [n.raw_title for n in restored] == ["第一卷", "第一章 x"]
    assert restored[0].paragraphs == ["卷二的正文"]
    assert restored[1].paragraphs == ["正文x"]


def test_load_toc_rejects_bad_files(tmp_path):
    with pytest.raises(ValueError, match="无法读取"):
        load_toc(tmp_path / "missing.json")
    bad = tmp_path / "bad.json"
    bad.write_text("{oops", encoding="utf-8")
    with pytest.raises(ValueError, match="不是合法 JSON"):
        load_toc(bad)
    bad.write_text('{"raw_title": "x"}', encoding="utf-8")
    with pytest.raises(ValueError, match="必须是 JSON 列表"):
        load_toc(bad)


def test_tree_from_json_rejects_bad_entries():
    lines = ["第一卷", "正文"]
    with pytest.raises(ValueError, match="缺少标题"):
        tree_from_json([{"level": 2, "lines": [1, 1]}], lines)
    with pytest.raises(ValueError, match="层级不合法"):
        tree_from_json([{"raw_title": "x", "level": 9, "lines": [1, 1]}], lines)
    with pytest.raises(ValueError, match="行号不合法"):
        tree_from_json([{"raw_title": "x", "level": 2, "lines": [1]}], lines)
    with pytest.raises(ValueError, match="行号超出输入范围"):
        tree_from_json([{"raw_title": "x", "level": 2, "lines": [5, 6]}], lines)
    with pytest.raises(ValueError, match="deleted 只能是"):
        tree_from_json(
            [{"raw_title": "x", "level": 2, "lines": [1, 1], "deleted": "yes"}], lines
        )
    with pytest.raises(ValueError, match="不是 JSON 对象"):
        tree_from_json(["不是字典"], lines)
