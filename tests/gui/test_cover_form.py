"""`cover_from_form()`：GUI 封面组的三个控件 → core 的 `Resource | None`。

这里最要紧的是**空串**。GUI 封面框清空传下来的是 `""`，那不是「没填」而是「用户说了
不要封面」；写成 `or None` 就会被系统替他从同目录翻一张 cover.png 出来。
"""

from pathlib import Path

import pytest

from simple_ebook_converter.gui.app import cover_from_form


class FakeEntry:
    def __init__(self, text=""):
        self._text = text

    def get(self):
        return self._text


class FakeVar:
    def __init__(self, value):
        self._value = value

    def get(self):
        return self._value


def _tab(tmp_path, *, cover="", input_txt=None, discovery=True):
    # 源文件默认给 tmp_path 里那个**真实路径**：写死相对路径的话 `cover_for()` 里的
    # `Path(input).parent` 会指向 cwd，测试目录里的 cover.png 就永远找不到，
    # 「空串会不会被自动发现顶掉」这条断言就成了假通过。
    source = tmp_path / "novel.txt" if input_txt is None else input_txt
    return {
        "cover_entry": FakeEntry(cover),
        "input_entry": FakeEntry(str(source)),
        "cover_discovery_var": FakeVar(discovery),
    }


def _png(tmp_path):
    path = tmp_path / "cover.png"
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 8)
    return path


@pytest.fixture
def book(tmp_path):
    (tmp_path / "novel.txt").write_text("第一章 甲\n正文", encoding="utf-8")
    return tmp_path / "novel.txt"


def test_blank_cover_box_means_no_cover(tmp_path, book):
    """框清空了 = 不要封面。同目录明明有 cover.png，也不许去拿。"""
    _png(tmp_path)
    assert cover_from_form(_tab(tmp_path)) is None


def test_blank_cover_box_beats_the_discovery_checkbox(tmp_path, book):
    """勾着「自动发现封面」也不行：显式的路径状态比开关更具体。"""
    _png(tmp_path)
    assert cover_from_form(_tab(tmp_path, discovery=True)) is None


def test_discovery_finds_the_cover_when_a_path_is_given(tmp_path, book):
    """框里有路径就用它，同目录那张 cover.png 不参与。"""
    _png(tmp_path)
    mine = tmp_path / "mine.png"
    mine.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 8)
    assert cover_from_form(_tab(tmp_path, cover=str(mine))).name == "mine.png"


def test_input_box_is_optional(tmp_path):
    """源文件框空着不影响：没有它就没有同目录可找，直接没有封面。"""
    assert cover_from_form(_tab(tmp_path, input_txt="")) is None


def test_discovery_is_off_means_no_cover(tmp_path, book):
    """关掉「自动发现封面」且框为空 → 没有封面。这是用户自己选的，不是 bug。"""
    _png(tmp_path)
    assert cover_from_form(_tab(tmp_path, discovery=False)) is None


def test_missing_cover_file_is_reported(tmp_path, book):
    """框里填了不存在的文件要报错，不能当成「没填」悄悄找一张。"""
    with pytest.raises(ValueError, match="封面图"):
        cover_from_form(_tab(tmp_path, cover=str(Path(tmp_path) / "nope.png")))