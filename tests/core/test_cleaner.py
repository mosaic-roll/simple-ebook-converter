from simple_ebook_converter.core.cleaner import clean_line, clean_lines


def test_strip_leading():
    assert clean_line("  第1段") == "第1段"
    assert clean_line("\u3000\u3000全角开头") == "全角开头"
    assert clean_line("\t tab开头") == "tab开头"


def test_strip_trailing():
    assert clean_line("结尾  ") == "结尾"
    assert clean_line("结尾\u3000") == "结尾"


def test_strip_both():
    assert clean_line("  中间有 空格  ") == "中间有 空格"


def test_remove_empty_lines():
    assert clean_lines(["a", "", "  ", "b"]) == ["a", "b"]


def test_keep_inner_spaces():
    assert clean_lines(["保留  中间 空格"]) == ["保留  中间 空格"]
