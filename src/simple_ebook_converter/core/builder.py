"""把章节树组装成 EPUB3：CSS、章节页、封面页、目录。

封面页只往 `epub.EpubHtml` 塞 `<body>` 片段，`<head>` 交给 `add_meta()` / `add_link()`：
`EpubHtml.get_content()` 会丢掉外部传入的 head 自己重拼，直接给完整文档会把 charset
与 CSS 链接弄丢。
"""

from __future__ import annotations

import html
import uuid
from pathlib import Path

from ebooklib import epub

from .config import Config
from .mediatypes import cover_media_type, font_media_type
from .parser import Node, walk

#: 封面页的语义角色，写进 `epub:type`（EPUB 3 结构语义词汇表里的标准声明）
COVER_SECTION_TYPE = "cover"

#: 内置字体的 CSS 家族名：@font-face 声明与正文引用共用这一份
_FONT_FAMILY = "sec-font"


def build_css(cfg: Config) -> str:
    """当前设置下的完整 CSS：@font-face → 正文样式 → 封面页样式 → 外部 CSS。"""
    css: list[str] = []
    if cfg.font:
        name = Path(cfg.font).name
        css.append(f'@font-face {{\n  font-family: "{_FONT_FAMILY}";\n  src: url("fonts/{name}");\n}}')
    family = f'"{_FONT_FAMILY}", ' if cfg.font else ""
    css.append(
        f"""body {{
  margin: 5%;
  font-size: 1em;
  line-height: {cfg.line_height};
  font-family: {family}sans-serif;
}}
p {{
  margin: 0 0 {cfg.para_spacing} 0;
  text-indent: {cfg.indent}em;
}}
h1, h2, h3, h4, h5, h6 {{
  text-align: center;
}}
.volume {{
  text-align: {cfg.volume_align};
}}
.chapter {{
  text-align: {cfg.chapter_align};
}}"""
    )
    # 整本书只有封面页的 body 里直接挂 section，章节页没有，所以这组结构选择器
    # 只命中封面页。不用 epub|type 属性选择器：各家阅读器对它的支持并不一致。
    css.append(
        """body > section {
  margin: 0;
  text-align: center;
}
body > section h1 {
  margin: 2em 0 0.5em;
  font-size: 2em;
  text-indent: 0;
}
body > section p {
  margin: 0;
  text-indent: 0;
}
body > section img {
  display: block;
  margin: 0 auto;
  max-width: 100%;
  max-height: 100vh;
}"""
    )
    if cfg.css_file:
        try:
            css.append(Path(cfg.css_file).read_text(encoding="utf-8"))
        except OSError as e:
            raise ValueError(f"无法读取外部 CSS：{e}") from e
    return "\n".join(css)


def image_cover_body(image_name: str, alt: str = "封面") -> str:
    """图片封面页的 body 片段：一个指向封面图的 cover section。"""
    return (
        f'<section epub:type="{COVER_SECTION_TYPE}">\n'
        f'  <img src="{_esc(image_name)}" alt="{_esc(alt)}"/>\n'
        "</section>"
    )


def text_cover_body(title: str, author: str = "") -> str:
    """文字封面页的 body 片段：书名 + 作者，没有图片。

    用 `h1` / `p` 而不是自定义 class——这一页的标题层级与署名段落本身就是那个意思。
    """
    parts = [f'<section epub:type="{COVER_SECTION_TYPE}">']
    if title:
        parts.append(f"  <h1>{_esc(title)}</h1>")
    if author:
        parts.append(f"  <p>{_esc(author)}</p>")
    parts.append("</section>")
    return "\n".join(parts)


def build_epub(cfg: Config, nodes: list[Node], css: str, output: Path) -> None:
    """把 `nodes` 写成 EPUB 文件。`css` 由 `build_css()` 生成。"""
    book = epub.EpubBook()
    book.set_identifier(f"urn:uuid:{uuid.uuid4()}")
    book.set_title(cfg.book_title)
    if cfg.author:
        book.add_author(cfg.author)
    book.set_language(cfg.language)
    if cfg.date:
        book.add_metadata("DC", "date", cfg.date)

    book.add_item(
        epub.EpubItem(uid="style", file_name="style.css", media_type="text/css", content=css.encode("utf-8"))
    )
    if cfg.font:
        path = Path(cfg.font)
        book.add_item(
            epub.EpubItem(
                uid="font",
                file_name=f"fonts/{path.name}",
                media_type=font_media_type(path),
                content=path.read_bytes(),
            )
        )

    pages: list[epub.EpubHtml] = []
    page_map: dict[str, epub.EpubHtml] = {}
    _add_cover(book, cfg, pages)

    for node in walk(nodes):
        page = epub.EpubHtml(
            title=node.title,
            file_name=f"text/{node.anchor}.xhtml",
            content=_page_html(node).encode("utf-8"),
        )
        page.add_meta(charset="utf-8")
        page.add_link(href="../style.css", rel="stylesheet", type="text/css")
        book.add_item(page)
        page_map[node.anchor] = page
        pages.append(page)

    if nodes:
        book.toc = _toc_entries(nodes, page_map, cfg.toc_depth)
    book.add_item(epub.EpubNav())
    book.add_item(epub.EpubNcx())
    book.spine = (["nav"] if cfg.toc_in_spine else []) + pages
    epub.write_epub(output, book, options={"compresslevel": 9})


def _page_html(node: Node) -> str:
    esc = html.escape
    level = max(1, node.level)
    heading = f'<h{level} class="{esc(node.class_name)}">{esc(node.title)}</h{level}>'
    paragraphs = "".join(f"<p>{esc(p)}</p>" for p in node.paragraphs)
    return f"{heading}\n{paragraphs}"


def _toc_entries(
    nodes: list[Node], page_map: dict[str, epub.EpubHtml], depth: int
) -> list:
    """章节树转 ebooklib 的 toc 结构；`depth` 之外的层级不写进目录。"""
    out = []
    for node in nodes:
        page = page_map[node.anchor]
        if node.children and node.level < depth:
            out.append((page, _toc_entries(node.children, page_map, depth)))
        elif node.level <= depth:
            out.append(page)
    return out


def _add_cover(book: epub.EpubBook, cfg: Config, pages: list[epub.EpubHtml]) -> None:
    """装配封面页并追加到 `pages`（它会进 spine）。三种情况：

    - 有封面图：图进 manifest（带 `properties="cover-image"`），另补一条
      `<meta name="cover">` 兼容 EPUB2 时代的阅读器；封面页 `linear="no"`，不打断正文。
    - 没图但 `text_cover` 开着：放只含书名/作者的封面页，`linear="yes"`，它就是第一页。
    - 都没有：整本书没有封面，spine 直接从第一章开始。
    """
    title = cfg.book_title
    if cfg.cover:
        path = Path(cfg.cover)
        book.set_cover(f"images/{path.name}", path.read_bytes(), create_page=False)
        item = book.get_item_with_id("cover-img")
        if item is not None:
            item.media_type = cover_media_type(path)
        page = epub.EpubHtml(uid="cover", file_name="cover.xhtml", title="封面")
        page.is_linear = False
        page.content = image_cover_body(f"images/{path.name}", alt=title).encode("utf-8")
    elif cfg.text_cover:
        page = epub.EpubHtml(uid="cover", file_name="cover.xhtml", title=title)
        page.content = text_cover_body(title, cfg.author).encode("utf-8")
    else:
        return
    page.add_meta(charset="utf-8")
    page.add_link(href="style.css", rel="stylesheet", type="text/css")
    book.add_item(page)
    pages.append(page)


def _esc(text: str) -> str:
    return html.escape(text or "", quote=True)
