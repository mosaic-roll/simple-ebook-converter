import posixpath
import re
import zipfile

from sec.builder import build_css, build_epub
from sec.config import Config
from sec.parser import parse
from sec.encoding import read_lines


def _default_tree():
    return parse(["第一章 一", "正文一", "第二章 二", "正文二"], Config().levels, fallback_title="测试书")[0]


def _build(tmp_path, cfg=None, tree=None):
    cfg = cfg or Config(input=tmp_path / "novel.txt")
    tree = tree or _default_tree()
    out = tmp_path / "out.epub"
    build_epub(cfg, tree, build_css(cfg), out)
    return out


def _entries(path):
    with zipfile.ZipFile(path) as z:
        return {n: z.read(n) for n in z.namelist()}


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


def test_pages_link_stylesheet(tmp_path):
    out = _build(tmp_path)
    entries = _entries(out)
    page = next(n for n in entries if n.endswith("text/p0001.xhtml"))
    html = entries[page].decode("utf-8")
    assert 'href="../style.css"' in html


def test_all_css_links_resolve(tmp_path):
    out = _build(tmp_path)
    entries = _entries(out)
    for name in entries:
        if not name.endswith(".xhtml") or not name.startswith("text/"):
            continue
        html = entries[name].decode("utf-8")
        hrefs = re.findall(r'href="([^"]+\.css)"', html)
        for href in hrefs:
            target = posixpath.normpath(posixpath.join(posixpath.dirname(name), href))
            normalized = "EPUB/" + target if not target.startswith("EPUB/") else target
            assert normalized in entries, f"{name} 引用了不存在的 {target}"


def test_css_content_applies_settings(tmp_path):
    cfg = Config(
        input=tmp_path / "novel.txt",
        indent=0,
        line_height="2",
        para_spacing="0.5em",
        chapter_align="left",
        volume_align="left",
    )
    out = _build(tmp_path, cfg=cfg)
    entries = _entries(out)
    css = entries["EPUB/style.css"].decode("utf-8")
    assert "text-indent: 0em" in css
    assert "line-height: 2" in css
    assert "0.5em" in css
    assert ".chapter {\n  text-align: left;" in css
    assert ".volume {\n  text-align: left;" in css


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