from sec.config import LevelRule, default_levels
from sec.parser import NoEnabledRulesError, parse

import pytest


def test_volume_chapter_nesting():
    lines = [
        "封面文案",
        "第一卷 风起",
        "第一章 初遇",
        "正文一字",
        "第二章 离别",
        "正文二字",
        "第二卷 云散",
        "第三章 重逢",
        "正文三字",
    ]
    tree, stats = parse(lines, default_levels(), fallback_title="书名")
    assert stats.has_preface is True
    assert stats.level_counts == {2: 2, 3: 3}
    assert len(tree) == 3
    assert tree[0].title == "前言"
    assert tree[0].level == 0
    assert tree[0].paragraphs == ["封面文案"]
    vol1 = tree[1]
    assert vol1.title == "第一卷 风起"
    assert vol1.level == 2
    assert [c.title for c in vol1.children] == ["第一章 初遇", "第二章 离别"]
    assert vol1.paragraphs == []
    assert vol1.children[0].paragraphs == ["正文一字"]
    assert tree[2].title == "第二卷 云散"


def test_no_volume_top_level_chapters():
    lines = ["第一章 a", "正文一", "第二章 b", "正文二"]
    tree, _ = parse(lines, default_levels(), fallback_title="书名")
    assert len(tree) == 2
    assert [n.title for n in tree] == ["第一章 a", "第二章 b"]


def test_no_titles_single_chapter():
    lines = ["第1行", "随便写点什么", "第3行"]
    tree, stats = parse(lines, default_levels(), fallback_title="书名")
    assert len(tree) == 1
    assert tree[0].title == "书名"
    assert tree[0].paragraphs == lines


def test_special_titles_match_chapter():
    lines = ["楔子", "引", "序章", "正文", "最终章 决战", "正文二", "番外 日常", "正文三", "完本感言"]
    tree, _ = parse(lines, default_levels(), fallback_title="书名")
    assert [n.title for n in tree] == ["楔子", "序章", "最终章 决战", "番外 日常", "完本感言"]


def test_english_and_numbered_titles_match_chapter():
    lines = ["Chapter 1", "正文一", "Section 2", "正文二", "Page 3", "正文三", "12", "正文四", "5、", "正文五"]
    tree, _ = parse(lines, default_levels(), fallback_title="书名")
    assert [n.title for n in tree] == ["Chapter 1", "Section 2", "Page 3", "12", "5、"]


def test_pian_not_volume():
    lines = ["第一篇 习作", "这一篇应该不是卷"]
    tree, _ = parse(lines, default_levels(), fallback_title="书名")
    assert len(tree) == 1
    assert tree[0].title == "书名"


def test_traditional_chinese_titles():
    lines = ["第二部 風雲", "第一章 相遇", "正文一", "第五節 夜", "正文二"]
    tree, _ = parse(lines, default_levels(), fallback_title="书名")
    assert tree[0].title == "第二部 風雲"
    assert tree[0].level == 2
    assert [c.title for c in tree[0].children] == ["第一章 相遇", "第五節 夜"]
    assert tree[0].children[1].level == 3


def test_japanese_titles():
    lines = ["第一巻 出会い", "第一話 始まり", "正文一", "第五節 夜", "正文二"]
    tree, _ = parse(lines, default_levels(), fallback_title="书名")
    assert tree[0].title == "第一巻 出会い"
    assert tree[0].level == 2
    assert [c.title for c in tree[0].children] == ["第一話 始まり", "第五節 夜"]


def test_trailing_content_merges_into_last_chapter():
    lines = ["第一章 a", "正文", "结尾杂句"]
    tree, _ = parse(lines, default_levels(), fallback_title="书名")
    assert tree[0].paragraphs == ["正文", "结尾杂句"]


def test_max_title_len():
    lines = ["第一章 " + "x" * 50, "这行不是标题"]
    tree, _ = parse(lines, default_levels(), max_title_len=35, fallback_title="书名")
    assert len(tree) == 1
    assert tree[0].title == "书名"
    assert len(tree[0].paragraphs) == 2


def test_custom_level_hierarchy():
    levels = default_levels()
    levels.append(LevelRule(4, r"^※小节\d*", "section"))
    lines = [
        "第一章 a",
        "※小节一",
        "正文",
        "※小节二",
    ]
    tree, stats = parse(lines, levels, fallback_title="书名")
    assert stats.max_level == 4
    ch = tree[0]
    assert [s.title for s in ch.children] == ["※小节一", "※小节二"]


def test_no_volume_flag_ignores_volume():
    lines = ["第一卷 甲", "第一章 a", "正文"]
    tree, _ = parse(lines, default_levels(), no_volume=True, fallback_title="书名")
    assert [n.title for n in tree] == ["前言", "第一章 a"]
    assert tree[0].paragraphs == ["第一卷 甲"]
    assert tree[1].paragraphs == ["正文"]


def test_no_enabled_rules():
    with pytest.raises(NoEnabledRulesError):
        parse([], [LevelRule(2, "", "volume")], fallback_title="x")


def test_empty_input():
    tree, _ = parse([], default_levels(), fallback_title="x")
    assert tree == []