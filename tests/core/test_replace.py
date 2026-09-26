import json

import pytest

from simple_ebook_converter.core.replace import (
    DEFAULT_SCOPE,
    SCOPE_ALL,
    SCOPE_BODY,
    SCOPE_CHOICES,
    SCOPE_LABELS,
    SCOPE_TITLE,
    Rule,
    apply,
    apply_lines,
    check_scope,
    compile_rules,
    rules_from_json,
    rules_to_json,
    split_by_scope,
)


def test_ordered_rules():
    rules = [
        Rule(r"^#+\s*", ""),
        Rule(r"　", " "),
    ]
    assert apply("## 标题　后", rules) == "标题 后"


def test_apply_lines_empty_rules():
    lines = ["a", "b"]
    assert apply_lines(lines, []) == lines


def test_compile_invalid_pattern_raises():
    with pytest.raises(ValueError, match="正则非法"):
        rules_from_json(json.dumps([{"pattern": "["}]))


# ---------- 作用范围 ----------


def test_scope_defaults_to_title():
    assert DEFAULT_SCOPE == SCOPE_TITLE
    assert Rule("a", "b").scope == SCOPE_TITLE


def test_scope_choices_and_labels_cover_every_choice():
    assert SCOPE_CHOICES == (SCOPE_TITLE, SCOPE_BODY, SCOPE_ALL)
    assert set(SCOPE_LABELS) == set(SCOPE_CHOICES)
    assert SCOPE_LABELS[SCOPE_TITLE] == "标题"
    assert SCOPE_LABELS[SCOPE_BODY] == "正文"
    assert SCOPE_LABELS[SCOPE_ALL] == "全文"


def test_rules_from_json_without_scope_is_title():
    (rule,) = rules_from_json(json.dumps([{"pattern": "a", "replace": "b"}]))
    assert rule == Rule("a", "b", SCOPE_TITLE)


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
    with pytest.raises(ValueError, match="第 1 条替换规则的 scope 只能是 title/body/all"):
        rules_from_json(json.dumps([{"pattern": "a", "scope": "chapter"}]))


def test_rules_from_json_rejects_non_string_scope():
    with pytest.raises(ValueError, match="scope 只能是"):
        rules_from_json(json.dumps([{"pattern": "a", "scope": 1}]))


def test_check_scope_passes_through():
    for scope in SCOPE_CHOICES:
        assert check_scope(scope) == scope


def test_check_scope_error_has_no_index_prefix():
    with pytest.raises(ValueError, match="^scope 只能是"):
        check_scope("nope")


def test_split_by_scope_partitions_rules():
    rules = [
        Rule("t", "1", SCOPE_TITLE),
        Rule("b", "2", SCOPE_BODY),
        Rule("a", "3", SCOPE_ALL),
    ]
    title, body = split_by_scope(rules)
    assert [r.pattern for r in title] == ["t", "a"]
    assert [r.pattern for r in body] == ["b", "a"]


def test_split_by_scope_on_empty():
    assert split_by_scope([]) == ([], [])


def test_scope_label_property():
    assert Rule("a", "b", SCOPE_BODY).scope_label == "正文"


# ---------- 序列化 ----------


def test_rules_to_json_always_writes_scope():
    text = rules_to_json([Rule("a", "b")])
    assert json.loads(text) == [{"pattern": "a", "replace": "b", "scope": SCOPE_TITLE}]


def test_rules_to_json_round_trips():
    rules = [Rule("a", "1", SCOPE_BODY), Rule("b", "2", SCOPE_ALL)]
    assert rules_from_json(rules_to_json(rules)) == rules


def test_compile_rules_keeps_order():
    rules = [Rule("a", ""), Rule("b", "")]
    assert [p.pattern for p in compile_rules(rules)] == ["a", "b"]
