"""`build_css` / `builtin_css` 的语义：配置项是否落到该落的选择器上。

纯函数，不建 EPUB。CSS 一旦生成就是字符串，断言选择器 → 声明比断言源码文本稳：
加声明、加注释、重排不会误报，但选择器写错、值没接上会挂。
"""

from helpers import parse_css

from simple_ebook_converter.core.builder import build_css, builtin_css
from simple_ebook_converter.core.config import Config
from simple_ebook_converter.core.sources import Resource, Sources


def test_build_css_defaults():
    rules = parse_css(build_css(Config()))
    assert rules["body"]["line-height"] == "1.2"  # body 兜底默认值，标题不单独设
    assert rules[".main-content p"]["line-height"] == "1.5"  # 段落才走 `--line-height`
    assert rules[".main-content p"]["text-indent"] == "2em"
    assert "h3.chapter" in rules


def test_css_content_applies_settings():
    cfg = Config(
        indent=0,
        line_height="2",
        para_spacing="0.5em",
        chapter_align="left",
        volume_align="left",
        para_align="left",
    )
    rules = parse_css(build_css(cfg))
    assert rules[".main-content p"]["text-indent"] == "0em"
    assert rules[".main-content p"]["margin"] == "0 0 0.5em 0"
    assert rules["body"]["line-height"] == "1.2"  # body 不跟随 `--line-height`
    assert rules[".main-content p"]["line-height"] == "2"  # 段落才是用户设置的值
    assert rules["h3.chapter"]["text-align"] == "left"
    assert rules["h2.volume"]["text-align"] == "left"
    assert rules[".main-content p"]["text-align"] == "left"


def test_headings_centered_by_default():
    """h1~h6 默认居中：否则 `--level` 自定义的 h4/h5/h6 会跟着段落走。"""
    css = build_css(Config())
    assert parse_css(css)["h4"]["text-align"] == "center"
    assert parse_css(css)["h3"]["text-align"] == "center"


def test_cover_css_rules_present():
    """封面页靠 `.cover` 这组 class 上样式（图片封面与文字封面共用同一个容器），
    文字封面另有 `.text-cover` 负责把书名作者压到页面偏下的位置。"""
    rules = parse_css(build_css(Config()))
    assert "margin" in rules[".cover"]
    assert "max-height" in rules[".cover img"]
    assert "margin-top" in rules[".text-cover"]
    assert rules[".text-cover .book-title"]["text-align"] == "center"


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
        Config(), Sources(css_append_text=".text-cover .book-title { color: red; }")
    )
    # 追加在后面是层叠契约：同特异性的规则靠后写的赢，追加到前面就压不住内置值。
    assert css.index("color: red;") > css.index("max-height: 100vh;")
    assert "text-indent" in css  # 内置正文样式还在
    assert parse_css(css)[".text-cover .book-title"]["color"] == "red"


def test_css_append_text_keeps_font_face():
    """追加不影响 `@font-face`（那是内置样式的一部分）。"""
    sources = Sources(
        font=Resource(name="f.ttf", data=b"\x00\x01\x00\x00", media_type="font/ttf"),
        css_append_text="body { color: red; }",
    )
    assert "@font-face" in parse_css(build_css(Config(), sources))


def test_empty_sources_uses_builtin():
    """空 `Sources()`：无外部 CSS、无字体，走内置模板。"""
    css = build_css(Config(), Sources())
    assert css == builtin_css(Config())
    assert "@font-face" not in css
