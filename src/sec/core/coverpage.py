"""封面页的 `<body>` 内容：整本书的第一个内容文档。两种形态，都走 EPUB 标准。

- 有封面图时：`<section epub:type="cover">` 里放一个指向封面图的 `<img>`；图本身在 OPF
  里带 `properties="cover-image"`，另外补一条 `<meta name="cover">` 兼容 EPUB2 时代的
  阅读器。
- 没有封面图时：同一节里直接写书名和作者，即「文字封面」。

为什么用 `epub:type="cover"` 而不是自定义 class：`epub:type` 是 EPUB 3 结构语义词汇表
里的标准声明，阅读器认它；自定义 class 只有本项目自己认。

这里只产出 **body 片段**而不是完整文档，因为 `ebooklib` 的 `EpubHtml.get_content()`
会丢掉外部传入的 `<head>`，自己按 `metas` / `links` / `title` 重新拼；`<meta charset>`
与 CSS 链接要由 `builder._add_cover()` 通过 `add_meta()` / `add_link()` 挂上去，和
正文章节页一个写法。

样式方面，封面页的语义由 `epub:type` 声明，排版则由 `builder.build_css()` 里的
`body > section` 结构选择器负责——各家阅读器对 CSS 里带命名空间的 `epub|type` 属性
选择器支持不一致，所以不靠它来选。
"""

from __future__ import annotations

import html

#: 封面页里可识别的语义角色，写进 `epub:type`，两个前端与 CSS 都不另造 class
COVER_SECTION_TYPE = "cover"


def _esc(text: str) -> str:
    return html.escape(text or "", quote=True)


def image_cover_body(image_name: str, alt: str = "封面") -> str:
    """图片封面页的 body 片段：一个指向封面图的标准 cover section。"""
    return (
        f'<section epub:type="{COVER_SECTION_TYPE}">\n'
        f'  <img src="{_esc(image_name)}" alt="{_esc(alt)}"/>\n'
        "</section>"
    )


def text_cover_body(title: str, author: str = "") -> str:
    """文字封面页的 body 片段：书名 + 作者，没有图片。

    用 `h1` / `p` 而不是自定义 class：书名是这一页真正的标题层级，作者是紧随的
    署名段落，语义本身就够清楚，屏幕阅读器也能正常朗读。两者都为空时返回空 section，
    仍然保留一个合法的封面页。
    """
    parts = [f'<section epub:type="{COVER_SECTION_TYPE}">']
    if title:
        parts.append(f"  <h1>{_esc(title)}</h1>")
    if author:
        parts.append(f"  <p>{_esc(author)}</p>")
    parts.append("</section>")
    return "\n".join(parts)
