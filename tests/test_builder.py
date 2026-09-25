import zipfile

from sec.builder import build_css, build_epub
from sec.config import Config
from sec.parser import parse
from sec.encoding import read_lines


def _sample_tree():
    lines = [
        "前言内容",
        "第一卷 起源",
        "第一章 开端",
        "这是第一段。<b>特殊字符 &</b>",
        "第二章 发展",
        "第二段内容",
    ]
    return parse(lines, Config().levels, fallback_title="测试书")[0]


def test_build_css_defaults():
    css = build_css(Config())
    assert "line-height: 1.5" in css
    assert "text-indent: 2em" in css
    assert ".chapter {" in css


def test_build_epub_structure(tmp_path):
    cfg = Config(input=tmp_path / "novel.txt", title="测试书", author="作者", language="zh")
    tree, _ = parse(
        ["前言内容", "第1章 一", "第一段文字", "第2章 二", "第二段文字"],
        cfg.levels,
        fallback_title="测试书",
    )
    out = tmp_path / "out.epub"
    build_epub(cfg, tree, build_css(cfg), out)

    with zipfile.ZipFile(out) as z:
        names = z.namelist()
        assert "mimetype" in names
        assert z.read("mimetype").startswith(b"application/epub+zip")
        assert "META-INF/container.xml" in names
        assert any(n.endswith("content.opf") for n in names)
        assert any("nav.xhtml" in n for n in names)
        assert any(n.endswith("text/p0001.xhtml") for n in names)


def test_preface_built(tmp_path):
    cfg = Config(input=tmp_path / "novel.txt")
    tree, _ = parse(["开篇语", "第1章 一", "正文"], cfg.levels, preface_title="前言", fallback_title="x")
    out = tmp_path / "out.epub"
    build_epub(cfg, tree, build_css(cfg), out)
    with zipfile.ZipFile(out) as z:
        names = z.namelist()
    assert any("preface.xhtml" in n for n in names)


def test_cover_packaged(tmp_path):
    cover = tmp_path / "c.png"
    cover.write_bytes(b"\x89PNG\r\n\x1a\nfake")
    cfg = Config(input=tmp_path / "novel.txt", cover=cover)
    tree, _ = parse(["第1章 一", "正文"], cfg.levels, fallback_title="x")
    out = tmp_path / "out.epub"
    build_epub(cfg, tree, build_css(cfg), out)
    with zipfile.ZipFile(out) as z:
        names = z.namelist()
    assert any("cover-image" in n for n in names) or any(n.endswith("c.png") for n in names)
    assert any("cover.xhtml" in n for n in names)