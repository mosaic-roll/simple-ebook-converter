import json

import pytest

from simple_ebook_converter.core.replace import (
    DEFAULT_STAGE,
    STAGE_BY_LABEL,
    STAGE_LABELS,
    STAGES,
    Replacer,
    Rule,
    check_stage,
    replacers_by_stage,
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


def test_empty_replacer_is_identity():
    assert Replacer.of([]).text("原样") == "原样"


# ---------- 阶段 ----------


def test_stage_defaults_to_raw():
    assert DEFAULT_STAGE == "raw"
    assert Rule("a", "b").stage == "raw"


def test_stage_choices_and_labels_cover_every_choice():
    """`STAGES` 是唯一一处真相：取值与中文标签都在这一张表里。"""
    assert tuple(STAGES) == ("raw", "html")
    assert set(STAGE_LABELS) == set(STAGES)
    assert set(STAGE_BY_LABEL) == set(STAGE_LABELS.values())
    assert list(STAGE_LABELS.values()) == ["原文", "HTML"]


def test_check_stage_passes_through():
    for stage in STAGES:
        assert check_stage(stage) == stage


def test_check_stage_accepts_labels():
    """GUI 表格里存的是中文标签，core 负责翻译。"""
    for stage, label in STAGE_LABELS.items():
        assert check_stage(label) == stage


def test_check_stage_error_has_no_prefix_by_default():
    with pytest.raises(ValueError, match="^阶段只能是"):
        check_stage("nope")


def test_check_stage_error_mentions_where():
    with pytest.raises(ValueError, match="^规则「a」的 "):
        check_stage("nope", "规则「a」")


def test_stage_label_property():
    assert Rule("a", "b", "html").stage_label == "HTML"


def test_replacers_by_stage_partitions_rules():
    rules = [Rule("r", "1", "raw"), Rule("h", "2", "html"), Rule("r2", "3", "raw")]
    raw, html = replacers_by_stage(rules)
    assert [r.pattern for r in raw.rules] == ["r", "r2"]
    assert [r.pattern for r in html.rules] == ["h"]
    assert raw.text("r") == "1"
    assert html.text("h") == "2"


def test_replacers_by_stage_on_empty():
    raw, html = replacers_by_stage([])
    assert raw.rules == () and html.rules == ()


# ---------- 解析 ----------


def test_rules_from_json_without_stage_is_raw():
    assert rules_from_json(json.dumps([{"pattern": "a", "replace": "b"}])) == [
        Rule("a", "b", "raw")
    ]


def test_rules_from_json_reads_stage():
    rules = rules_from_json(
        json.dumps(
            [
                {"pattern": "a", "replace": "1", "stage": "raw"},
                {"pattern": "b", "replace": "2", "stage": "html"},
            ]
        )
    )
    assert [r.stage for r in rules] == ["raw", "html"]


def test_rules_from_json_rejects_unknown_stage():
    with pytest.raises(ValueError, match="第 1 条替换规则的 阶段只能是"):
        rules_from_json(json.dumps([{"pattern": "a", "stage": "chapter"}]))


def test_rules_from_json_rejects_non_string_stage():
    with pytest.raises(ValueError, match="阶段只能是"):
        rules_from_json(json.dumps([{"pattern": "a", "stage": 1}]))


def test_rules_from_rows_skips_blank_pattern():
    assert rules_from_rows([("", "x", "原文"), ("a", "b", "HTML")]) == [Rule("a", "b", "html")]


def test_rules_from_rows_accepts_short_rows():
    assert rules_from_rows([("a", "b")]) == [Rule("a", "b", "raw")]


def test_rules_from_rows_passes_rules_through():
    rule = Rule("a", "b", "html")
    assert rules_from_rows([rule]) == [rule]


def test_rules_from_rows_rejects_unknown_label():
    with pytest.raises(ValueError, match=r"规则「a」的 阶段只能是 原文/HTML"):
        rules_from_rows([("a", "b", "第1章")])


def test_rules_from_source_from_text():
    assert rules_from_source('[{"pattern": "a"}]') == [Rule("a", "", "raw")]


def test_rules_from_source_from_file(tmp_path):
    path = tmp_path / "rules.json"
    path.write_text('[{"pattern": "a", "stage": "html"}]', encoding="utf-8")
    assert rules_from_source(file=path) == [Rule("a", "", "html")]


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


def test_rules_to_json_always_writes_stage():
    assert json.loads(rules_to_json([Rule("a", "b")])) == [
        {"pattern": "a", "replace": "b", "stage": "raw", "enabled": True}
    ]


def test_rules_to_json_round_trips():
    rules = [Rule("a", "1", "html"), Rule("b", "2", "raw")]
    assert rules_from_json(rules_to_json(rules)) == rules
