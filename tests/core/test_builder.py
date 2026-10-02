import posixpath
import re
import zipfile

from simple_ebook_converter.core.builder import (
    COVER_SECTION_TYPE,
    build_css,
    build_epub,
    builtin_css,
    image_cover_body,
    text_cover_body,
)
from simple_ebook_converter.core.config import Config, default_levels
from simple_ebook_converter.core.levels import build_levels
from simple_ebook_converter.core.parser import parse
from simple_ebook_converter.core.sources import Sources, cover_resource, font_resource


def _default_tree():
    return parse(
        ["第一章 一", "正文一", "第二章 二", "正文二"],
        Config().levels,
        fallback_title="测试书",
    )[0]


def _section_tree():
    """章(h3) 下带两个节(h4)：节应该并入章的页，而不是各建一个文件。"""
    lines = ["第一章 开端", "※清晨", "正文甲", "※黄昏", "正文乙"]
    return parse(lines, _with_defaults("h4.section:^※"), fallback_title="测试书")[0]


def _with_defaults(*extra: str):
    """内置卷/章 + 额外层级规格，顺序同前端 `_level_specs()`。"""
    return [*default_levels(), *build_levels(list(extra))]


def _build(tmp_path, cfg=None, tree=None, sources=None):
    cfg = cfg or Config(input=tmp_path / "novel.txt")
    tree = tree or _default_tree()
    out = tmp_path / "out.epub"
    build_epub(cfg, tree, sources, out)
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


def _rule(css: str, selector: str) -> str:
    """CSS 里某个选择器的声明块（出现多次就拼起来）。

    不按整块文本断言，否则加一条声明就误报。`/* */` 注释会粘在上一条的值后面，先剥掉。
    """
    blocks = [
        body
        for sel, body in re.findall(r"([^{}]+)\{([^}]*)\}", css)
        if selector in [s.strip() for s in sel.split(",")]
    ]
    assert blocks, f"CSS 里没有 {selector} 规则：\n{css}"
    return re.sub(r"/\*.*?\*/", "", "\n".join(blocks), flags=re.S)


def _declarations(css: str, selector: str) -> dict[str, str]:
    """`_rule()` 的结果 → `{'text-align': 'left', ...}`。"""
    out = {}
    for decl in _rule(css, selector).split(";"):
        if ":" in decl:
            prop, _, value = decl.partition(":")
            out[prop.strip()] = value.strip()
    return out


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
        body_align="left",
    )
    out = _build(tmp_path, cfg=cfg)
    entries = _entries(out)
    css = entries["EPUB/style.css"].decode("utf-8")
    assert "text-indent: 0em" in css
    assert "line-height: 2" in css
    assert "0.5em" in css
    assert _declarations(css, ".chapter")["text-align"] == "left"
    assert _declarations(css, ".volume")["text-align"] == "left"
    assert _declarations(css, "body")["text-align"] == "left"


def test_headings_centered_by_default():
    """h1~h6 默认居中：否则 `--level` 自定义的 h4/h5/h6 会跟着 `body_align` 跑。"""
    css = build_css(Config())
    assert _declarations(css, "h4")["text-align"] == "center"
    # 居中规则要排在 `body` 之后：两者特异性相同，靠源码顺序决胜
    assert css.index("h1, h2, h3, h4, h5, h6 {") > css.index("body {")


def test_build_epub_structure(tmp_path):
    cfg = Config(
        input=tmp_path / "novel.txt", title="测试书", author="作者", language="zh"
    )
    tree, _ = parse(
        ["前言内容", "第1章 一", "第一段文字", "第2章 二", "第二段文字"],
        cfg.levels,
        fallback_title="测试书",
    )
    out = tmp_path / "out.epub"
    build_epub(cfg, tree, Sources(), out)

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
    tree, _ = parse(
        ["开篇语", "第1章 一", "正文"],
        cfg.levels,
        preface_title="前言",
        fallback_title="x",
    )
    out = tmp_path / "out.epub"
    build_epub(cfg, tree, Sources(), out)
    with zipfile.ZipFile(out) as z:
        names = z.namelist()
    assert any("preface.xhtml" in n for n in names)


def test_preface_and_fallback_use_h3(tmp_path):
    """前言/兜底单章（level 0）按章级渲染 h3；h1 留给书名（文字封面页）。"""
    cfg = Config(input=tmp_path / "novel.txt")
    tree, _ = parse(
        ["开篇语", "第1章 一", "正文"],
        cfg.levels,
        preface_title="前言",
        fallback_title="x",
    )
    out = tmp_path / "out.epub"
    build_epub(cfg, tree, Sources(), out)
    with zipfile.ZipFile(out) as z:
        page = z.read("EPUB/text/preface.xhtml").decode("utf-8")
    assert '<h3 class="preface">前言</h3>' in page
    assert "<h1" not in page

    # 整篇无标题：兜底单章同样 h3（anchor 也是 preface）
    fb_tree, _ = parse(["正文一", "正文二"], cfg.levels, fallback_title="书名")
    fb_out = tmp_path / "fb.epub"
    build_epub(cfg, fb_tree, Sources(), fb_out)
    with zipfile.ZipFile(fb_out) as z:
        fb_page = z.read("EPUB/text/preface.xhtml").decode("utf-8")
    assert '<h3 class="chapter">书名</h3>' in fb_page
    assert "<h1" not in fb_page


def test_cover_packaged(tmp_path):
    cover = tmp_path / "c.png"
    cover.write_bytes(b"\x89PNG\r\n\x1a\nfake")
    cfg = Config(input=tmp_path / "novel.txt")
    tree, _ = parse(["第1章 一", "正文"], cfg.levels, fallback_title="x")
    out = tmp_path / "out.epub"
    build_epub(cfg, tree, Sources(cover=cover_resource(cover)), out)
    with zipfile.ZipFile(out) as z:
        names = z.namelist()
    assert any("cover-image" in n for n in names) or any(
        n.endswith("c.png") for n in names
    )
    assert any("cover.xhtml" in n for n in names)


def test_cover_avif_media_type(tmp_path):
    cover = tmp_path / "c.avif"
    cover.write_bytes(b"\x00\x00\x00 ftypfavif")
    cfg = Config(input=tmp_path / "novel.txt")
    tree, _ = parse(["第1章 一", "正文"], cfg.levels, fallback_title="x")
    out = tmp_path / "out.epub"
    build_epub(cfg, tree, Sources(cover=cover_resource(cover)), out)
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
    assert '<dc:creator id="creator">张三</dc:creator>' in opf
    assert "<dc:date>2024-05-13</dc:date>" in opf


def test_no_toc_nav_not_in_spine(tmp_path):
    cfg = Config(input=tmp_path / "novel.txt", toc_in_spine=False)
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
    assert '"nav"' in spine or 'nav"' in spine


# ---------- 分页：只 h1~h3 单独成页 ----------


def test_deep_headings_share_the_ancestor_page(tmp_path):
    """h4 并入章的页，带 id 供片段链接，不再单独建文件。"""
    entries = _entries(_build(tmp_path, tree=_section_tree()))
    pages = sorted(n for n in entries if n.startswith("EPUB/text/"))
    assert pages == ["EPUB/text/p0001.xhtml"]
    html = entries["EPUB/text/p0001.xhtml"].decode("utf-8")
    assert '<h4 class="section" id="p0002">※清晨</h4>' in html
    assert '<h4 class="section" id="p0003">※黄昏</h4>' in html
    assert "<p>正文甲</p>" in html and "<p>正文乙</p>" in html


def test_toc_links_deep_headings_by_fragment(tmp_path):
    entries = _entries(_build(tmp_path, tree=_section_tree()))
    nav = entries["EPUB/nav.xhtml"].decode("utf-8")
    assert 'href="text/p0001.xhtml#p0002"' in nav
    assert "清晨" in nav


def test_toc_depth_hides_deep_headings(tmp_path):
    cfg = Config(input=tmp_path / "novel.txt", toc_depth=3)
    entries = _entries(_build(tmp_path, cfg=cfg, tree=_section_tree()))
    nav = entries["EPUB/nav.xhtml"].decode("utf-8")
    assert "#p0002" not in nav


def test_deep_only_tree_still_gets_a_page(tmp_path):
    """只启用 h4 当层级时它没有成页的祖先，也得自己成页，正文才不至于无家可归。"""
    tree = parse(
        ["※清晨", "正文甲"], build_levels(["h4.section:^※"]), fallback_title="测试书"
    )[0]
    entries = _entries(_build(tmp_path, tree=tree))
    html = entries["EPUB/text/p0001.xhtml"].decode("utf-8")
    assert '<h4 class="section">※清晨</h4>' in html  # 根标题不带 id
    assert "<p>正文甲</p>" in html


# ---------- 封面页 ----------

COVER_XHTML = "EPUB/cover.xhtml"


def _cover_xhtml(tmp_path, cfg=None, sources=None):
    entries = _entries(_build(tmp_path, cfg=cfg, sources=sources))
    return entries[COVER_XHTML].decode("utf-8") if COVER_XHTML in entries else ""


def _spine_of(tmp_path, cfg=None, sources=None):
    entries = _entries(_build(tmp_path, cfg=cfg, sources=sources))
    opf = entries[next(n for n in entries if n.endswith("content.opf"))].decode("utf-8")
    return opf.split("<spine", 1)[1].split("</spine>", 1)[0]


def _spine_items(tmp_path, cfg=None, sources=None):
    """spine 里的 itemref 解析成 [(idref, linear)]，linear 默认 yes。"""
    spine = _spine_of(tmp_path, cfg=cfg, sources=sources)
    out = []
    for tag in re.findall(r"<itemref\b[^>]*/>", spine):
        idref = re.search(r'idref="([^"]+)"', tag)
        out.append((idref.group(1) if idref else None, 'linear="no"' not in tag))
    return out


def _cover_sources(tmp_path):
    """有封面图时的 `Sources`（图的内容，不是路径）。"""
    return Sources(cover=cover_resource(_png(tmp_path)))


def test_text_cover_page_is_default(tmp_path):
    """没有封面图时默认生成文字封面页，且页里有书名和作者。"""
    cfg = Config(input=tmp_path / "novel.txt", title="书名", author="作者")
    page = _cover_xhtml(tmp_path, cfg=cfg)
    assert 'epub:type="cover"' in page
    assert '<h1 class="book-title">书名</h1>' in page
    assert '<p class="book-author">作者</p>' in page
    assert "<img" not in page


def test_text_cover_page_is_linear(tmp_path):
    """文字封面是书的第一页，进正文流（linear 不是 no）。"""
    cfg = Config(input=tmp_path / "novel.txt", title="书名")
    items = _spine_items(tmp_path, cfg=cfg)
    assert ("cover", True) in items
    # 封面排在 nav 前面：阅读器从 spine 第一个 linear 项开始，不该先落到目录页
    assert [i for i, _ in items].index("cover") == 0
    assert [i for i, _ in items].index("nav") == 1


def test_text_cover_page_has_no_cover_image_property(tmp_path):
    """文字封面不是图片，不能带 cover-image / meta name=cover。"""
    entries = _entries(
        _build(tmp_path, cfg=Config(input=tmp_path / "novel.txt", title="书名"))
    )
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
    assert "<p" not in page


def test_cover_page_links_stylesheet(tmp_path):
    """封面页必须链到 style.css，否则内置封面样式和外部 CSS 都对它无效。"""
    assert 'href="style.css"' in _cover_xhtml(
        tmp_path, cfg=Config(input=tmp_path / "novel.txt", title="书名")
    )
    assert 'href="style.css"' in _cover_xhtml(
        tmp_path,
        cfg=Config(input=tmp_path / "novel.txt"),
        sources=_cover_sources(tmp_path),
    )


def test_image_cover_declares_cover_meta(tmp_path):
    """有封面图时补 <meta name="cover">，兼容 EPUB2 时代的阅读器。"""
    entries = _entries(_build(tmp_path, sources=_cover_sources(tmp_path)))
    opf = entries[next(n for n in entries if n.endswith("content.opf"))].decode("utf-8")
    assert 'properties="cover-image"' in opf
    assert '<meta name="cover" content="cover-img">' in opf


def test_image_cover_page_is_not_linear(tmp_path):
    """图片封面页 linear=no，不打断正文流。"""
    items = _spine_items(tmp_path, sources=_cover_sources(tmp_path))
    assert ("cover", False) in items


def test_image_cover_alt_is_book_title(tmp_path):
    cfg = Config(input=tmp_path / "novel.txt", title="书名")
    page = _cover_xhtml(tmp_path, cfg=cfg, sources=_cover_sources(tmp_path))
    assert 'alt="书名"' in page


def test_image_cover_webp_media_type(tmp_path):
    """.webp 不在标准 mimetypes 里，manifest 的 media-type 不能写空。"""
    cover = tmp_path / "c.webp"
    cover.write_bytes(b"RIFF____WEBPVP8 fake")
    entries = _entries(_build(tmp_path, sources=Sources(cover=cover_resource(cover))))
    opf = entries[next(n for n in entries if n.endswith("content.opf"))].decode("utf-8")
    assert 'media-type="image/webp"' in opf


def test_image_cover_wins_over_text_cover(tmp_path):
    """给了封面图就不再生成文字封面，两者互斥。"""
    cfg = Config(input=tmp_path / "novel.txt", title="书名")
    page = _cover_xhtml(tmp_path, cfg=cfg, sources=_cover_sources(tmp_path))
    assert "<h1" not in page
    assert "<img" in page


def test_cover_css_rules_present():
    """封面页仍靠 `.cover` 这组 class 上样式（图片封面与文字封面共用同一个容器）。"""
    css = build_css(Config())
    assert ".cover {" in css
    assert ".cover img" in css


# ---------- CSS：整份替代 / 追加（内容由 Sources 送来） ----------


def test_css_text_replaces_builtin():
    """`Sources.css_text` 是完整样式表，替代内置（不是追加）。"""
    css = build_css(Config(), Sources(css_text="body { color: red; }"))
    assert css == "body { color: red; }"
    assert "text-indent" not in css  # 内置正文样式没有混进来
    assert ".cover" not in css  # 内置封面样式也没了


def test_builtin_css_is_unaffected_by_css_text():
    """`--dump-css` 要的是内置模板，外部 CSS 不该拿它当模板。"""
    cfg = Config(indent=0)
    assert builtin_css(cfg) == build_css(cfg, Sources())


def test_css_append_text_adds_to_builtin():
    """`Sources.css_append_text` 加在内置样式之后，所以能覆盖内置规则。"""
    css = build_css(Config(), Sources(css_append_text=".cover .book-title { color: red; }"))
    assert css.index("color: red;") > css.index("max-height: 100vh;")  # 追加在内置之后
    assert "text-indent" in css  # 内置正文样式还在


def test_css_append_text_keeps_font_face(tmp_path):
    """追加不影响 `@font-face`（那是内置样式的一部分）。"""
    font = tmp_path / "f.ttf"
    font.write_bytes(b"\x00\x01\x00\x00")
    sources = Sources(font=font_resource(font), css_append_text="body { color: red; }")
    assert "@font-face" in build_css(Config(), sources)


def test_empty_sources_uses_builtin():
    """空 `Sources()`：无外部 CSS、无字体，走内置模板。"""
    css = build_css(Config(), Sources())
    assert css == builtin_css(Config())
    assert "@font-face" not in css


# ---------- 封面页的 body 片段 ----------


def test_cover_section_type_is_epub_standard():
    """用标准语义角色，不自造 class。"""
    assert COVER_SECTION_TYPE == "cover"


def test_image_body_uses_standard_cover_section():
    """封面用标准语义角色 + 显式 class="cover"，不自造 class。"""
    body = image_cover_body("images/cover.png", alt="书名")
    assert body.startswith('<section class="cover" epub:type="cover">')
    assert '<img src="images/cover.png" alt="书名"/>' in body
    assert body.rstrip().endswith("</section>")
    assert 'class="cover"' in body


def test_image_body_escapes_src_and_alt():
    body = image_cover_body('a"b.png', alt="<x & y>")
    assert "&quot;" in body
    assert "&lt;x &amp; y&gt;" in body
    assert "<x & y>" not in body


def test_text_body_title_and_author():
    body = text_cover_body("书名", "作者")
    assert '<section class="cover" epub:type="cover">' in body
    assert '<h1 class="book-title">书名</h1>' in body
    assert '<p class="book-author">作者</p>' in body
    assert "<img" not in body
    assert 'class="cover"' in body


def test_text_body_omits_missing_parts():
    assert "<p" not in text_cover_body("书名")
    assert "<h1" not in text_cover_body("", "作者")


def test_text_body_empty_still_valid_section():
    assert (
        text_cover_body("", "")
        == '<section class="cover" epub:type="cover">\n</section>'
    )


def test_text_body_escapes_markup():
    body = text_cover_body("<b>书名</b>", "a & b")
    assert "&lt;b&gt;书名&lt;/b&gt;" in body
    assert "a &amp; b" in body
    assert "<b>" not in body


def _png(tmp_path):
    cover = tmp_path / "c.png"
    cover.write_bytes(b"\x89PNG\r\n\x1a\nfake")
    return cover
