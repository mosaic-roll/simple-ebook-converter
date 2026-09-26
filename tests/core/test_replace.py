import json

import pytest

from simple_ebook_converter.core.replace import (
    DEFAULT_SCOPE,
    SCOPE_ALL,
    SCOPE_BODY,
    SCOPE_CHOICES,
    SCOPE_LABELS,
    SCOPE_TITLE,
    Replacer,
    Rule,
    check_scope,
    replacers_by_scope,
    rules_from_json,
    rules_from_rows,
    rules_from_source,
    rules_to_json,
)


def test_ordered_rules():
    replacer = Replacer.of([Rule(r"^#+\s*", ""), Rule(r"　", " ")])
    assert replacer.text("## 标题　后") == "标题 后"


def test_replacer_compiles_once_and_keeps_order():
    replacer = Replacer.of([Rule("a", "1"), Rule("b", "2")])
    assert [p.pattern for p in replacer.patterns] == ["a", "b"]
    assert replacer.text("ab") == "12"


def test_replacer_lines():
    assert Replacer.of([Rule("a", "b")]).lines(["a", "a"]) == ["b", "b"]


def test_empty_replacer_is_identity():
    empty = Replacer.of([])
    assert empty.text("原样") == "原样"
    assert empty.lines(["a", "b"]) == ["a", "b"]


# ---------- 作用范围 ----------


def test_scope_defaults_to_title():
    assert DEFAULT_SCOPE == SCOPE_TITLE
    assert Rule("a", "b").scope == SCOPE_TITLE


def test_scope_choices_and_labels_cover_every_choice():
    assert SCOPE_CHOICES == (SCOPE_TITLE, SCOPE_BODY, SCOPE_ALL)
    assert set(SCOPE_LABELS) == set(SCOPE_CHOICES)
    assert list(SCOPE_LABELS.values()) == ["标题", "正文", "全文"]


def test_check_scope_passes_through():
    for scope in SCOPE_CHOICES:
        assert check_scope(scope) == scope


def test_check_scope_accepts_labels():
    """GUI 表格里存的是中文标签，core 负责翻译。"""
    for scope, label in SCOPE_LABELS.items():
        assert check_scope(label) == scope


def test_check_scope_error_has_no_prefix_by_default():
    with pytest.raises(ValueError, match="^作用范围只能是"):
        check_scope("nope")


def test_check_scope_error_mentions_where():
    with pytest.raises(ValueError, match="^规则「a」的 "):
        check_scope("nope", "规则「a」")


def test_scope_label_property():
    assert Rule("a", "b", SCOPE_BODY).scope_label == "正文"


def test_replacers_by_scope_partitions_rules():
    rules = [Rule("t", "1", SCOPE_TITLE), Rule("b", "2", SCOPE_BODY), Rule("a", "3", SCOPE_ALL)]
    titles, bodies = replacers_by_scope(rules)
    assert [r.pattern for r in titles.rules] == ["t", "a"]
    assert [r.pattern for r in bodies.rules] == ["b", "a"]
    assert titles.text("ta") == "13"
    assert bodies.lines(["ba"]) == ["23"]


def test_replacers_by_scope_on_empty():
    titles, bodies = replacers_by_scope([])
    assert titles.rules == () and bodies.rules == ()


# ---------- 解析 ----------


def test_rules_from_json_without_scope_is_title():
    assert rules_from_json(json.dumps([{"pattern": "a", "replace": "b"}])) == [
        Rule("a", "b", SCOPE_TITLE)
    ]


def test_rules_from_json_reads_scope():
    rules = rules_from_json(
        json.dumps(
            [
                {"pattern": "a", "replace": "1", "scope": "body"},
                {"pattern": "b", "replace": "2", "scope": "all"},
            ]
        )
    )
    assert [r.scope for r in rules] == [SCOPE_BODY, SCOPE_ALL]


def test_rules_from_json_rejects_unknown_scope():
    with pytest.raises(ValueError, match="第 1 条替换规则的 作用范围只能是"):
        rules_from_json(json.dumps([{"pattern": "a", "scope": "chapter"}]))


def test_rules_from_json_rejects_non_string_scope():
    with pytest.raises(ValueError, match="作用范围只能是"):
        rules_from_json(json.dumps([{"pattern": "a", "scope": 1}]))


def test_rules_from_rows_skips_blank_pattern():
    assert rules_from_rows([("", "x", "标题"), ("a", "b", "正文")]) == [Rule("a", "b", SCOPE_BODY)]


def test_rules_from_rows_accepts_short_rows():
    assert rules_from_rows([("a", "b")]) == [Rule("a", "b", SCOPE_TITLE)]


def test_rules_from_rows_passes_rules_through():
    rule = Rule("a", "b", SCOPE_ALL)
    assert rules_from_rows([rule]) == [rule]


def test_rules_from_rows_rejects_unknown_label():
    with pytest.raises(ValueError, match=r"规则「a」的 作用范围只能是 标题/正文/全文"):
        rules_from_rows([("a", "b", "第1章")])


def test_rules_from_source_from_text():
    assert rules_from_source('[{"pattern": "a"}]') == [Rule("a", "", SCOPE_TITLE)]


def test_rules_from_source_from_file(tmp_path):
    path = tmp_path / "rules.json"
    path.write_text('[{"pattern": "a", "scope": "body"}]', encoding="utf-8")
    assert rules_from_source(file=path) == [Rule("a", "", SCOPE_BODY)]


def test_rules_from_source_rejects_both(tmp_path):
    path = tmp_path / "rules.json"
    path.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="只能给一处"):
        rules_from_source("[]", path)


def test_rules_from_source_empty():
    assert rules_from_source() == []


def test_rules_from_source_reports_unreadable_file(tmp_path):
    with pytest.raises(ValueError, match="无法读取替换规则文件"):
        rules_from_source(file=tmp_path / "nope.json")


# ---------- 序列化 ----------


def test_rules_to_json_always_writes_scope():
    assert json.loads(rules_to_json([Rule("a", "b")])) == [
        {"pattern": "a", "replace": "b", "scope": SCOPE_TITLE}
    ]


def test_rules_to_json_round_trips():
    rules = [Rule("a", "1", SCOPE_BODY), Rule("b", "2", SCOPE_ALL)]
    assert rules_from_json(rules_to_json(rules)) == rules
