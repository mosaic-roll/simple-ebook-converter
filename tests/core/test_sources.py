import json

import pytest

from simple_ebook_converter.core.config import Config
from simple_ebook_converter.core.sources import (
    Sources,
    cover_for,
    cover_resource,
    font_resource,
    load_sources,
    read_text,
)


def _cfg(tmp_path, **kw):
    novel = tmp_path / "novel.txt"
    novel.write_text("第一章 一\n正文\n", encoding="utf-8")
    return Config(input=novel, **kw)


def _png(tmp_path, name="cover.png"):
    path = tmp_path / name
    path.write_bytes(b"\x89PNG\r\n\x1a\nfake")
    return path


def _jpeg_named_png(tmp_path, name="cover.png"):
    """扩展名是 .png，内容其实是 JPEG——epubcheck 会报 OPF-029 + PKG-022。"""
    path = tmp_path / name
    path.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 64)
    return path


def _jpeg(tmp_path, name="cover.jpg"):
    path = tmp_path / name
    path.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 64)
    return path


def _ttf(tmp_path, name="f.ttf"):
    path = tmp_path / name
    path.write_bytes(b"\x00\x01\x00\x00")
    return path


# ---------- Sources 的不变量 ----------


def test_empty_sources_fields_are_none():
    s = Sources()
    assert s.toc_entries is None
    assert s.css_text is None
    assert s.css_append_text is None
    assert s.font is None
    assert s.cover is None


def test_css_replacement_and_append_are_mutually_exclusive():
    """`validate_config()` 只管得到 CLI 那侧，GUI 恒为 None，所以互斥靠这里兜住。"""
    with pytest.raises(ValueError, match="互斥"):
        Sources(css_text="a{}", css_append_text="b{}")


def test_one_css_field_alone_is_fine():
    assert Sources(css_text="a{}").css_append_text is None
    assert Sources(css_append_text="b{}").css_text is None


# ---------- 资源构造函数 ----------


def test_font_resource_reads_name_and_bytes(tmp_path):
    font = _ttf(tmp_path)
    res = font_resource(font)
    assert res.name == "f.ttf"
    assert res.data == b"\x00\x01\x00\x00"
    assert res.media_type == "font/ttf"


def test_cover_resource_reads_name_and_bytes(tmp_path):
    cover = _png(tmp_path)
    res = cover_resource(cover)
    assert res.name == "cover.png"
    assert res.data.startswith(b"\x89PNG")
    assert res.media_type == "image/png"


def test_resource_name_is_basename_only(tmp_path):
    """`Resource.name` 不含目录：写进 manifest 的路径由调用方拼。"""
    nested = tmp_path / "sub"
    nested.mkdir()
    font = nested / "f.ttf"
    font.write_bytes(b"\x00\x01\x00\x00")
    assert font_resource(font).name == "f.ttf"


def test_font_resource_rejects_unknown_extension(tmp_path):
    bad = tmp_path / "f.xyz"
    bad.write_bytes(b"\x00")
    with pytest.raises(ValueError, match="字体"):
        font_resource(bad)


def test_font_resource_corrects_mislabelled_font(tmp_path):
    """OTF 存成 .ttf 时按内容来：名字和 media-type 一起改。"""
    path = tmp_path / "f.ttf"
    path.write_bytes(b"OTTO" + b"\x00" * 64)
    res = font_resource(path)
    assert res.name == "f.otf"
    assert res.media_type == "font/otf"


def test_font_resource_corrects_woff2_named_ttf(tmp_path):
    path = tmp_path / "f.ttf"
    path.write_bytes(b"wOF2" + b"\x00" * 64)
    res = font_resource(path)
    assert res.name == "f.woff2"
    assert res.media_type == "font/woff2"


def test_font_resource_keeps_name_when_type_agrees(tmp_path):
    res = font_resource(_ttf(tmp_path))
    assert res.name == "f.ttf"
    assert res.media_type == "font/ttf"


def test_font_resource_falls_back_to_extension_when_bytes_unknown(tmp_path):
    """认不出字节就别硬猜，不能因此把原本能转的文件判死。"""
    path = tmp_path / "f.ttf"
    path.write_bytes(b"not a font at all")
    res = font_resource(path)
    assert res.name == "f.ttf"
    assert res.media_type == "font/ttf"


def test_font_resource_does_not_touch_the_source_file(tmp_path):
    path = tmp_path / "f.ttf"
    path.write_bytes(b"OTTO" + b"\x00" * 64)
    font_resource(path)
    assert path.exists() and path.name == "f.ttf"


def test_cover_resource_rejects_unknown_extension(tmp_path):
    bad = tmp_path / "c.xyz"
    bad.write_bytes(b"\x00")
    with pytest.raises(ValueError, match="封面图"):
        cover_resource(bad)


def test_cover_resource_corrects_mislabelled_image(tmp_path):
    """扩展名和内容不符时按内容来：名字和 media-type 一起改，OPF 里才自洽。"""
    res = cover_resource(_jpeg_named_png(tmp_path))
    assert res.name == "cover.jpg"
    assert res.media_type == "image/jpeg"
    assert res.data.startswith(b"\xff\xd8\xff")


def test_cover_resource_corrects_reverse_direction(tmp_path):
    """反过来也一样：PNG 存成 .jpg 要改回 .png。"""
    path = tmp_path / "cover.jpg"
    path.write_bytes(b"\x89PNG\r\n\x1a\nfake")
    res = cover_resource(path)
    assert res.name == "cover.png"
    assert res.media_type == "image/png"


def test_cover_resource_keeps_name_when_type_agrees(tmp_path):
    """`.jpeg` 和 `.jpg` 都对，不必改名。"""
    path = tmp_path / "cover.jpeg"
    path.write_bytes(b"\xff\xd8\xff\xe0")
    res = cover_resource(path)
    assert res.name == "cover.jpeg"
    assert res.media_type == "image/jpeg"


def test_cover_resource_keeps_multi_suffix_stem(tmp_path):
    path = tmp_path / "my.book.png"
    path.write_bytes(b"\xff\xd8\xff\xe0")
    assert cover_resource(path).name == "my.book.jpg"


def test_cover_resource_falls_back_to_extension_when_bytes_unknown(tmp_path):
    """认不出字节就别硬猜，退回扩展名——不能因此把原本能转的文件判死。"""
    path = tmp_path / "cover.png"
    path.write_bytes(b"not an image at all")
    res = cover_resource(path)
    assert res.name == "cover.png"
    assert res.media_type == "image/png"


def test_cover_resource_does_not_touch_the_source_file(tmp_path):
    """改名只改 EPUB 里叫什么，用户磁盘上的文件不动。"""
    path = _jpeg_named_png(tmp_path)
    cover_resource(path)
    assert path.exists() and path.name == "cover.png"


def test_bad_extension_is_reported_before_a_missing_file(tmp_path):
    """扩展名先验：文件压根不存在时，也该说"格式不对"而不是"读不出"。"""
    with pytest.raises(ValueError, match="字体"):
        font_resource(tmp_path / "f.xyz")
    with pytest.raises(ValueError, match="封面图"):
        cover_resource(tmp_path / "c.xyz")


def test_resource_reports_unreadable_file(tmp_path):
    with pytest.raises(ValueError, match="无法读取字体"):
        font_resource(tmp_path / "nope.ttf")
    with pytest.raises(ValueError, match="无法读取封面图"):
        cover_resource(tmp_path / "nope.png")


def test_read_text_reports_unreadable_file(tmp_path):
    with pytest.raises(ValueError, match="无法读取外部 CSS"):
        read_text(tmp_path / "nope.css", "外部 CSS")


# ---------- cover_for：显式路径优先，无显式路径一律返回 None ----------


def test_cover_for_prefers_explicit(tmp_path):
    _png(tmp_path)
    explicit = _jpeg(tmp_path, "mine.jpg")
    assert cover_for(explicit, _cfg(tmp_path).input).name == "mine.jpg"


def test_cover_for_returns_none_when_no_explicit(tmp_path):
    """没给封面（`None`）且没关发现时，去同目录找唯一的 `cover.*`。"""
    _png(tmp_path)
    assert cover_for(None, _cfg(tmp_path).input).name == "cover.png"


def test_cover_for_returns_none_without_input():
    assert cover_for(None, None) is None


def test_cover_for_treats_blank_as_absent(tmp_path):
    """空串是**显式说不要封面**，与「没给」（None）不是一回事。

    GUI 传的就是输入框内容：用户把框清空了，就是不要封面，不能再去同目录翻一张
    cover.png 替他做主。
    """
    _png(tmp_path)
    assert cover_for("", _cfg(tmp_path).input) is None


def test_cover_for_blank_beats_discovery(tmp_path):
    """空串连 `discovery=True` 也压得住——它比开关更具体。"""
    _png(tmp_path)
    assert cover_for("", _cfg(tmp_path).input, discovery=True) is None


def test_cover_for_explicit_beats_discovery(tmp_path):
    """给了路径就用给的，同目录有没有 cover.* 都一样。"""
    _png(tmp_path)
    explicit = _jpeg(tmp_path, "mine.jpg")
    assert cover_for(explicit, _cfg(tmp_path).input).name == "mine.jpg"
    assert cover_for(explicit, _cfg(tmp_path).input, discovery=False).name == "mine.jpg"


def test_cover_for_needs_explicit_path(tmp_path):
    """多张候选图也不会乱挑——没有显式路径就不封。"""
    _png(tmp_path, "cover.png")
    _png(tmp_path, "cover.jpg")
    assert cover_for(None, _cfg(tmp_path).input) is None


# ---------- load_sources：CLI 侧的入口 ----------


def test_load_sources_reads_every_path(tmp_path):
    toc = tmp_path / "toc.json"
    toc.write_text(json.dumps([{"raw_title": "一", "level": 3, "line": 1}]), "utf-8")
    css = tmp_path / "extra.css"
    css.write_text("body{}", encoding="utf-8")
    append = tmp_path / "append.css"
    append.write_text("p{}", encoding="utf-8")
    cfg = _cfg(
        tmp_path,
        toc_file=toc,
        css_file=css,
        font=_ttf(tmp_path),
        cover=_png(tmp_path, "mine.png"),
    )
    sources = load_sources(cfg)
    assert sources.toc_entries == [{"raw_title": "一", "level": 3, "line": 1}]
    assert sources.css_text == "body{}"
    assert sources.font is not None and sources.font.name == "f.ttf"
    assert sources.cover is not None and sources.cover.name == "mine.png"
    # `css_file` 与 `css_append` 互斥由 `validate_config()` 管，这里单独给
    assert load_sources(Config(input=cfg.input, css_append=append)).css_append_text == (
        "p{}"
    )


def test_load_sources_empty_config_gives_empty_sources(tmp_path):
    sources = load_sources(_cfg(tmp_path))
    assert sources.toc_entries is None
    assert sources.css_text is None
    assert sources.css_append_text is None
    assert sources.font is None
    assert sources.cover is None


def test_load_sources_discovers_the_cover_by_default(tmp_path):
    """CLI 默认也会去同目录找封面——不给 `--cover` 就该有封面，不是让用户多打一遍。"""
    _png(tmp_path)
    assert load_sources(_cfg(tmp_path)).cover.name == "cover.png"


def test_load_sources_no_cover_discovery_off(tmp_path):
    """`--no-cover-discovery` 时不翻目录，直接走文字封面。"""
    _png(tmp_path)
    assert load_sources(_cfg(tmp_path, cover_discovery=False)).cover is None


def test_load_sources_explicit_cover_wins_over_discovery(tmp_path):
    _png(tmp_path)
    cfg = _cfg(tmp_path, cover=_jpeg(tmp_path, "mine.jpg"))
    assert load_sources(cfg).cover.name == "mine.jpg"


def test_load_sources_ambiguous_cover_is_not_discovered(tmp_path):
    """同目录两张 cover.*（png + jpg）时 `find_cover()` 返回 None——挑一个是在替用户猜。"""
    _png(tmp_path)
    _jpeg(tmp_path)
    assert load_sources(_cfg(tmp_path)).cover is None


def test_load_sources_reports_unreadable_css(tmp_path):
    cfg = _cfg(tmp_path, css_file=tmp_path / "nope.css")
    with pytest.raises(ValueError, match="无法读取外部 CSS"):
        load_sources(cfg)


def test_load_sources_reports_unreadable_toc_file(tmp_path):
    cfg = _cfg(tmp_path, toc_file=tmp_path / "nope.json")
    with pytest.raises(ValueError, match="无法读取目录树文件"):
        load_sources(cfg)


def test_load_sources_reports_broken_toc_json(tmp_path):
    toc = tmp_path / "toc.json"
    toc.write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError, match="目录树不是合法 JSON"):
        load_sources(_cfg(tmp_path, toc_file=toc))
