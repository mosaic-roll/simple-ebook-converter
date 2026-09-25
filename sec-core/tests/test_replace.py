from sec_core.replace import Rule, apply, apply_lines


def test_ordered_rules():
    rules = [
        Rule(r"^#+\s*", ""),
        Rule(r"\u3000", " "),
    ]
    assert apply("## 标题\u3000后", rules) == "标题 后"


def test_apply_lines_empty_rules():
    lines = ["a", "b"]
    assert apply_lines(lines, []) == lines


def test_compile_invalid_pattern_raises():
    import pytest
    import re

    with pytest.raises(re.error):
        Rule("[", "x").compile()