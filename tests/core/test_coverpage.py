from simple_ebook_converter.core.coverpage import COVER_SECTION_TYPE, image_cover_body, text_cover_body


def test_cover_section_type_is_epub_standard():
    """用标准语义角色，不自造 class。"""
    assert COVER_SECTION_TYPE == "cover"


def test_image_body_uses_standard_cover_section():
    body = image_cover_body("images/cover.png", alt="书名")
    assert body.startswith('<section epub:type="cover">')
    assert '<img src="images/cover.png" alt="书名"/>' in body
    assert body.rstrip().endswith("</section>")
    assert "class=" not in body


def test_image_body_escapes_src_and_alt():
    body = image_cover_body('a"b.png', alt='<x & y>')
    assert "&quot;" in body
    assert "&lt;x &amp; y&gt;" in body
    assert "<x & y>" not in body


def test_text_body_title_and_author():
    body = text_cover_body("书名", "作者")
    assert '<section epub:type="cover">' in body
    assert "<h1>书名</h1>" in body
    assert "<p>作者</p>" in body
    assert "<img" not in body
    assert "class=" not in body


def test_text_body_omits_missing_parts():
    assert "<p>" not in text_cover_body("书名")
    assert "<h1>" not in text_cover_body("", "作者")


def test_text_body_empty_still_valid_section():
    body = text_cover_body("", "")
    assert body == '<section epub:type="cover">\n</section>'


def test_text_body_escapes_markup():
    body = text_cover_body("<b>书名</b>", "a & b")
    assert "&lt;b&gt;书名&lt;/b&gt;" in body
    assert "a &amp; b" in body
    assert "<b>" not in body
