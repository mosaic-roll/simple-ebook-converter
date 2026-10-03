"""把 `helpers.Epub` 接到真实 `build_epub` 产物上。

`test_conftest.py` 拿手拼 EPUB 验 helper 本身；这里验它对真的产物也成立——链接可达
与 media-type 自洽这两条断言，得在真实产出的目录结构与相对路径基准下才算数。
"""

import re

import pytest
from helpers import assert_heading

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
JPEG = b"\xff\xd8\xff" + b"\x00" * 32


@pytest.fixture
def simple(build_epub_file):
    return build_epub_file()


@pytest.fixture
def cover_path(tmp_path):
    def _make(data=PNG, name="cover.png"):
        path = tmp_path / name
        path.write_bytes(data)
        return path

    return _make


def sources_with_cover(cover):
    from simple_ebook_converter.core.sources import Sources, cover_resource

    return Sources(cover=cover_resource(cover))


# ---------- 真实产物上的两条契约 ----------


def test_links_reachable_on_a_real_book(simple):
    simple.assert_links_reachable()


def test_media_types_match_bytes_on_a_real_book(simple):
    simple.assert_manifest_media_types_match_bytes()


def test_mislabeled_cover_passes_the_byte_check(build_epub_file, cover_path):
    """源文件后缀骗人时，包内文件名与 media-type 都按实际字节改写（OPF-029 / PKG-022）。"""
    epub = build_epub_file(sources=sources_with_cover(cover_path(JPEG, "cover.png")))
    item = epub.manifest_item(prop="cover-image")
    assert item["media-type"] == "image/jpeg"
    assert item["href"].endswith(".jpg")
    epub.assert_manifest_media_types_match_bytes()
    epub.assert_links_reachable()


def test_honest_cover_keeps_its_extension(build_epub_file, cover_path):
    epub = build_epub_file(sources=sources_with_cover(cover_path(PNG, "cover.png")))
    item = epub.manifest_item(prop="cover-image")
    assert (item["media-type"], item["href"]) == ("image/png", "images/cover.png")


# ---------- 结构 ----------


def test_real_book_structure(simple):
    """封面 → nav → 正文，这是 spine 顺序的契约，不关心具体文件名。"""
    assert simple.spine_ids()[:2] == ["cover", "nav"]
    assert all(
        simple.has_entry(simple.itemref_target(idref)) for idref in simple.spine_ids()
    )


def test_stylesheet_is_linked_from_every_text_page(simple):
    assert simple.has_entry("EPUB/style.css")
    for page in simple.text_pages():
        assert "../style.css" in simple.html(page), page


def test_no_spine_item_is_non_linear(build_epub_file, cover_path):
    """图片封面页也得是 linear 的，否则 epubcheck 报 OPF-096（内容不可达）。"""
    for sources in (None, sources_with_cover(cover_path())):
        epub = build_epub_file(sources=sources)
        tags = re.findall(r"<itemref[^>]*>", epub.opf())
        assert tags
        for tag in tags:
            assert "linear=" not in tag, f"spine 里有非线性项：{tag}"


def test_deep_headings_are_linked_by_fragment(build_epub_file):
    """h4 并入祖先页，nav 用片段链接——链接必须真的落在那个 id 上。"""
    from simple_ebook_converter.core.config import default_levels
    from simple_ebook_converter.core.levels import build_levels
    from simple_ebook_converter.core.parser import parse

    tree = parse(
        ["第一章 开端", "※清晨", "正文甲", "※黄昏", "正文乙"],
        [*default_levels(), *build_levels(["h4.section:^※"])],
        fallback_title="测试书",
    )[0]
    epub = build_epub_file(tree=tree)
    assert len(epub.text_pages()) == 1, "h4 应该并入章的页，不单独建文件"
    assert_heading(epub.html(epub.text_pages()[0]), "h4", "※清晨",
                   class_name="section", has_id=True)
    assert re.search(r'href="[^"]*#', epub.nav()), "nav 里应该有片段链接"
    epub.assert_links_reachable()


def test_headings_carry_their_level_class(simple):
    html = simple.html(simple.text_pages()[0])
    assert_heading(html, "h3", "第一章 一", class_name="chapter")


def test_prelude_renders_as_chapter_heading(build_epub_file):
    """level 0 的前言按「章」渲染成 h3 + class=chapter（h1 通常留给书名）。"""
    epub = build_epub_file(lines=["前言内容", "第一章 一", "正文一"])
    holder = next(epub.html(n) for n in epub.text_pages() if n.endswith("preface.xhtml"))
    assert_heading(holder, "h3", "前言", class_name="chapter")
    assert "<p>前言内容</p>" in holder