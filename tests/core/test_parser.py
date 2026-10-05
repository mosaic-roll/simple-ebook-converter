import pytest

from simple_ebook_converter.core.config import (
    DEFAULT_CHAPTER_RE,
    DEFAULT_VOLUME_RE,
    LevelRule,
    default_levels,
)
from simple_ebook_converter.core.levels import build_rules
from simple_ebook_converter.core.parser import NoEnabledRulesError, parse, walk


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
    tree, _stats = parse(lines, default_levels(), fallback_title="书名")
    assert len(tree) == 1
    assert tree[0].title == "书名"
    assert tree[0].paragraphs == lines


def test_special_titles_match_chapter():
    lines = [
        "楔子",
        "引",
        "序章",
        "正文",
        "最终章 决战",
        "正文二",
        "番外 日常",
        "正文三",
        "完本感言",
    ]
    tree, _ = parse(lines, default_levels(), fallback_title="书名")
    assert [n.title for n in tree] == [
        "楔子",
        "序章",
        "最终章 决战",
        "番外 日常",
        "完本感言",
    ]


def test_english_and_numbered_titles_match_chapter():
    lines = [
        "Chapter 1",
        "正文一",
        "Section 2",
        "正文二",
        "12",
        "正文三",
        "5、",
        "正文四",
    ]
    tree, _ = parse(lines, default_levels(), fallback_title="书名")
    # 纯数字和数字+顿号不再匹配章标题（容易误报）；Section 也不匹配（已移除）
    assert [n.title for n in tree] == ["Chapter 1"]


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
    levels = build_rules(
        [LevelRule(2, "", "volume"), LevelRule(3, DEFAULT_CHAPTER_RE, "chapter")]
    )
    tree, _ = parse(lines, levels, fallback_title="书名")
    assert [n.title for n in tree] == ["前言", "第一章 a"]
    assert tree[0].paragraphs == ["第一卷 甲"]
    assert tree[1].paragraphs == ["正文"]


def test_level_wins_over_priority():
    """先比级别：h1 的额外层级比卷（h2）级别低，所以仍先被试。"""
    levels = build_rules([LevelRule(1, "^第一卷", "part")])
    tree, _ = parse(["第一卷 甲", "正文"], levels, fallback_title="书名")
    assert [(n.level, n.class_name) for n in tree] == [(1, "part")]


def test_builtin_wins_within_one_level():
    """同级比优先级：内置卷的 class 赢过用户写的 h2 规则。"""
    levels = build_rules(
        [
            LevelRule(2, DEFAULT_VOLUME_RE, "volume"),
            LevelRule(2, "^第一卷", "part"),
            LevelRule(3, DEFAULT_CHAPTER_RE, "chapter"),
        ]
    )
    tree, _ = parse(["第一卷 甲", "第一章 a"], levels, fallback_title="书名")
    assert [(n.level, n.class_name) for n in walk(tree)] == [
        (2, "volume"),
        (3, "chapter"),
    ]


def test_first_written_wins_within_one_level():
    """同级里写在前面的先试，命中后同一行不再试后面的规则。"""
    levels = build_rules([LevelRule(5, "^※", "note"), LevelRule(5, "^※", "scene")])
    tree, _ = parse(["※甲", "正文"], levels, fallback_title="书名")
    assert [(n.level, n.class_name) for n in tree] == [(5, "note")]


def test_same_class_specs_work_as_an_ordered_set():
    """同 class 拆成多条：第一条没命中的行交给下一条，内置那条已经让位。"""
    levels = build_rules(
        [LevelRule(2, "^第一卷", "volume"), LevelRule(2, "^第.+部", "volume")]
    )
    tree, _ = parse(
        ["第一卷 甲", "第二卷 乙", "第一部 丙"], levels, fallback_title="书名"
    )
    assert [(n.class_name, n.title) for n in tree] == [
        ("volume", "第一卷 甲"),
        ("volume", "第一部 丙"),
    ]
    assert "第二卷 乙" in tree[0].paragraphs


def test_no_enabled_rules():
    with pytest.raises(NoEnabledRulesError):
        parse([], [LevelRule(2, "", "volume")], fallback_title="x")


def test_no_enabled_rules_is_value_error():
    assert issubclass(NoEnabledRulesError, ValueError)
    with pytest.raises(ValueError):
        parse([], [LevelRule(2, "", "volume")], fallback_title="x")


def test_empty_input():
    tree, _ = parse([], default_levels(), fallback_title="x")
    assert tree == []


def test_anchors_number_chapters_and_pin_preface():
    lines = ["前言内容", "第一卷 风起", "第一章 a", "第二章 b", "尾句"]
    tree, _ = parse(lines, default_levels(), fallback_title="书名")
    assert [n.anchor for n in walk(tree)] == ["preface", "p0001", "p0002", "p0003"]


def test_titles_are_stripped_but_paragraphs_are_not():
    tree, _ = parse(["  第一章 a  ", "　正文　"], default_levels(), fallback_title="x")
    assert tree[0].title == "第一章 a"
    assert tree[0].raw_title == "第一章 a"
    assert tree[0].paragraphs == ["　正文　"]


def test_paragraphs_follow_the_nearest_heading():
    lines = [
        "第一卷 甲",
        "卷内正文",
        "第一章 a",
        "正文一",
        "第二章 b",
        "正文二",
        "结尾",
    ]
    tree, _ = parse(lines, default_levels(), fallback_title="书名")
    (volume,) = tree
    first, second = volume.children
    assert volume.paragraphs == ["卷内正文"]
    assert first.paragraphs == ["正文一"]
    assert second.paragraphs == ["正文二", "结尾"]


def test_classless_level_has_empty_class_name():
    """`--level h1:…` 不带 class，节点就不带 class（落到 hN 标签选择器）。"""
    tree, _ = parse(
        ["Part 1", "正文"], build_rules([LevelRule(1, "^Part")]), fallback_title="书名"
    )
    assert tree[0].level == 1
    assert tree[0].class_name == ""


def test_exclude_blocks_a_title_that_matches_levels():
    """排除规则命中时，行降级为正文而不是标题。"""
    levels = build_rules([LevelRule(3, "^第.章", "chapter")])
    tree, _ = parse(
        ["第一章 开端", "排除这条", "第二章 发展"],
        levels,
        fallback_title="书名",
        exclude="^排除",
    )
    titles = [n.title for n in walk(tree)]
    assert "第一章 开端" in titles
    assert "排除这条" not in titles
    assert "第二章 发展" in titles
    # 被排除的行成了上一章的正文
    assert "排除这条" in tree[0].paragraphs
