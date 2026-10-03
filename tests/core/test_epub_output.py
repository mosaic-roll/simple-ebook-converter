import re
from pathlib import Path

from helpers import Epub, assert_heading

from simple_ebook_converter.core.builder import (
    COVER_SECTION_TYPE,
    build_epub,
    image_cover_body,
    text_cover_body,
)
from simple_ebook_converter.core.config import DEFAULTS, Config, default_levels
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


def _build(cfg=None, tree=None, sources=None):
    cfg = cfg or Config()
    tree = tree or _default_tree()
    return Epub(build_epub(cfg, tree, sources))


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


# ---------- 写入 ebooklib ----------


def test_build_epub_lets_write_errors_surface(monkeypatch):
    """`ebooklib` 默认把 OSError 吞掉只 warn；不显式打开它，写盘失败就静默了。"""
    captured = {}

    def fake_write_epub(name, book, options=None):
        captured["options"] = options
        return True

    monkeypatch.setattr(
        "simple_ebook_converter.core.builder.epub.write_epub", fake_write_epub
    )
    build_epub(DEFAULTS, [], Sources())
    assert captured["options"]["raise_exceptions"] is True


def test_build_epub_returns_a_zip():
    assert build_epub(DEFAULTS, [], Sources())[:2] == b"PK"


# ---------- 包结构 ----------


def test_build_epub_structure():
    epub = _build(
        cfg=Config(input=Path("novel.txt"), title="测试书", author="作者",
                   language="zh"),
        tree=_sample_tree(),
    )
    assert epub.entries["mimetype"] == b"application/epub+zip"
    assert epub.has_entry("META-INF/container.xml")
    assert epub.has_entry(epub.opf_name())
    assert epub.nav()
    assert epub.text_pages(), "应该有正文页"


def test_every_package_file_is_reachable_and_self_consistent():
    """链接都指得到、manifest 声明与字节一致——一次断掉整包。"""
    epub = _build(tree=_sample_tree())
    epub.assert_links_reachable()
    epub.assert_manifest_media_types_match_bytes()


def test_pages_link_stylesheet():
    """正文页与封面页都要链到 style.css，否则内置样式和外部 CSS 都无效。"""
    epub = _build(tree=_sample_tree())
    assert "../style.css" in epub.html(epub.text_pages()[0])
    assert "style.css" in epub.html("EPUB/cover.xhtml")


def test_spine_starts_with_cover_then_nav():
    """阅读器从 spine 第一个 linear 项开始，不该先落到目录页。"""
    epub = _build()
    assert epub.spine_ids()[:2] == ["cover", "nav"]
    assert all(epub.has_entry(epub.itemref_target(i)) for i in epub.spine_ids())


def test_author_empty_omits_creator():
    assert "<dc:creator" not in _build().opf()


def test_date_empty_omits_dc_date():
    assert "<dc:date" not in _build().opf()


def test_author_and_date_written():
    cfg = Config(input=Path("novel.txt"), author="张三", date="2024-05-13")
    opf = _build(cfg=cfg).opf()
    assert '<dc:creator id="creator">张三</dc:creator>' in opf
    assert "<dc:date>2024-05-13</dc:date>" in opf


def test_no_toc_nav_not_in_spine():
    """`--no-toc-page` 时 nav 仍要写进 manifest（否则 OPF 报错），只是不进 spine。"""
    cfg = Config(input=Path("novel.txt"), toc_in_spine=False)
    epub = _build(cfg=cfg)
    assert epub.nav()
    assert "nav" not in epub.spine_ids()
    assert 'properties="nav"' in epub.opf()
    assert epub.manifest_item(prop="nav")
    assert any(n.endswith(".ncx") for n in epub.entries)


def test_toc_nav_in_spine_by_default():
    assert "nav" in _build().spine_ids()


# ---------- 分页：只 h1~h3 单独成页 ----------


def test_every_text_page_wraps_its_content_in_main_content():
    """卷页/章页/前言页一律套同一个壳，正文段落好按 `.main-content p` 定位。"""
    epub = _build()
    pages = epub.text_pages()
    assert pages
    for name in pages:
        html = epub.html(name)
        assert '<section class="main-content">' in html, name
        assert html.count("<section") == 1, f"{name} 里不该有别的 section"


def test_main_content_wraps_the_heading_too():
    """壳包整页含根标题，不只包段落。"""
    epub = _build()
    html = epub.html(epub.text_pages()[0])
    section = re.search(
        r'<section class="main-content">(.*)</section>', html, re.DOTALL
    ).group(1)
    assert_heading(section, "h3", "第一章 一", class_name="chapter")
    assert "<p>正文一</p>" in section


def test_cover_page_keeps_its_own_section():
    """封面页容器仍是 `.cover`，不被正文的壳波及。"""
    page = _cover_xhtml()
    assert '<section class="cover"' in page
    assert "main-content" not in page


def test_deep_headings_share_the_ancestor_page():
    """h4 并入章的页，带 id 供片段链接，不再单独建文件。"""
    epub = _build(tree=_section_tree())
    assert len(epub.text_pages()) == 1, "h4 不该单独建文件"
    html = epub.html(epub.text_pages()[0])
    assert_heading(html, "h4", "※清晨", class_name="section", has_id=True)
    assert_heading(html, "h4", "※黄昏", class_name="section", has_id=True)
    assert "<p>正文甲</p>" in html and "<p>正文乙</p>" in html


def test_toc_links_deep_headings_by_fragment():
    """nav 用片段链接指到 h4；链接必须真的落在那个 id 上。"""
    epub = _build(tree=_section_tree())
    nav = epub.nav()
    assert re.search(r'href="[^"]+\.xhtml#', nav), f"nav 里应该有片段链接：\n{nav}"
    assert "清晨" in nav
    epub.assert_links_reachable()


def test_toc_depth_hides_deep_headings():
    """`--toc-depth 3` 时 h4 不进目录，片段链接也一并消失。"""
    cfg = Config(input=Path("novel.txt"), toc_depth=3)
    nav = _build(cfg=cfg, tree=_section_tree()).nav()
    assert not re.search(r'href="[^"]+#', nav), f"toc_depth=3 不该有片段链接：\n{nav}"
    assert "清晨" not in nav


def test_deep_only_tree_still_gets_a_page():
    """只启用 h4 当层级时它没有成页的祖先，也得自己成页，正文才不至于无家可归。"""
    tree = parse(
        ["※清晨", "正文甲"], build_levels(["h4.section:^※"]), fallback_title="测试书"
    )[0]
    epub = _build(tree=tree)
    html = epub.html(epub.text_pages()[0])
    assert_heading(html, "h4", "※清晨", class_name="section")  # 根标题不带 id
    assert "<p>正文甲</p>" in html
    epub.assert_links_reachable()


# ---------- 封面页 ----------


def _cover_xhtml(cfg=None, sources=None):
    epub = _build(cfg=cfg, sources=sources)
    return epub.html("EPUB/cover.xhtml") if epub.has_entry("EPUB/cover.xhtml") else ""


def _cover_sources(tmp_path):
    """有封面图时的 `Sources`（图的内容，不是路径）。"""
    return Sources(cover=cover_resource(_png(tmp_path)))


def test_text_cover_page_is_default():
    """没有封面图时默认生成文字封面页，且页里有书名和作者。"""
    cfg = Config(input=Path("novel.txt"), title="书名", author="作者")
    page = _cover_xhtml(cfg=cfg)
    assert 'epub:type="cover"' in page
    assert_heading(page, "h1", "书名", class_name="book-title")
    assert '<p class="book-author">作者</p>' in page
    assert "<img" not in page


def test_text_cover_page_is_linear():
    """文字封面是书的第一页，进正文流（linear 不是 no）。"""
    items = _build(cfg=Config(input=Path("novel.txt"), title="书名")
    ).spine_items()
    assert ("cover", True) in items
    # 封面排在 nav 前面：阅读器从 spine 第一个 linear 项开始，不该先落到目录页
    assert [i for i, _ in items].index("cover") == 0
    assert [i for i, _ in items].index("nav") == 1


def test_text_cover_page_has_no_cover_image_property():
    """文字封面不是图片，不能带 cover-image / meta name=cover。"""
    epub = _build(cfg=Config(input=Path("novel.txt"), title="书名"))
    assert "cover-image" not in epub.opf()
    assert 'name="cover"' not in epub.opf()
    assert not [n for n in epub.entries if n.startswith("EPUB/images/")]


def test_no_text_cover_has_no_cover_page():
    cfg = Config(input=Path("novel.txt"), title="书名", text_cover=False)
    epub = _build(cfg=cfg)
    assert not epub.has_entry("EPUB/cover.xhtml")
    assert "cover" not in epub.spine_ids()


def test_text_cover_escapes_markup():
    cfg = Config(input=Path("novel.txt"), title='<A & "B">', author="x&y")
    page = _cover_xhtml(cfg=cfg)
    assert "&lt;A &amp; &quot;B&quot;&gt;" in page or "&lt;A &amp;" in page
    assert "<A &" not in page
    assert "x&amp;y" in page


def test_text_cover_omits_author_when_empty():
    page = _cover_xhtml(cfg=Config(input=Path("novel.txt"), title="书名")
    )
    assert "<p" not in page


def test_cover_page_links_stylesheet(tmp_path):
    """封面页必须链到 style.css，否则内置封面样式和外部 CSS 都对它无效。"""
    assert "style.css" in _cover_xhtml(cfg=Config(input=Path("novel.txt"), title="书名")
    )
    assert "style.css" in _cover_xhtml(
        cfg=Config(input=Path("novel.txt")),
        sources=_cover_sources(tmp_path),
    )


def test_image_cover_declares_cover_meta(tmp_path):
    """有封面图时补 <meta name="cover">，兼容 EPUB2 时代的阅读器。"""
    opf = _build(sources=_cover_sources(tmp_path)).opf()
    assert 'properties="cover-image"' in opf
    assert '<meta name="cover" content="cover-img">' in opf


def test_image_cover_page_is_linear(tmp_path):
    """图片封面页也是打开书的第一页（曾是 linear=no，触发 OPF-096）。"""
    items = _build(sources=_cover_sources(tmp_path)).spine_items()
    assert ("cover", True) in items
    assert [i for i, _ in items].index("cover") == 0


def test_no_non_linear_spine_item_without_a_link_to_it(tmp_path):
    """OPF-096：非线性内容必须可达，所以现在全书不该有线性为 no 的 spine 项。"""
    for sources in (_cover_sources(tmp_path), Sources()):
        assert [i for i, linear in _build(sources=sources).spine_items()
                if not linear] == []


def test_opf_cover_media_type_matches_actual_bytes(tmp_path):
    """扩展名骗人时，OPF 的 media-type 和 href 都得跟着实际内容走（否则 OPF-029/PKG-022）。"""
    mislabeled = tmp_path / "cover.png"
    mislabeled.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 64)
    epub = _build(sources=Sources(cover=cover_resource(mislabeled)))
    item = epub.manifest_item(prop="cover-image")
    assert item["media-type"] == "image/jpeg"
    assert item["href"].endswith(".jpg")
    assert not item["href"].endswith(".png")
    assert epub.has_entry("EPUB/" + item["href"])
    epub.assert_manifest_media_types_match_bytes()


def test_cover_page_image_src_follows_the_renamed_file(tmp_path):
    """封面页里的 <img src> 得和包内实际文件名一致，否则图裂。"""
    mislabeled = tmp_path / "cover.png"
    mislabeled.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 64)
    page = _cover_xhtml(sources=Sources(cover=cover_resource(mislabeled)))
    assert 'src="images/cover.jpg"' in page
    assert 'src="images/cover.png"' not in page


def test_image_cover_alt_is_book_title(tmp_path):
    cfg = Config(input=Path("novel.txt"), title="书名")
    page = _cover_xhtml(cfg=cfg, sources=_cover_sources(tmp_path))
    assert 'alt="书名"' in page


def test_image_cover_webp_media_type(tmp_path):
    """.webp 不在标准 mimetypes 里，manifest 的 media-type 不能写空。"""
    cover = tmp_path / "c.webp"
    cover.write_bytes(b"RIFF____WEBPVP8 fake")
    epub = _build(sources=Sources(cover=cover_resource(cover)))
    assert epub.manifest_item(prop="cover-image")["media-type"] == "image/webp"
    epub.assert_manifest_media_types_match_bytes()


def test_cover_avif_media_type(tmp_path):
    # 字节得是真正的 AVIF 形状：data[4:8]="ftyp"、data[8:12]="avif"。
    # 少写一个字节就 sniff 不出，会静默退回按扩展名 `.avif` 报类型——
    # 那样这条测试会因为错误的原因通过。
    cover = tmp_path / "c.avif"
    cover.write_bytes(b"\x00\x00\x00 ftypavif")
    epub = _build(sources=Sources(cover=cover_resource(cover)))
    assert epub.manifest_item(prop="cover-image")["media-type"] == "image/avif"
    epub.assert_manifest_media_types_match_bytes()


def test_image_cover_wins_over_text_cover(tmp_path):
    """给了封面图就不再生成文字封面，两者互斥。"""
    cfg = Config(input=Path("novel.txt"), title="书名")
    page = _cover_xhtml(cfg=cfg, sources=_cover_sources(tmp_path))
    assert "<h1" not in page
    assert "<img" in page


def test_font_href_and_css_url_follow_the_renamed_file(tmp_path):
    """OTF 存成 .ttf 时，manifest 的 href、media-type 和 CSS 的 url() 得一起改。"""
    font = tmp_path / "f.ttf"
    font.write_bytes(b"OTTO" + b"\x00" * 64)
    epub = _build(sources=Sources(font=font_resource(font)))
    item = epub.manifest_item(suffix=".otf")
    assert item["media-type"] == "font/otf"
    assert not any(i["href"].endswith(".ttf") for i in epub.manifest_items())
    assert epub.has_entry("EPUB/" + item["href"])
    # CSS 的 url() 要跟着改名走，否则 @font-face 指不到包内文件
    assert f'src: url("{item["href"]}")' in epub.html("EPUB/style.css")
    epub.assert_manifest_media_types_match_bytes()
    epub.assert_links_reachable()


# ---------- 前言 / 兜底单章 ----------


def test_preface_built():
    cfg = Config(input=Path("novel.txt"))
    tree, _ = parse(
        ["开篇语", "第1章 一", "正文"], cfg.levels, preface_title="前言", fallback_title="x"
    )
    epub = _build(cfg=cfg, tree=tree)
    assert epub.text_pages(), "前言应该单独成页"


def test_preface_and_fallback_use_h3():
    """前言/兜底单章（level 0）按章级渲染 h3；h1 留给书名（文字封面页）。"""
    cfg = Config(input=Path("novel.txt"))
    tree, _ = parse(
        ["开篇语", "第1章 一", "正文"], cfg.levels, preface_title="前言", fallback_title="x"
    )
    page = _preface_page(_build(cfg=cfg, tree=tree))
    assert_heading(page, "h3", "前言", class_name="chapter")

    # 整篇无标题：兜底单章同样 h3
    fb_tree, _ = parse(["正文一", "正文二"], cfg.levels, fallback_title="书名")
    fb_page = _preface_page(_build(cfg=cfg, tree=fb_tree))
    assert_heading(fb_page, "h3", "书名", class_name="chapter")


def _preface_page(epub):
    """前言/兜底单章那一页：level 0 的 anchor 固定是 `preface`。"""
    for name in epub.text_pages():
        if name.endswith("preface.xhtml"):
            return epub.html(name)
    raise AssertionError(f"没有找到前言页；正文页：{epub.text_pages()}")


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
