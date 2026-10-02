import re

from helpers import Epub, assert_heading, parse_css

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


def _build(tmp_path, cfg=None, tree=None, sources=None, out="out.epub"):
    cfg = cfg or Config(input=tmp_path / "novel.txt")
    tree = tree or _default_tree()
    path = tmp_path / out
    build_epub(cfg, tree, sources, path)
    return Epub(path)


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


# ---------- CSS：配置是否生效 ----------


def test_build_css_defaults():
    rules = parse_css(build_css(Config()))
    assert rules["body"]["line-height"] == "1.5"
    assert rules["p"]["text-indent"] == "2em"
    assert "h3.chapter" in rules


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
    rules = parse_css(_build(tmp_path, cfg=cfg).html("EPUB/style.css"))
    assert rules["p"]["text-indent"] == "0em"
    assert rules["p"]["margin"] == "0 0 0.5em 0"
    assert rules["body"]["line-height"] == "2"
    assert rules["h3.chapter"]["text-align"] == "left"
    assert rules["h2.volume"]["text-align"] == "left"
    assert rules["body"]["text-align"] == "left"


def test_headings_centered_by_default():
    """h1~h6 默认居中：否则 `--level` 自定义的 h4/h5/h6 会跟着 `body_align` 跑。"""
    css = build_css(Config())
    assert parse_css(css)["h4"]["text-align"] == "center"
    # 顺序是层叠契约：`body` 与这条 `h1..h6` 特异性相同（都是 0,0,1），靠源码顺序决胜。
    # body 排到后面就会把 `--body-align` 套到所有标题上，h4/h5/h6 全废。
    assert css.index("h1, h2, h3, h4, h5, h6 {") > css.index("body {")


def test_cover_css_rules_present():
    """封面页靠 `.cover` 这组 class 上样式（图片封面与文字封面共用同一个容器）。"""
    rules = parse_css(build_css(Config()))
    assert "margin" in rules[".cover"]
    assert "max-height" in rules[".cover img"]
    assert rules[".cover .book-title"]["text-align"] == "center"


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
    css = build_css(
        Config(), Sources(css_append_text=".cover .book-title { color: red; }")
    )
    # 追加在后面是层叠契约：同特异性的规则靠后写的赢，追加到前面就压不住内置值。
    assert css.index("color: red;") > css.index("max-height: 100vh;")
    assert "text-indent" in css  # 内置正文样式还在
    assert parse_css(css)[".cover .book-title"]["color"] == "red"


def test_css_append_text_keeps_font_face(tmp_path):
    """追加不影响 `@font-face`（那是内置样式的一部分）。"""
    font = tmp_path / "f.ttf"
    font.write_bytes(b"\x00\x01\x00\x00")
    sources = Sources(font=font_resource(font), css_append_text="body { color: red; }")
    assert "@font-face" in parse_css(build_css(Config(), sources))


def test_empty_sources_uses_builtin():
    """空 `Sources()`：无外部 CSS、无字体，走内置模板。"""
    css = build_css(Config(), Sources())
    assert css == builtin_css(Config())
    assert "@font-face" not in css


# ---------- 包结构 ----------


def test_build_epub_structure(tmp_path):
    epub = _build(
        tmp_path,
        cfg=Config(input=tmp_path / "novel.txt", title="测试书", author="作者",
                   language="zh"),
        tree=_sample_tree(),
    )
    assert epub.entries["mimetype"] == b"application/epub+zip"
    assert epub.has_entry("META-INF/container.xml")
    assert epub.has_entry(epub.opf_name())
    assert epub.nav()
    assert epub.text_pages(), "应该有正文页"


def test_every_package_file_is_reachable_and_self_consistent(tmp_path):
    """链接都指得到、manifest 声明与字节一致——一次断掉整包。"""
    epub = _build(tmp_path, tree=_sample_tree())
    epub.assert_links_reachable()
    epub.assert_manifest_media_types_match_bytes()


def test_pages_link_stylesheet(tmp_path):
    """正文页与封面页都要链到 style.css，否则内置样式和外部 CSS 都无效。"""
    epub = _build(tmp_path, tree=_sample_tree())
    assert "../style.css" in epub.html(epub.text_pages()[0])
    assert "style.css" in epub.html("EPUB/cover.xhtml")


def test_spine_starts_with_cover_then_nav(tmp_path):
    """阅读器从 spine 第一个 linear 项开始，不该先落到目录页。"""
    epub = _build(tmp_path)
    assert epub.spine_ids()[:2] == ["cover", "nav"]
    assert all(epub.has_entry(epub.itemref_target(i)) for i in epub.spine_ids())


def test_author_empty_omits_creator(tmp_path):
    assert "<dc:creator" not in _build(tmp_path).opf()


def test_date_empty_omits_dc_date(tmp_path):
    assert "<dc:date" not in _build(tmp_path).opf()


def test_author_and_date_written(tmp_path):
    cfg = Config(input=tmp_path / "novel.txt", author="张三", date="2024-05-13")
    opf = _build(tmp_path, cfg=cfg).opf()
    assert '<dc:creator id="creator">张三</dc:creator>' in opf
    assert "<dc:date>2024-05-13</dc:date>" in opf


def test_no_toc_nav_not_in_spine(tmp_path):
    """`--no-toc-page` 时 nav 仍要写进 manifest（否则 OPF 报错），只是不进 spine。"""
    cfg = Config(input=tmp_path / "novel.txt", toc_in_spine=False)
    epub = _build(tmp_path, cfg=cfg)
    assert epub.nav()
    assert "nav" not in epub.spine_ids()
    assert 'properties="nav"' in epub.opf()
    assert epub.manifest_item(prop="nav")
    assert any(n.endswith(".ncx") for n in epub.entries)


def test_toc_nav_in_spine_by_default(tmp_path):
    assert "nav" in _build(tmp_path).spine_ids()


# ---------- 分页：只 h1~h3 单独成页 ----------


def test_deep_headings_share_the_ancestor_page(tmp_path):
    """h4 并入章的页，带 id 供片段链接，不再单独建文件。"""
    epub = _build(tmp_path, tree=_section_tree())
    assert len(epub.text_pages()) == 1, "h4 不该单独建文件"
    html = epub.html(epub.text_pages()[0])
    assert_heading(html, "h4", "※清晨", class_name="section", has_id=True)
    assert_heading(html, "h4", "※黄昏", class_name="section", has_id=True)
    assert "<p>正文甲</p>" in html and "<p>正文乙</p>" in html


def test_toc_links_deep_headings_by_fragment(tmp_path):
    """nav 用片段链接指到 h4；链接必须真的落在那个 id 上。"""
    epub = _build(tmp_path, tree=_section_tree())
    nav = epub.nav()
    assert re.search(r'href="[^"]+\.xhtml#', nav), f"nav 里应该有片段链接：\n{nav}"
    assert "清晨" in nav
    epub.assert_links_reachable()


def test_toc_depth_hides_deep_headings(tmp_path):
    """`--toc-depth 3` 时 h4 不进目录，片段链接也一并消失。"""
    cfg = Config(input=tmp_path / "novel.txt", toc_depth=3)
    nav = _build(tmp_path, cfg=cfg, tree=_section_tree()).nav()
    assert not re.search(r'href="[^"]+#', nav), f"toc_depth=3 不该有片段链接：\n{nav}"
    assert "清晨" not in nav


def test_deep_only_tree_still_gets_a_page(tmp_path):
    """只启用 h4 当层级时它没有成页的祖先，也得自己成页，正文才不至于无家可归。"""
    tree = parse(
        ["※清晨", "正文甲"], build_levels(["h4.section:^※"]), fallback_title="测试书"
    )[0]
    epub = _build(tmp_path, tree=tree)
    html = epub.html(epub.text_pages()[0])
    assert_heading(html, "h4", "※清晨", class_name="section")  # 根标题不带 id
    assert "<p>正文甲</p>" in html
    epub.assert_links_reachable()


# ---------- 封面页 ----------


def _cover_xhtml(tmp_path, cfg=None, sources=None):
    epub = _build(tmp_path, cfg=cfg, sources=sources)
    return epub.html("EPUB/cover.xhtml") if epub.has_entry("EPUB/cover.xhtml") else ""


def _cover_sources(tmp_path):
    """有封面图时的 `Sources`（图的内容，不是路径）。"""
    return Sources(cover=cover_resource(_png(tmp_path)))


def test_text_cover_page_is_default(tmp_path):
    """没有封面图时默认生成文字封面页，且页里有书名和作者。"""
    cfg = Config(input=tmp_path / "novel.txt", title="书名", author="作者")
    page = _cover_xhtml(tmp_path, cfg=cfg)
    assert 'epub:type="cover"' in page
    assert_heading(page, "h1", "书名", class_name="book-title")
    assert '<p class="book-author">作者</p>' in page
    assert "<img" not in page


def test_text_cover_page_is_linear(tmp_path):
    """文字封面是书的第一页，进正文流（linear 不是 no）。"""
    items = _build(
        tmp_path, cfg=Config(input=tmp_path / "novel.txt", title="书名")
    ).spine_items()
    assert ("cover", True) in items
    # 封面排在 nav 前面：阅读器从 spine 第一个 linear 项开始，不该先落到目录页
    assert [i for i, _ in items].index("cover") == 0
    assert [i for i, _ in items].index("nav") == 1


def test_text_cover_page_has_no_cover_image_property(tmp_path):
    """文字封面不是图片，不能带 cover-image / meta name=cover。"""
    epub = _build(tmp_path, cfg=Config(input=tmp_path / "novel.txt", title="书名"))
    assert "cover-image" not in epub.opf()
    assert 'name="cover"' not in epub.opf()
    assert not [n for n in epub.entries if n.startswith("EPUB/images/")]


def test_no_text_cover_has_no_cover_page(tmp_path):
    cfg = Config(input=tmp_path / "novel.txt", title="书名", text_cover=False)
    epub = _build(tmp_path, cfg=cfg)
    assert not epub.has_entry("EPUB/cover.xhtml")
    assert "cover" not in epub.spine_ids()


def test_text_cover_escapes_markup(tmp_path):
    cfg = Config(input=tmp_path / "novel.txt", title='<A & "B">', author="x&y")
    page = _cover_xhtml(tmp_path, cfg=cfg)
    assert "&lt;A &amp; &quot;B&quot;&gt;" in page or "&lt;A &amp;" in page
    assert "<A &" not in page
    assert "x&amp;y" in page


def test_text_cover_omits_author_when_empty(tmp_path):
    page = _cover_xhtml(
        tmp_path, cfg=Config(input=tmp_path / "novel.txt", title="书名")
    )
    assert "<p" not in page


def test_cover_page_links_stylesheet(tmp_path):
    """封面页必须链到 style.css，否则内置封面样式和外部 CSS 都对它无效。"""
    assert "style.css" in _cover_xhtml(
        tmp_path, cfg=Config(input=tmp_path / "novel.txt", title="书名")
    )
    assert "style.css" in _cover_xhtml(
        tmp_path,
        cfg=Config(input=tmp_path / "novel.txt"),
        sources=_cover_sources(tmp_path),
    )


def test_image_cover_declares_cover_meta(tmp_path):
    """有封面图时补 <meta name="cover">，兼容 EPUB2 时代的阅读器。"""
    opf = _build(tmp_path, sources=_cover_sources(tmp_path)).opf()
    assert 'properties="cover-image"' in opf
    assert '<meta name="cover" content="cover-img">' in opf


def test_image_cover_page_is_linear(tmp_path):
    """图片封面页也是打开书的第一页（曾是 linear=no，触发 OPF-096）。"""
    items = _build(tmp_path, sources=_cover_sources(tmp_path)).spine_items()
    assert ("cover", True) in items
    assert [i for i, _ in items].index("cover") == 0


def test_no_non_linear_spine_item_without_a_link_to_it(tmp_path):
    """OPF-096：非线性内容必须可达，所以现在全书不该有线性为 no 的 spine 项。"""
    for sources in (_cover_sources(tmp_path), Sources()):
        assert [i for i, linear in _build(tmp_path, sources=sources).spine_items()
                if not linear] == []


def test_opf_cover_media_type_matches_actual_bytes(tmp_path):
    """扩展名骗人时，OPF 的 media-type 和 href 都得跟着实际内容走（否则 OPF-029/PKG-022）。"""
    mislabeled = tmp_path / "cover.png"
    mislabeled.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 64)
    epub = _build(tmp_path, sources=Sources(cover=cover_resource(mislabeled)))
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
    page = _cover_xhtml(tmp_path, sources=Sources(cover=cover_resource(mislabeled)))
    assert 'src="images/cover.jpg"' in page
    assert 'src="images/cover.png"' not in page


def test_image_cover_alt_is_book_title(tmp_path):
    cfg = Config(input=tmp_path / "novel.txt", title="书名")
    page = _cover_xhtml(tmp_path, cfg=cfg, sources=_cover_sources(tmp_path))
    assert 'alt="书名"' in page


def test_image_cover_webp_media_type(tmp_path):
    """.webp 不在标准 mimetypes 里，manifest 的 media-type 不能写空。"""
    cover = tmp_path / "c.webp"
    cover.write_bytes(b"RIFF____WEBPVP8 fake")
    epub = _build(tmp_path, sources=Sources(cover=cover_resource(cover)))
    assert epub.manifest_item(prop="cover-image")["media-type"] == "image/webp"
    epub.assert_manifest_media_types_match_bytes()


def test_cover_avif_media_type(tmp_path):
    # 字节得是真正的 AVIF 形状：data[4:8]="ftyp"、data[8:12]="avif"。
    # 少写一个字节就 sniff 不出，会静默退回按扩展名 `.avif` 报类型——
    # 那样这条测试会因为错误的原因通过。
    cover = tmp_path / "c.avif"
    cover.write_bytes(b"\x00\x00\x00 ftypavif")
    epub = _build(tmp_path, sources=Sources(cover=cover_resource(cover)))
    assert epub.manifest_item(prop="cover-image")["media-type"] == "image/avif"
    epub.assert_manifest_media_types_match_bytes()


def test_image_cover_wins_over_text_cover(tmp_path):
    """给了封面图就不再生成文字封面，两者互斥。"""
    cfg = Config(input=tmp_path / "novel.txt", title="书名")
    page = _cover_xhtml(tmp_path, cfg=cfg, sources=_cover_sources(tmp_path))
    assert "<h1" not in page
    assert "<img" in page


def test_font_href_and_css_url_follow_the_renamed_file(tmp_path):
    """OTF 存成 .ttf 时，manifest 的 href、media-type 和 CSS 的 url() 得一起改。"""
    font = tmp_path / "f.ttf"
    font.write_bytes(b"OTTO" + b"\x00" * 64)
    epub = _build(tmp_path, sources=Sources(font=font_resource(font)))
    item = epub.manifest_item(suffix=".otf")
    assert item["media-type"] == "font/otf"
    assert not any(i["href"].endswith(".ttf") for i in epub.manifest_items())
    assert epub.has_entry("EPUB/" + item["href"])
    # CSS 的 url() 要跟着改名走，否则 @font-face 指不到包内文件
    assert f'src: url("{item["href"]}")' in epub.html("EPUB/style.css")
    epub.assert_manifest_media_types_match_bytes()
    epub.assert_links_reachable()


# ---------- 前言 / 兜底单章 ----------


def test_preface_built(tmp_path):
    cfg = Config(input=tmp_path / "novel.txt")
    tree, _ = parse(
        ["开篇语", "第1章 一", "正文"], cfg.levels, preface_title="前言", fallback_title="x"
    )
    epub = _build(tmp_path, cfg=cfg, tree=tree, out="preface.epub")
    assert epub.text_pages(), "前言应该单独成页"


def test_preface_and_fallback_use_h3(tmp_path):
    """前言/兜底单章（level 0）按章级渲染 h3；h1 留给书名（文字封面页）。"""
    cfg = Config(input=tmp_path / "novel.txt")
    tree, _ = parse(
        ["开篇语", "第1章 一", "正文"], cfg.levels, preface_title="前言", fallback_title="x"
    )
    page = _preface_page(_build(tmp_path, cfg=cfg, tree=tree, out="a.epub"))
    assert_heading(page, "h3", "前言", class_name="preface")
    assert "<h1" not in page

    # 整篇无标题：兜底单章同样 h3（class 是 chapter，因为没有前言标题行）
    fb_tree, _ = parse(["正文一", "正文二"], cfg.levels, fallback_title="书名")
    fb_page = _preface_page(_build(tmp_path, cfg=cfg, tree=fb_tree, out="b.epub"))
    assert_heading(fb_page, "h3", "书名", class_name="chapter")
    assert "<h1" not in fb_page


def _preface_page(epub):
    """前言/兜底单章那一页：正文页里带 preface class 的那个。"""
    for name in epub.text_pages():
        html = epub.html(name)
        if 'class="preface"' in html or name.endswith("preface.xhtml"):
            return html
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
