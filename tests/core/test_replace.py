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
    rules_from_file,
    rules_from_json,
    rules_from_list,
    rules_from_rows,
    rules_to_json,
    rules_to_list,
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


def test_apply_reports_a_hit():
    assert Replacer.of([Rule("起", "起风")]).apply("风起") == ("风起风", True)


def test_apply_reports_a_miss():
    assert Replacer.of([Rule("起", "起风")]).apply("云散") == ("云散", False)


def test_apply_counts_a_hit_that_changes_nothing():
    """替换文本与原文相同也算命中：规则确实作用过，界面要标出来。"""
    assert Replacer.of([Rule("<b>", "<b>")]).apply("<b>") == ("<b>", True)


def test_apply_reports_a_hit_from_any_rule_in_the_chain():
    replacer = Replacer.of([Rule("无", "有"), Rule("云", "风")])
    assert replacer.apply("云散") == ("风散", True)


def test_apply_on_empty_replacer_is_a_miss():
    assert Replacer.of([]).apply("原样") == ("原样", False)


def test_text_is_the_apply_result_without_the_flag():
    replacer = Replacer.of([Rule("起", "起风")])
    assert replacer.text("风起") == replacer.apply("风起")[0]


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


def test_replacers_by_stage_skips_disabled():
    raw, _html = replacers_by_stage([Rule("a", "1", enabled=False), Rule("b", "2")])
    assert [r.pattern for r in raw.rules] == ["b"]


def test_replacers_by_stage_skips_empty_pattern():
    """空 pattern 不是「没填完」，是没有可匹配的东西：`re.compile("")` 匹配每个位置，
    放行等于把替换文本插到标题的每个字符之间（"第一卷" → "X第X一X卷X"）。"""
    raw, _html = replacers_by_stage([Rule("", "X", enabled=True), Rule("卷", "Y")])
    assert [r.pattern for r in raw.rules] == ["卷"]
    assert raw.apply("第一卷") == ("第一Y", True)


def test_replacers_by_stage_guards_a_hand_edited_config():
    """配置文件可手改，一条空 pattern 的启用规则就能毁掉全书标题——所以在 core 拦。

    GUI 那边（collect_rules）照样原样保存空卡片，这里拦的是「作用到文本上」这一步。
    """
    saved = [{"pattern": "", "replace": "X", "stage": "raw", "enabled": True}]
    raw, _html = replacers_by_stage(rules_from_list(saved))
    assert raw.apply("第一卷") == ("第一卷", False)


# ---------- 解析 ----------


def test_rules_from_json_without_stage_is_raw():
    assert rules_from_json(json.dumps([{"pattern": "a", "replace": "b"}])) == [
        Rule("a", "b", "raw")
    ]


def test_rules_from_json_accepts_empty_list():
    assert rules_from_json("[]") == []


@pytest.mark.parametrize(
    "text", ['{"pattern": "甲"}', '[{"replace": "乙"}]', "not json", '[{"pattern": 1}]']
)
def test_rules_from_json_rejects_invalid_payload(text):
    with pytest.raises(ValueError):
        rules_from_json(text)


def test_rules_from_json_rejects_an_uncompilable_pattern():
    with pytest.raises(ValueError) as exc:
        rules_from_json('[{"pattern": "甲", "replace": "乙"}, {"pattern": "("}]')
    msg = str(exc.value)
    assert "正则非法" in msg  # 文案只匹关键词，改措辞不该挂
    assert "第 2 条" in msg  # 索引是契约：得指向出事的那一条


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
    with pytest.raises(ValueError) as exc:
        rules_from_json(json.dumps([{"pattern": "a", "stage": "chapter"}]))
    msg = str(exc.value)
    assert "阶段只能是" in msg
    assert "第 1 条" in msg  # 索引
    assert "'chapter'" in msg  # 收到的值要回显，否则用户不知道错在哪


def test_rules_from_json_rejects_non_string_stage():
    with pytest.raises(ValueError, match="阶段只能是"):
        rules_from_json(json.dumps([{"pattern": "a", "stage": 1}]))


def test_rules_from_rows_skips_blank_pattern():
    assert rules_from_rows([("", "x", "原文"), ("a", "b", "HTML")]) == [
        Rule("a", "b", "html")
    ]


def test_rules_from_rows_accepts_short_rows():
    assert rules_from_rows([("a", "b")]) == [Rule("a", "b", "raw")]


def test_rules_from_rows_passes_rules_through():
    rule = Rule("a", "b", "html")
    assert rules_from_rows([rule]) == [rule]


def test_rules_from_rows_rejects_unknown_label():
    with pytest.raises(ValueError) as exc:
        rules_from_rows([("a", "b", "第1章")])
    msg = str(exc.value)
    assert "阶段只能是" in msg
    assert "规则「a」" in msg  # 是哪个查找词出错，要比文案更重要
    assert "'第1章'" in msg


def test_rules_from_file_reads_file(tmp_path):
    path = tmp_path / "rules.json"
    path.write_text('[{"pattern": "a", "stage": "html"}]', encoding="utf-8")
    assert rules_from_file(path) == [Rule("a", "", "html")]


def test_rules_from_file_empty_path_is_empty():
    """没给路径 = 没有规则，不是错误。"""
    assert rules_from_file(None) == []
    assert rules_from_file("") == []


def test_rules_from_file_empty_file_is_empty(tmp_path):
    path = tmp_path / "rules.json"
    path.write_text("", encoding="utf-8")
    assert rules_from_file(path) == []


def test_rules_from_file_reports_unreadable_file(tmp_path):
    with pytest.raises(ValueError, match="无法读取替换规则文件"):
        rules_from_file(tmp_path / "nope.json")


# ---------- 序列化 ----------


def test_rules_to_json_always_writes_stage():
    assert json.loads(rules_to_json([Rule("a", "b")])) == [
        {"pattern": "a", "replace": "b", "stage": "raw", "enabled": True}
    ]


def test_rules_to_json_round_trips():
    rules = [Rule("a", "1", "html"), Rule("b", "2", "raw")]
    assert rules_from_json(rules_to_json(rules)) == rules


def test_rules_to_list_equals_json_payload():
    rules = [Rule("a", "1", "html", enabled=False), Rule("b", "2")]
    assert rules_from_list(rules_to_list(rules)) == rules
    assert rules_to_list(rules) == json.loads(rules_to_json(rules))


def test_rules_from_list_rejects_non_list():
    with pytest.raises(ValueError, match="必须是 JSON 列表"):
        rules_from_list({"pattern": "a"})
