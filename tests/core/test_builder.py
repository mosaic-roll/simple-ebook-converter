import posixpath
import re
import zipfile

from simple_ebook_converter.core.builder import build_css, build_epub
from simple_ebook_converter.core.config import Config
from simple_ebook_converter.core.parser import parse


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


def test_cover_avif_media_type(tmp_path):
    cover = tmp_path / "c.avif"
    cover.write_bytes(b"\x00\x00\x00 ftypfavif")
    cfg = Config(input=tmp_path / "novel.txt", cover=cover)
    tree, _ = parse(["第1章 一", "正文"], cfg.levels, fallback_title="x")
    out = tmp_path / "out.epub"
    build_epub(cfg, tree, build_css(cfg), out)
    with zipfile.ZipFile(out) as z:
        opf = next(n for n in z.namelist() if n.endswith("content.opf"))
        text = z.read(opf).decode("utf-8")
    assert 'media-type="image/avif"' in text


def _opf(tmp_path):
    entries = _entries(_build(tmp_path))
    opf = next(n for n in entries if n.endswith("content.opf"))
    return entries[opf].decode("utf-8")


def test_author_empty_omits_creator(tmp_path):
    opf = _opf(tmp_path)
    assert "<dc:creator" not in opf


def test_date_empty_omits_dc_date(tmp_path):
    opf = _opf(tmp_path)
    assert "<dc:date" not in opf


def test_author_and_date_written(tmp_path):
    cfg = Config(input=tmp_path / "novel.txt", author="张三", date="2024-05-13")
    out = _build(tmp_path, cfg=cfg)
    entries = _entries(out)
    opf = entries[next(n for n in entries if n.endswith("content.opf"))].decode("utf-8")
    assert "<dc:creator id=\"creator\">张三</dc:creator>" in opf
    assert "<dc:date>2024-05-13</dc:date>" in opf


def test_no_toc_nav_not_in_spine(tmp_path):
    cfg = Config(input=tmp_path / "novel.txt", no_toc=True)
    out = _build(tmp_path, cfg=cfg)
    entries = _entries(out)
    assert "EPUB/nav.xhtml" in entries
    opf = entries[next(n for n in entries if n.endswith("content.opf"))].decode("utf-8")
    spine = opf.split("<spine", 1)[1].split("</spine>", 1)[0]
    assert "nav" not in spine
    assert 'properties="nav"' in opf
    ncx = entries[next(n for n in entries if "toc.ncx" in n)].decode("utf-8")
    assert "第1章" in ncx or "一" in ncx


def test_toc_nav_in_spine_by_default(tmp_path):
    out = _build(tmp_path)
    entries = _entries(out)
    assert "EPUB/nav.xhtml" in entries
    opf = entries[next(n for n in entries if n.endswith("content.opf"))].decode("utf-8")
    spine = opf.split("<spine", 1)[1].split("</spine>", 1)[0]
    assert '"nav"' in spine or "nav\"" in spine


# ---------- 封面页 ----------

COVER_XHTML = "EPUB/cover.xhtml"


def _cover_xhtml(tmp_path, cfg=None):
    entries = _entries(_build(tmp_path, cfg=cfg))
    return entries[COVER_XHTML].decode("utf-8") if COVER_XHTML in entries else ""


def _spine_of(tmp_path, cfg=None):
    entries = _entries(_build(tmp_path, cfg=cfg))
    opf = entries[next(n for n in entries if n.endswith("content.opf"))].decode("utf-8")
    return opf.split("<spine", 1)[1].split("</spine>", 1)[0]


def _spine_items(tmp_path, cfg=None):
    """spine 里的 itemref 解析成 [(idref, linear)]，linear 默认 yes。"""
    spine = _spine_of(tmp_path, cfg=cfg)
    out = []
    for tag in re.findall(r"<itemref\b[^>]*/>", spine):
        idref = re.search(r'idref="([^"]+)"', tag)
        out.append((idref.group(1) if idref else None, 'linear="no"' not in tag))
    return out


def test_text_cover_page_is_default(tmp_path):
    """没有封面图时默认生成文字封面页，且页里有书名和作者。"""
    cfg = Config(input=tmp_path / "novel.txt", title="书名", author="作者")
    page = _cover_xhtml(tmp_path, cfg=cfg)
    assert 'epub:type="cover"' in page
    assert "<h1>书名</h1>" in page
    assert "<p>作者</p>" in page
    assert "<img" not in page


def test_text_cover_page_is_linear(tmp_path):
    """文字封面是书的第一页，进正文流（linear 不是 no）。"""
    cfg = Config(input=tmp_path / "novel.txt", title="书名")
    items = _spine_items(tmp_path, cfg=cfg)
    assert ("cover", True) in items
    # nav 之后立刻就是封面页，也就是正文的第一页
    assert [i for i, _ in items].index("cover") == 1


def test_text_cover_page_has_no_cover_image_property(tmp_path):
    """文字封面不是图片，不能带 cover-image / meta name=cover。"""
    entries = _entries(_build(tmp_path, cfg=Config(input=tmp_path / "novel.txt", title="书名")))
    opf = entries[next(n for n in entries if n.endswith("content.opf"))].decode("utf-8")
    assert "cover-image" not in opf
    assert 'name="cover"' not in opf
    assert not [n for n in entries if n.startswith("EPUB/images/")]


def test_no_text_cover_has_no_cover_page(tmp_path):
    cfg = Config(input=tmp_path / "novel.txt", title="书名", text_cover=False)
    entries = _entries(_build(tmp_path, cfg=cfg))
    assert COVER_XHTML not in entries
    assert "cover" not in _spine_of(tmp_path, cfg=cfg)


def test_text_cover_escapes_markup(tmp_path):
    cfg = Config(input=tmp_path / "novel.txt", title='<A & "B">', author="x&y")
    page = _cover_xhtml(tmp_path, cfg=cfg)
    assert "&lt;A &amp; &quot;B&quot;&gt;" in page or "&lt;A &amp;" in page
    assert "<A &" not in page
    assert "x&amp;y" in page


def test_text_cover_omits_author_when_empty(tmp_path):
    page = _cover_xhtml(tmp_path, cfg=Config(input=tmp_path / "novel.txt", title="书名"))
    assert "<p>" not in page


def test_cover_page_links_stylesheet(tmp_path):
    """封面页必须链到 style.css，否则内置封面样式和 --css-file 都对它无效。"""
    for cfg in (
        Config(input=tmp_path / "novel.txt", title="书名"),
        Config(input=tmp_path / "novel.txt", cover=_png(tmp_path)),
    ):
        assert 'href="style.css"' in _cover_xhtml(tmp_path, cfg=cfg)


def test_image_cover_declares_cover_meta(tmp_path):
    """有封面图时补 <meta name="cover">，兼容 EPUB2 时代的阅读器。"""
    cfg = Config(input=tmp_path / "novel.txt", cover=_png(tmp_path))
    entries = _entries(_build(tmp_path, cfg=cfg))
    opf = entries[next(n for n in entries if n.endswith("content.opf"))].decode("utf-8")
    assert 'properties="cover-image"' in opf
    assert '<meta name="cover" content="cover-img">' in opf


def test_image_cover_page_is_not_linear(tmp_path):
    """图片封面页 linear=no，不打断正文流。"""
    cfg = Config(input=tmp_path / "novel.txt", cover=_png(tmp_path))
    assert ("cover", False) in _spine_items(tmp_path, cfg=cfg)


def test_image_cover_alt_is_book_title(tmp_path):
    cfg = Config(input=tmp_path / "novel.txt", title="书名", cover=_png(tmp_path))
    assert 'alt="书名"' in _cover_xhtml(tmp_path, cfg=cfg)


def test_image_cover_webp_media_type(tmp_path):
    """.webp 不在标准 mimetypes 里，manifest 的 media-type 不能写空。"""
    cover = tmp_path / "c.webp"
    cover.write_bytes(b"RIFF____WEBPVP8 fake")
    cfg = Config(input=tmp_path / "novel.txt", cover=cover)
    entries = _entries(_build(tmp_path, cfg=cfg))
    opf = entries[next(n for n in entries if n.endswith("content.opf"))].decode("utf-8")
    assert 'media-type="image/webp"' in opf


def test_image_cover_wins_over_text_cover(tmp_path):
    """给了封面图就不再生成文字封面，两者互斥。"""
    cfg = Config(input=tmp_path / "novel.txt", title="书名", cover=_png(tmp_path))
    page = _cover_xhtml(tmp_path, cfg=cfg)
    assert "<h1>" not in page
    assert "<img" in page


def test_cover_css_rules_present():
    css = build_css(Config())
    assert "body > section" in css
    assert "body > section img" in css
    assert "body > section p" in css


def test_cover_css_comes_before_user_css(tmp_path):
    """--css-file 追加在最后，用户才可能覆盖内置封面样式。"""
    extra = tmp_path / "extra.css"
    extra.write_text("body > section h1 { color: red; }", encoding="utf-8")
    cfg = Config(input=tmp_path / "novel.txt", css_file=extra)
    css = build_css(cfg)
    assert css.index("body > section h1 {") > css.index("body > section {")


def _png(tmp_path):
    cover = tmp_path / "c.png"
    cover.write_bytes(b"\x89PNG\r\n\x1a\nfake")
    return cover
