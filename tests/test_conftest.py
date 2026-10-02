"""`helpers.py` 里那些 helper 自己的测试。

helper 是用来抓回归的，它自己坏了就等于回归没拦——所以每条契约断言都先拿一份
"确实坏掉"的产物验一遍：能报出预期信息，才说明它在真坏时也会报。
"""

import zipfile

import pytest

from helpers import Epub, assert_heading, parse_css, resolve_href

CONTAINER = (
    '<?xml version="1.0"?>\n'
    '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container" version="1.0">\n'
    "  <rootfiles><rootfile full-path=\"{opf}\""
    ' media-type="application/oebps-package+xml"/></rootfiles>\n'
    "</container>\n"
)
OPF_HEAD = (
    '<?xml version="1.0"?>\n'
    '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="id">\n'
    '  <metadata><dc:title xmlns:dc="http://purl.org/dc/elements/1.1/">t</dc:title>'
    '<meta property="dcterms:modified">2020-01-01T00:00:00Z</meta></metadata>\n'
    "  <manifest>\n"
)
OPF_TAIL = "  </manifest>\n  <spine>\n%s  </spine>\n</package>\n"
ITEM = '    <item href="{href}" id="{id}" media-type="{mt}"{extra}/>\n'
ITEMREF = '    <itemref idref="{idref}"/>\n'

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
JPEG = b"\xff\xd8\xff" + b"\x00" * 16
GIF = b"GIF89a" + b"\x00" * 16
OTF = b"OTTO" + b"\x00" * 16
WOFF = b"wOFF" + b"\x00" * 16
XHTML = "application/xhtml+xml"


def make_epub(tmp_path, items=(), refs=(), name="o.epub", opf="EPUB/content.opf"):
    """拼一本最小 EPUB。

    `items` 是 `(id, href, media-type, 内容)`；内容为 `None` 表示空文件。
    """
    manifest = "".join(
        ITEM.format(
            href=href,
            id=item_id,
            mt=media,
            extra=f' properties="{props}"' if props else "",
        )
        for item_id, href, media, _, props in items
    )
    with zipfile.ZipFile(tmp_path / name, "w") as z:
        z.writestr("mimetype", "application/epub+zip")
        z.writestr("META-INF/container.xml", CONTAINER.format(opf=opf))
        z.writestr(opf, OPF_HEAD + manifest + OPF_TAIL % "".join(
            ITEMREF.format(idref=r) for r in refs
        ))
        for _, href, _, content, _ in items:
            z.writestr(f"EPUB/{href}", b"" if content is None else content)
    return Epub(tmp_path / name)


def item(item_id, href, media=XHTML, content=None, props=""):
    return (item_id, href, media, content, props)


# ---------- resolve_href ----------


@pytest.mark.parametrize(
    ("base", "href", "expect"),
    [
        ("EPUB/nav.xhtml", "text/p0001.xhtml", "EPUB/text/p0001.xhtml"),
        ("EPUB/content.opf", "style.css", "EPUB/style.css"),
        ("EPUB/text/p0001.xhtml", "../style.css", "EPUB/style.css"),
        ("EPUB/text/p0001.xhtml", "p0002.xhtml#x", "EPUB/text/p0002.xhtml"),
        ("EPUB/content.opf", "images/cover.jpg", "EPUB/images/cover.jpg"),
        ("EPUB/text/p0001.xhtml", "../a/../style.css", "EPUB/style.css"),
    ],
)
def test_resolve_href_resolves_against_the_containing_file(base, href, expect):
    assert resolve_href(base, href) == expect


def test_resolve_href_decodes_percent_escapes():
    assert resolve_href("EPUB/nav.xhtml", "text/%E7%AC%AC1%E7%AB%A0.xhtml") == (
        "EPUB/text/第1章.xhtml"
    )


def test_container_full_path_is_package_root_relative_not_meta_inf_relative():
    """`full-path` 从包根算起——拿 container.xml 当基准会拼出 `META-INF/EPUB/...`。"""
    epub = make_epub(tmp_path := make_tmp(), items=[item("c", "text/p1.xhtml")])
    assert epub.opf_name() == "EPUB/content.opf"
    assert epub.entries["EPUB/content.opf"]
    assert resolve_href("META-INF/container.xml", "EPUB/content.opf") == (
        "META-INF/EPUB/content.opf"
    )  # 这就是不能走 resolve_href 的原因


def make_tmp():
    import tempfile
    from pathlib import Path

    return Path(tempfile.mkdtemp())


# ---------- assert_links_reachable ----------


def test_links_reachable_passes_on_a_consistent_book(tmp_path):
    epub = make_epub(
        tmp_path,
        items=[
            item("chapter_0", "text/p0001.xhtml",
                 content='<h4 id="p0002">※清晨</h4><link href="../style.css"/>'),
            item("css", "style.css", "text/css", b"body{}"),
            item("nav", "nav.xhtml", content='<a href="text/p0001.xhtml#p0002">目录</a>',
                 props="nav"),
        ],
        refs=["nav", "chapter_0"],
    )
    epub.assert_links_reachable()


def test_links_reachable_catches_a_dangling_page(tmp_path):
    epub = make_epub(
        tmp_path,
        items=[item("nav", "nav.xhtml", content='<a href="text/p0009.xhtml">目录</a>',
                    props="nav")],
        refs=["nav"],
    )
    with pytest.raises(AssertionError, match="指向不存在的条目"):
        epub.assert_links_reachable()


def test_links_reachable_catches_a_dangling_fragment(tmp_path):
    """nav 指的片段在目标页里没有 id——重命名 anchor 就会踩到。"""
    epub = make_epub(
        tmp_path,
        items=[
            item("chapter_0", "text/p0001.xhtml", content="<h4>清晨</h4>"),
            item("nav", "nav.xhtml",
                 content='<a href="text/p0001.xhtml#p0002">清晨</a>', props="nav"),
        ],
        refs=["nav", "chapter_0"],
    )
    with pytest.raises(AssertionError, match=r"#p0002 在 EPUB/text/p0001\.xhtml"):
        epub.assert_links_reachable()


def test_links_reachable_catches_a_missing_stylesheet(tmp_path):
    epub = make_epub(
        tmp_path,
        items=[item("chapter_0", "text/p0001.xhtml", content='<link href="../style.css"/>')],
        refs=["chapter_0"],
    )
    with pytest.raises(AssertionError, match="指向不存在的条目"):
        epub.assert_links_reachable()


def test_links_reachable_skips_external_and_same_page(tmp_path):
    epub = make_epub(
        tmp_path,
        items=[item("chapter_0", "text/p0001.xhtml",
                    content='<a href="https://example.com">站外</a><a href="#p0001">本页</a>')],
        refs=["chapter_0"],
    )
    epub.assert_links_reachable()


def test_links_reachable_reads_single_quoted_attributes(tmp_path):
    epub = make_epub(
        tmp_path,
        items=[item("chapter_0", "text/p0001.xhtml", content="<a href='p0002.xhtml'>相邻</a>")],
        refs=["chapter_0"],
    )
    with pytest.raises(AssertionError, match="指向不存在的条目"):
        epub.assert_links_reachable()  # 单引号不认的话这条就是假绿


def test_links_reachable_checks_manifest_hrefs_too(tmp_path):
    """manifest 的 href 也要核：包内文件被删了就是死链。"""
    epub = make_epub(tmp_path, items=[item("ghost", "text/gone.xhtml")], refs=[])
    del epub.entries["EPUB/text/gone.xhtml"]
    with pytest.raises(AssertionError, match="指向不存在的条目"):
        epub.assert_links_reachable()


# ---------- assert_manifest_media_types_match_bytes ----------


def test_manifest_media_types_accepts_truthful_declarations(tmp_path):
    epub = make_epub(
        tmp_path,
        items=[
            item("cover", "images/cover.png", "image/png", PNG),
            item("font", "fonts/f.otf", "font/otf", OTF),
            item("css", "style.css", "text/css", b"body{}"),
        ],
    )
    epub.assert_manifest_media_types_match_bytes()


@pytest.mark.parametrize(
    ("declared", "data", "actual"),
    [
        ("image/jpeg", PNG, "image/png"),
        ("image/png", JPEG, "image/jpeg"),
        ("image/png", GIF, "image/gif"),
        ("font/otf", WOFF, "font/woff"),
        ("image/png", OTF, "font/otf"),
    ],
)
def test_manifest_media_types_catches_a_lying_declaration(tmp_path, declared, data, actual):
    """扩展名和声明各自合法、互相撒谎——OPF-029 / PKG-022 就是这么报的。"""
    epub = make_epub(tmp_path, items=[item("x", "images/cover.png", declared, data)])
    with pytest.raises(AssertionError, match=f"声明 '{declared}'，实际字节是 '{actual}'"):
        epub.assert_manifest_media_types_match_bytes()


def test_manifest_media_types_fails_loudly_on_an_unknown_image(tmp_path):
    """声明成图片却认不出字节 = 有格式没实现，跳过就等于在这类回归前静默。"""
    epub = make_epub(tmp_path, items=[item("x", "images/c.xyz", "image/x-weird", b"?????")])
    with pytest.raises(AssertionError, match="字节头认不出格式"):
        epub.assert_manifest_media_types_match_bytes()


def test_manifest_media_types_ignores_non_binary_types(tmp_path):
    epub = make_epub(
        tmp_path,
        items=[
            item("css", "style.css", "text/css", b"body { color: red }"),
            item("c", "text/p1.xhtml", XHTML, b"<p>x</p>"),
            item("ncx", "toc.ncx", "application/x-dtbncx+xml", b"<ncx/>"),
        ],
    )
    epub.assert_manifest_media_types_match_bytes()


# ---------- parse_css ----------


def test_parse_css_reads_declarations_per_selector():
    assert parse_css("body {\n  text-align: justify;\n  margin: 5%;\n}")["body"] == {
        "text-align": "justify",
        "margin": "5%",
    }


def test_parse_css_splits_a_group_into_each_selector():
    rules = parse_css("h1, h2, h3 {\n  text-align: center;\n}")
    assert rules["h1"] == rules["h2"] == rules["h3"] == {"text-align": "center"}


def test_parse_css_drops_comments_before_reading_values():
    """`padding-left` 后面那条 `/* 装饰符号宽度 */` 不能粘进值里。"""
    assert parse_css("p {\n  padding-left: 1.5em;  /* 装饰符号宽度 */\n}")["p"][
        "padding-left"
    ] == "1.5em"


def test_parse_css_keeps_at_rules_as_keys():
    assert parse_css('@font-face {\n  src: url("fonts/f.otf");\n}')["@font-face"] == {
        "src": 'url("fonts/f.otf")'
    }


def test_parse_css_lets_a_later_rule_win():
    """同选择器出现两次时后者覆盖——外部样式追加到内置之后的路径靠这个。"""
    assert parse_css("body { color: red; }\nbody { color: blue; }")["body"]["color"] == "blue"


def test_parse_css_keeps_selectors_with_a_comment_on_the_same_line():
    assert parse_css("h2.volume { /* 卷标题 */\n  text-align: left;\n}")[
        "h2.volume"
    ] == {"text-align": "left"}


# ---------- assert_heading ----------

PAGE = (
    '<h3 class="chapter">第一章</h3>'
    '<h4 class="section" id="p0002">※清晨</h4>'
    '<h2 class="volume">第一卷</h2>'
)


def test_assert_heading_accepts_matching_tag_class_and_id():
    assert_heading(PAGE, "h4", "※清晨", class_name="section", has_id=True)


def test_assert_heading_accepts_a_heading_without_id():
    assert_heading(PAGE, "h2", "第一卷", class_name="volume")


@pytest.mark.parametrize(
    ("args", "expect"),
    [
        (("h5", "※清晨"), "页里没有"),
        (("h4", "※黄昏"), "页里没有"),
        (("h4", "※清晨", "chapter"), "class 不含 'chapter'"),
        (("h2", "第一卷", None, True), "缺 id"),
    ],
)
def test_assert_heading_failure_names_the_problem(args, expect):
    with pytest.raises(AssertionError, match=expect):
        assert_heading(PAGE, *args)


def test_assert_heading_failure_lists_what_was_actually_there():
    """失败信息要能看出页里实际有什么，而不是只说 False。"""
    with pytest.raises(AssertionError) as exc:
        assert_heading(PAGE, "h4", "※黄昏")
    message = str(exc.value)
    assert "section" in message and "※清晨" in message


def test_assert_heading_class_may_be_one_of_several():
    html = '<h4 class="section tail" id="p1">x</h4>'
    assert_heading(html, "h4", "x", class_name="section", has_id=True)
    with pytest.raises(AssertionError, match="class 不含"):
        assert_heading(html, "h4", "x", class_name="sec")


# ---------- Epub 的定位辅助 ----------


def test_opf_name_follows_container_instead_of_guessing(tmp_path):
    epub = make_epub(
        tmp_path,
        items=[item("c", "text/p1.xhtml")],
        opf="EPUB/pkg.opf",
        name="renamed.epub",
    )
    assert epub.opf_name() == "EPUB/pkg.opf"
    assert epub.manifest_items()[0]["href"] == "text/p1.xhtml"
    assert not epub.has_entry("EPUB/content.opf")


def test_spine_ids_and_itemref_target(tmp_path):
    epub = make_epub(
        tmp_path,
        items=[
            item("cover", "cover.xhtml"),
            item("nav", "nav.xhtml", props="nav"),
            item("chapter_0", "text/p0001.xhtml"),
        ],
        refs=["cover", "nav", "chapter_0"],
    )
    assert epub.spine_ids() == ["cover", "nav", "chapter_0"]
    assert epub.itemref_target("nav") == "EPUB/nav.xhtml"
    assert epub.itemref_target("chapter_0") == "EPUB/text/p0001.xhtml"


def test_itemref_target_rejects_an_idref_with_no_manifest_item(tmp_path):
    epub = make_epub(tmp_path, items=[item("nav", "nav.xhtml")], refs=["nav"])
    with pytest.raises(AssertionError, match="在 manifest 里没有对应 item"):
        epub.itemref_target("chapter_9")


def test_manifest_item_selects_by_property(tmp_path):
    epub = make_epub(
        tmp_path,
        items=[item("cover", "images/cover.png", "image/png", PNG, props="cover-image")],
    )
    assert epub.manifest_item(prop="cover-image")["href"] == "images/cover.png"


def test_manifest_item_complains_when_the_match_is_not_unique(tmp_path):
    epub = make_epub(
        tmp_path,
        items=[item("a", "images/a.png", "image/png", PNG, props="cover-image"),
               item("b", "images/b.png", "image/png", PNG, props="cover-image")],
    )
    with pytest.raises(AssertionError, match="期望恰好一条 manifest item"):
        epub.manifest_item(prop="cover-image")


def test_text_pages_lists_sorted(tmp_path):
    epub = make_epub(
        tmp_path,
        items=[item("b", "text/p0002.xhtml"), item("a", "text/p0001.xhtml")],
    )
    assert epub.text_pages() == ["EPUB/text/p0001.xhtml", "EPUB/text/p0002.xhtml"]


def test_nav_finds_the_item_marked_as_nav(tmp_path):
    epub = make_epub(
        tmp_path,
        items=[item("nav", "nav.xhtml", content="<nav/>", props="nav"),
               item("c", "text/p1.xhtml", content="<p/>")],
    )
    assert "<nav/>" in epub.nav()