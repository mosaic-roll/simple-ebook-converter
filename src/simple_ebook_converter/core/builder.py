from __future__ import annotations

import html
import uuid
from pathlib import Path

from ebooklib import epub

from .config import Config, Node
from .coverpage import image_cover_body, text_cover_body
from .mediatypes import cover_media_type, font_media_type
from .parser import walk


def build_css(cfg: Config) -> str:
    css: list[str] = []
    if cfg.font:
        name = Path(cfg.font).name
        css.append(
            f"""@font-face {{
  font-family: "sec-font";
  src: url("fonts/{name}");
}}"""
        )
    family = '"sec-font", ' if cfg.font else ""
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
    # 封面页：整本书只有封面页的 body 里直接挂 section，章节页没有，所以下面这组
    # 结构选择器只会命中封面页。这样就不必为了样式自造 class——封面页的语义由
    # `epub:type="cover"` 声明（见 coverpage.py），这里只负责排版。
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
        css.append(Path(cfg.css_file).read_text(encoding="utf-8"))
    return "\n".join(css)


def _page_html(node: Node) -> str:
    esc = html.escape
    level = max(1, node.level)
    cls = node.class_name or (f"level{node.level}" if node.level > 0 else "preface")
    heading = f"<h{level} class=\"{esc(cls)}\">{esc(node.title)}</h{level}>"
    paragraphs = "".join(f"<p>{esc(p)}</p>" for p in node.paragraphs)
    return f"{heading}\n{paragraphs}"


def _build_toc(nodes: list[Node], page_map: dict[int, epub.EpubHtml], depth: int) -> list:
    out = []
    for node in nodes:
        page = page_map[id(node)]
        if node.children and node.level < depth:
            out.append((page, _build_toc(node.children, page_map, depth)))
        elif node.level <= depth:
            out.append(page)
    return out


def _add_cover(book: epub.EpubBook, cfg: Config, pages: list[epub.EpubHtml]) -> None:
    """装配封面页，并把封面页追加到 `pages`（它会进 spine）。

    三种情况：

    - 有封面图：`set_cover()` 写 manifest item（带 `properties="cover-image"`）并补一条
      `<meta name="cover">`——后者是 EPUB2 时代的约定，ebooklib 自带封面页时会给，
      少了它一部分旧阅读器/工具就认不出封面。封面页 `linear="no"`，不打断正文流。
    - 没封面图但 `text_cover` 开着：放一个只含书名/作者的「文字封面页」，
      `linear="yes"`，它就是书的第一页。
    - 都没有：整本书没有封面，`spine` 直接从第一章开始。

    两种封面页都只传 body 片段给 `epub.EpubHtml`，`<meta charset>` 与 CSS 链接走
    `add_meta()` / `add_link()`——`get_content()` 会重建 head，直接塞完整文档会被丢掉。
    """
    title = cfg.title or Path(str(cfg.input)).stem

    if cfg.cover:
        path = Path(cfg.cover)
        media = cover_media_type(path)
        book.set_cover(f"images/{path.name}", path.read_bytes(), create_page=False)
        # set_cover 靠扩展名猜 media-type，但标准 mimetypes 不认 .webp（猜出 None），
        # 猜错就会在 manifest 里写出空的 media-type，所以显式改回 mediatypes 的表。
        item = book.get_item_with_id("cover-img")
        if item is not None:
            item.media_type = media
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


def build_epub(cfg: Config, nodes: list[Node], css: str, output: Path) -> None:
    book = epub.EpubBook()
    book.set_identifier(f"urn:uuid:{uuid.uuid4()}")
    book.set_title(cfg.title or Path(str(cfg.input)).stem)
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
    page_map: dict[int, epub.EpubHtml] = {}

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
        page_map[id(node)] = page
        pages.append(page)

    if nodes:
        book.toc = _build_toc(nodes, page_map, cfg.toc_depth)
    book.add_item(epub.EpubNav())
    book.add_item(epub.EpubNcx())

    book.spine = (["nav"] if not cfg.no_toc else []) + [p for p in pages]
    epub.write_epub(output, book, options={"compresslevel": 9})
