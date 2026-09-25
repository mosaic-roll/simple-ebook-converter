import pytest

from sec.encoding import EncodingError, decode, read_lines


def test_bom_utf8():
    raw = b"\xef\xbb\xbf" + "第一行\r\n第二行".encode("utf-8")
    text, enc = decode(raw)
    assert enc == "utf-8-sig"
    assert text.splitlines() == ["第一行", "第二行"]


def test_utf16_le_bom():
    raw = b"\xff\xfe" + "第一行\n第二行".encode("utf-16-le")
    text, enc = decode(raw)
    assert enc == "utf-16-le"
    assert text.startswith("第一行")


def test_utf8_plain():
    raw = "第一行\n第二行".encode("utf-8")
    text, enc = decode(raw)
    assert enc == "utf-8"
    assert text == "第一行\n第二行"


def test_gb18030():
    raw = "中文测试".encode("gb18030")
    text, enc = decode(raw)
    assert "中文" in text
    assert enc == "gb18030"


def test_manual_encoding():
    raw = "中文".encode("gb18030")
    text, enc = decode(raw, encoding="gb18030")
    assert enc == "gb18030"


def test_manual_wrong_encoding():
    raw = "中文".encode("gb18030")
    with pytest.raises(EncodingError):
        decode(raw, encoding="utf-8")


def test_read_lines(tmp_path):
    p = tmp_path / "a.txt"
    p.write_bytes("行一\r\n行二\r\n行三".encode("utf-8"))
    lines, enc = read_lines(p)
    assert lines == ["行一", "行二", "行三"]
    assert enc == "utf-8"