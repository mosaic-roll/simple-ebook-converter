from pathlib import Path

import pytest

from sec.core.config import Config
from sec.core.mediatypes import (
    COVER_TYPES,
    FONT_TYPES,
    cover_media_type,
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
