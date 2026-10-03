"""`core.toc`：扁平目录 JSON 的渲染与往返（`--toc-file` 的数据契约）。"""

import pytest

from simple_ebook_converter.core.config import LevelRule
from simple_ebook_converter.core.parser import Node, parse
from simple_ebook_converter.core.toc import load_toc, to_json, to_text, tree_from_json


def _sample_tree() -> list[Node]:
    body = Node(
        "第一章 一",
        3,
        "chapter",
        paragraphs=["正文甲"],
        raw_title="第一章 一",
        line=2,
    )
    volume = Node("第一卷", 2, "volume", children=[body], raw_title="第一卷", line=1)
    return [volume]


def test_to_json_and_tree_from_json_round_trip():
    """to_json 只存原始标题与标题行号（扁平、无 children）；回喂后标题与正文一致。"""
    lines = ["第一卷", "第一章 一", "正文甲"]
    data = to_json(_sample_tree())
    assert [set(e) for e in data] == [{"raw_title", "level", "class_name", "line"}] * 2
    assert [e["line"] for e in data] == [1, 2]

    restored = tree_from_json(data, lines)
    volume, body = restored[0], restored[0].children[0]
    assert (volume.raw_title, volume.level, volume.class_name) == (
        "第一卷",
        2,
        "volume",
    )
    assert volume.paragraphs == []  # direct body stops before the next heading
    assert body.paragraphs == ["正文甲"]  # 标题行本身不进正文


def test_to_text_indents_by_relation_not_by_level():
    """顶层不管自己是 h2 还是 h4 都不缩进，其后逐层加一级。"""
    chapter = Node("第一章 一", 3, "chapter", paragraphs=["正文甲"])
    assert to_text([Node("第一卷", 2, "volume", children=[chapter])]) == (
        "第一卷\n  第一章 一"
    )

    # 顶层是 h4（--level 改过的目录）：不该因为 level-1=3 就缩进三级
    section = Node("第一节", 4, "section", children=[chapter])
    assert to_text([Node("总述", 4, "section", children=[section])]) == (
        "总述\n  第一节\n    第一章 一"
    )


def test_to_text_and_to_json_agree_on_depth():
    """`depth` 卡的是绝对 level，两种格式得挑出同一批节点——包括顶层。"""
    tree = _sample_tree()
    for depth in range(1, 7):
        assert len(to_text(tree, depth).splitlines()) == len(to_json(tree, depth))

    assert to_text(tree, 1) == ""  # 顶层 level 2 > depth 1，同样被卡掉
    assert to_json(tree, 1) == []


def test_tree_from_json_uses_titles_as_given():
    """标题用 json 现值：界面编辑过就是编辑后的。"""
    lines = ["第一卷", "第一章 一", "正文甲"]
    data = to_json(_sample_tree())
    data[0]["raw_title"] = "手改的卷名"
    assert tree_from_json(data, lines)[0].title == "手改的卷名"


def test_tree_from_json_levels_are_stacked():
    """层级只由 level 决定：line 不影响挂树。"""
    lines = ["第一卷", "第一章 一", "正文甲", "第二章 二", "正文二"]
    data = [
        {"raw_title": "第一卷", "level": 2, "class_name": "volume", "line": 1},
        {"raw_title": "第一章 一", "level": 3, "class_name": "chapter", "line": 2},
        {"raw_title": "第二章 二", "level": 3, "class_name": "chapter", "line": 4},
    ]
    restored = tree_from_json(data, lines)
    assert [c.raw_title for c in restored[0].children] == ["第一章 一", "第二章 二"]
    assert restored[0].children[0].paragraphs == ["正文甲"]


def test_tree_from_json_assigns_interstitial_lines_to_previous():
    """没有「行空洞」：两个条目之间的行总是归前一条目的正文。"""
    lines = ["第一卷", "多余的行", "第一章 一", "正文甲"]
    data = [
        {"raw_title": "第一卷", "level": 2, "class_name": "volume", "line": 1},
        {"raw_title": "第一章 一", "level": 3, "class_name": "chapter", "line": 3},
    ]
    restored = tree_from_json(data, lines)
    assert restored[0].paragraphs == ["多余的行"]
    assert restored[0].children[0].paragraphs == ["正文甲"]


def test_tree_from_json_keeps_preface_content():
    """前言（level 0）的标题不在原文里，从自身 line 起整段都是正文。"""
    lines = ["卷首语", "献给某君", "第一卷", "正文"]
    data = [
        {"raw_title": "前言", "level": 0, "class_name": "preface", "line": 1},
        {"raw_title": "第一卷", "level": 2, "class_name": "volume", "line": 3},
    ]
    restored = tree_from_json(data, lines)
    assert restored[0].paragraphs == ["卷首语", "献给某君"]
    assert restored[1].paragraphs == ["正文"]  # 标题行本身不进正文
    # level 0 的 class 由程序定，文件里写什么都按章级渲染（与扫描路径一致）
    assert restored[0].class_name == "chapter"


def test_fallback_round_trip_keeps_first_line():
    """整篇无标题时兜底成一章（level 0）；to_json → tree_from_json 不丢首行。"""
    lines = ["第一行正文", "第二行正文", "第三行正文"]
    rules = [LevelRule(2, r"^NEVER$", "chapter")]
    tree, _ = parse(lines, rules, fallback_title="书名")
    assert tree[0].level == 0  # 合成标题：与前言语义一致
    assert tree[0].line == 1  # 没有标题行，line 记正文首行
    restored = tree_from_json(to_json(tree), lines)
    assert restored[0].paragraphs == lines


def test_tree_from_json_dissolves_deleted_into_previous():
    """删除线：被删标题消失，标题行与直属正文都并入文档序上一个未删除条目，
    子条目自动上挂。"""
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
        {"raw_title": "第一卷", "level": 2, "class_name": "volume", "line": 1},
        {"raw_title": "第一章 一", "level": 3, "class_name": "chapter", "line": 2},
        {
            "raw_title": "第100章 误匹配",
            "level": 3,
            "class_name": "chapter",
            "line": 4,
            "deleted": True,
        },
        {"raw_title": "第二章 二", "level": 3, "class_name": "chapter", "line": 6},
    ]
    restored = tree_from_json(data, lines)
    volume = restored[0]
    assert [c.raw_title for c in volume.children] == ["第一章 一", "第二章 二"]
    # 被删条目的标题行（"第100章 误匹配"）与直属正文都归入前一条目
    assert volume.children[0].paragraphs == ["正文一", "第100章 误匹配", "误捕的正文"]
    assert volume.children[1].paragraphs == ["正文二"]


def test_tree_from_json_lifts_children_of_deleted_volume():
    """整卷被删：卷的标题行与直属正文并入上一条目，未删除的子章自动挂到更上层的未删除祖先。"""
    lines = ["第一卷", "误匹配的卷", "卷二的正文", "第一章 x", "正文x"]
    data = [
        {"raw_title": "第一卷", "level": 2, "class_name": "volume", "line": 1},
        {
            "raw_title": "误匹配的卷",
            "level": 2,
            "class_name": "volume",
            "line": 2,
            "deleted": True,
        },
        {"raw_title": "第一章 x", "level": 3, "class_name": "chapter", "line": 4},
    ]
    restored = tree_from_json(data, lines)
    assert [n.raw_title for n in restored] == ["第一卷"]
    # 误匹配的卷 的标题行和正文都归入第一卷；第一章 x 挂在第一卷下。
    assert restored[0].paragraphs == ["误匹配的卷", "卷二的正文"]
    assert [c.raw_title for c in restored[0].children] == ["第一章 x"]
    assert restored[0].children[0].paragraphs == ["正文x"]


def test_tree_from_json_deleted_title_line_becomes_body():
    """中间条目被删：标题行并入前一条的正文，该条不产生节点。"""
    lines = ["第一章 A", "正文 A", "第二章 B", "正文 B", "第三章 C"]
    data = [
        {"raw_title": "第一章 A", "level": 3, "class_name": "chapter", "line": 1},
        {
            "raw_title": "第二章 B",
            "level": 3,
            "class_name": "chapter",
            "line": 3,
            "deleted": True,
        },
        {"raw_title": "第三章 C", "level": 3, "class_name": "chapter", "line": 5},
    ]
    tree = tree_from_json(data, lines)
    assert [n.raw_title for n in tree] == ["第一章 A", "第三章 C"]
    assert tree[0].paragraphs == ["正文 A", "第二章 B", "正文 B"]
    assert tree[1].paragraphs == []


def test_tree_from_json_deleted_at_front_becomes_preface():
    """最前方的条目被删：其内容落到前言（level 0），后续标题照常。"""
    lines = ["引子", "引言正文", "第一章 A", "正文 A"]
    data = [
        {"raw_title": "引子", "level": 3, "line": 1, "deleted": True},
        {"raw_title": "第一章 A", "level": 3, "line": 3},
    ]
    tree = tree_from_json(data, lines)
    assert tree[0].level == 0
    assert tree[0].class_name == "chapter"
    assert tree[0].paragraphs == ["引子", "引言正文"]
    assert tree[1].raw_title == "第一章 A"
    assert tree[1].paragraphs == ["正文 A"]


def test_tree_from_json_multiple_deleted_at_front():
    """顶部连续多条被删：合并成一个前言，不各起一个。"""
    lines = ["引子", "引言正文", "序章", "序章正文", "第一章 A", "正文 A"]
    data = [
        {"raw_title": "引子", "level": 3, "line": 1, "deleted": True},
        {"raw_title": "序章", "level": 3, "line": 3, "deleted": True},
        {"raw_title": "第一章 A", "level": 3, "line": 5},
    ]
    tree = tree_from_json(data, lines)
    assert tree[0].level == 0
    assert tree[0].paragraphs == ["引子", "引言正文", "序章", "序章正文"]
    assert tree[1].paragraphs == ["正文 A"]


def test_tree_from_json_all_deleted():
    """所有条目都被删：整篇作为前言，只剩一个 level 0 节点。"""
    lines = ["引子", "引言正文", "第一章 A", "正文 A"]
    data = [
        {"raw_title": "引子", "level": 3, "line": 1, "deleted": True},
        {"raw_title": "第一章 A", "level": 3, "line": 3, "deleted": True},
    ]
    tree = tree_from_json(data, lines)
    assert len(tree) == 1
    assert tree[0].level == 0
    assert tree[0].paragraphs == lines


def test_tree_from_json_preface_title_param():
    """`preface_title` 指定前言节点的标题。"""
    lines = ["引子", "引言正文"]
    data = [
        {"raw_title": "引子", "level": 3, "line": 1, "deleted": True},
    ]
    tree = tree_from_json(data, lines, preface_title="楔子")
    assert tree[0].title == "楔子"


def test_tree_from_json_no_delete_round_trip():
    """无删除条目时，回喂的树与 `parse()` 逐节点一致（回归）。"""
    from simple_ebook_converter.core.parser import parse, walk

    lines = ["第一卷", "第一章 一", "正文甲"]
    data = [
        {"raw_title": "第一卷", "level": 2, "class_name": "volume", "line": 1},
        {"raw_title": "第一章 一", "level": 3, "class_name": "chapter", "line": 2},
    ]
    restored = tree_from_json(data, lines)
    # 与 scan_toc 走 parse() 的结果逐节点比对（含子节点）
    from simple_ebook_converter.core.config import LevelRule

    rules = [LevelRule(2, r"^第一卷$", "volume"), LevelRule(3, r"^第一章 ", "chapter")]
    parsed, _ = parse(lines, rules, fallback_title="书名")
    assert [n.raw_title for n in walk(parsed)] == [n.raw_title for n in walk(restored)]
    for p, r in zip(walk(parsed), walk(restored)):
        assert p.paragraphs == r.paragraphs


def test_pipeline_read_book_deleted_entry_keeps_title_as_paragraph(tmp_path):
    """`read_book` 读了带 `deleted=true` 的目录：被删条目的标题行作为 `<p>` 留在前一条正文里。"""
    from simple_ebook_converter.core.config import Config
    from simple_ebook_converter.core.pipeline import read_book
    from simple_ebook_converter.core.sources import Sources

    input_file = tmp_path / "novel.txt"
    input_file.write_text(
        "第一章 A\n正文 A\n第100章 误匹配\n误捕的正文\n第二章 B\n正文 B\n",
        encoding="utf-8",
    )
    toc_entries = [
        {"raw_title": "第一章 A", "level": 3, "line": 1, "deleted": False},
        {"raw_title": "第100章 误匹配", "level": 3, "line": 3, "deleted": True},
        {"raw_title": "第二章 B", "level": 3, "line": 5, "deleted": False},
    ]
    book = read_book(
        cfg=Config(input=input_file), sources=Sources(toc_entries=toc_entries)
    )
    tree = book.tree
    assert [n.raw_title for n in tree] == ["第一章 A", "第二章 B"]
    # 被删条目 "第100章 误匹配" 的标题行出现在第一章的正文里
    assert "第100章 误匹配" in tree[0].paragraphs


def test_load_toc_reports_missing_file_bad_json_and_non_list(tmp_path):
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
        tree_from_json([{"level": 2, "line": 1}], lines)
    with pytest.raises(ValueError, match="层级不合法"):
        tree_from_json([{"raw_title": "x", "level": 9, "line": 1}], lines)
    with pytest.raises(ValueError, match="行号不合法"):
        tree_from_json([{"raw_title": "x", "level": 2, "line": "1"}], lines)
    # True 是 bool，不能当 1 通过
    with pytest.raises(ValueError, match="行号不合法"):
        tree_from_json([{"raw_title": "x", "level": 2, "line": True}], lines)
    with pytest.raises(ValueError, match="行号超出输入范围"):
        tree_from_json([{"raw_title": "x", "level": 2, "line": 5}], lines)
    with pytest.raises(ValueError, match="deleted 只能是"):
        tree_from_json(
            [{"raw_title": "x", "level": 2, "line": 1, "deleted": "yes"}], lines
        )
    with pytest.raises(ValueError, match="不是 JSON 对象"):
        tree_from_json(["不是字典"], lines)


def test_tree_from_json_rejects_multiple_level_zero():
    """多个 level 0（前言）会撞 anchor='preface'、生成重名 xhtml，直接拒绝。"""
    lines = ["前言一", "前言二", "第一章", "正文"]
    data = [
        {"raw_title": "前言一", "level": 0, "line": 1},
        {"raw_title": "前言二", "level": 0, "line": 2},
        {"raw_title": "第一章", "level": 2, "line": 3},
    ]
    with pytest.raises(ValueError, match="只能有一个 level 0"):
        tree_from_json(data, lines)


def test_tree_from_json_keeps_an_empty_class_name():
    """classless 层级（`--level h1:…`）的 class 是空串，回喂后原样保留，不能补成 levelN。"""
    data = [{"raw_title": "Part 1", "level": 1, "class_name": "", "line": 1}]
    restored = tree_from_json(data, ["Part 1", "正文"])
    assert restored[0].class_name == ""
