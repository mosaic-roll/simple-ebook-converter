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
    """`Config.validate()` 只管得到 CLI 那侧，GUI 恒为 None，所以互斥靠这里兜住。"""
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


def test_cover_resource_rejects_unknown_extension(tmp_path):
    bad = tmp_path / "c.xyz"
    bad.write_bytes(b"\x00")
    with pytest.raises(ValueError, match="封面图"):
        cover_resource(bad)


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
    explicit = _png(tmp_path, "mine.jpg")
    assert cover_for(explicit, _cfg(tmp_path).input).name == "mine.jpg"


def test_cover_for_returns_none_when_no_explicit(tmp_path):
    """不传显式路径时一律返回 None——自动发现由打开文件时填路径负责，不在这里。"""
    _png(tmp_path)
    assert cover_for(None, _cfg(tmp_path).input) is None


def test_cover_for_returns_none_without_input():
    assert cover_for(None, None) is None


def test_cover_for_treats_blank_as_absent(tmp_path):
    """GUI 传的是输入框内容，空串 = 用户没填 = 返回 None（不自动发现）。"""
    _png(tmp_path)
    assert cover_for("", _cfg(tmp_path).input) is None


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
    # `css_file` 与 `css_append` 互斥由 `Config.validate()` 管，这里单独给
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


def test_load_sources_no_cover_without_explicit(tmp_path):
    """CLI 侧同样不自动发现：cover_for 只认显式路径。"""
    _png(tmp_path)
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
