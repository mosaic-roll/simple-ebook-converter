from pathlib import Path

import pytest

from simple_ebook_converter.core.config import Config
from simple_ebook_converter.core.mediatypes import (
    COVER_TYPES,
    FONT_TYPES,
    cover_media_type,
    find_cover,
    font_media_type,
)


def test_font_media_type():
    assert font_media_type(Path("a.ttf")) == "font/ttf"
    assert font_media_type(Path("A.OTF")) == "font/otf"
    assert font_media_type(Path("b.woff2")) == "font/woff2"


def test_font_media_type_rejects_unknown_suffix():
    with pytest.raises(ValueError, match="font.ttc"):
        font_media_type(Path("font.ttc"))


def test_cover_media_type():
    assert cover_media_type(Path("c.JPG")) == "image/jpeg"
    assert cover_media_type(Path("c.png")) == "image/png"
    assert cover_media_type(Path("c.avif")) == "image/avif"


def test_cover_media_type_rejects_unknown_suffix():
    """过去这里是 `.get(suffix, "image/jpeg")`，未知后缀会被悄悄当 jpeg 塞进 EPUB。"""
    with pytest.raises(ValueError, match="cover.txt"):
        cover_media_type(Path("cover.txt"))


def test_error_message_lists_supported_formats():
    with pytest.raises(ValueError, match="ttf/otf/woff/woff2"):
        font_media_type(Path("x.ttc"))


def test_validate_rejects_unsupported_font():
    with pytest.raises(ValueError, match="不支持的字体格式"):
        Config(font="font.ttc").validate()


def test_validate_rejects_unsupported_cover():
    with pytest.raises(ValueError, match="不支持的封面图格式"):
        Config(cover="cover.txt").validate()


def test_validate_accepts_supported_assets():
    Config(font="f.ttf", cover="c.png").validate()


def test_tables_are_consistent():
    """两个表都不该是空的，且 jpg/jpeg 指向同一类型。"""
    assert FONT_TYPES and COVER_TYPES
    assert COVER_TYPES[".jpg"] == COVER_TYPES[".jpeg"] == "image/jpeg"


# ---------- 封面自动发现 ----------


def _touch(path):
    path.write_bytes(b"\x00")
    return path


def test_find_cover_finds_the_only_one(tmp_path):
    cover = _touch(tmp_path / "cover.png")
    assert find_cover(tmp_path / "novel.txt") == cover


@pytest.mark.parametrize("name", ["cover.jpg", "cover.JPEG", "Cover.webp", "COVER.avif"])
def test_find_cover_accepts_every_supported_format(tmp_path, name):
    cover = _touch(tmp_path / name)
    assert find_cover(tmp_path / "novel.txt") == cover


def test_find_cover_ignores_unsupported_extension(tmp_path):
    _touch(tmp_path / "cover.txt")
    assert find_cover(tmp_path / "novel.txt") is None


def test_find_cover_ignores_other_names(tmp_path):
    _touch(tmp_path / "cover.png.bak")
    _touch(tmp_path / "mycover.png")
    _touch(tmp_path / "cover2.png")
    assert find_cover(tmp_path / "novel.txt") is None


def test_find_cover_needs_exactly_one(tmp_path):
    """两个候选说明作者没拿准，静默挑一张反而会咬人，所以不采用。"""
    _touch(tmp_path / "cover.png")
    _touch(tmp_path / "cover.jpg")
    assert find_cover(tmp_path / "novel.txt") is None


def test_find_cover_ignores_directories(tmp_path):
    (tmp_path / "cover.png").mkdir()
    assert find_cover(tmp_path / "novel.txt") is None


def test_find_cover_only_looks_beside_the_input(tmp_path):
    """别的目录里的 cover.* 不算数。"""
    other = tmp_path / "other"
    other.mkdir()
    _touch(other / "cover.png")
    assert find_cover(tmp_path / "novel.txt") is None


def test_find_cover_on_missing_directory(tmp_path):
    assert find_cover(tmp_path / "nope" / "novel.txt") is None


def test_find_cover_with_no_input_file_present(tmp_path):
    """输入文件本身不必存在，只要父目录能列出来就行。"""
    cover = _touch(tmp_path / "cover.png")
    assert find_cover(tmp_path / "not-created-yet.txt") == cover
