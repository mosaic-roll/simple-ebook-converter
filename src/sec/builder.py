from __future__ import annotations

import html
import uuid
from pathlib import Path

from ebooklib import epub

from .config import Config, Node

_MEDIA_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".svg": "image/svg+xml",
    ".webp": "image/webp",
    ".avif": "image/avif",
}

_FONT_TYPES = {
    ".ttf": "font/ttf",
    ".otf": "font/otf",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
}


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
    if cfg.css_file:
        css.append(Path(cfg.css_file).read_text(encoding="utf-8"))
    return "\n".join(css)


def _page_html(cfg: Config, node: Node) -> str:
    esc = html.escape
    level = max(1, node.level)
    cls = node.cls or f"level{node.level}" if node.level > 0 else "preface"
    heading = f"<h{level} class=\"{esc(cls)}\">{esc(node.title)}</h{level}>"
    paragraphs = "".join(f"<p>{esc(p)}</p>" for p in node.paragraphs)
    return f"{heading}\n{paragraphs}"


def _ordered(nodes: list[Node]) -> list[Node]:
    out: list[Node] = []
    for node in nodes:
        out.append(node)
        out.extend(_ordered(node.children))
    return out


def _build_toc(nodes: list[Node], page_map: dict[int, epub.EpubHtml], depth: int) -> list:
    out = []
    for node in nodes:
        page = page_map[id(node)]
        if node.children and node.level < depth:
            out.append((page, _build_toc(node.children, page_map, depth)))
        elif node.level <= depth:
            out.append(page)
    return out


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
        ext = path.suffix.lower()
        book.add_item(
            epub.EpubItem(
                uid="font",
                file_name=f"fonts/{path.name}",
                media_type=_FONT_TYPES.get(ext, "application/octet-stream"),
                content=path.read_bytes(),
            )
        )

    pages: list[epub.EpubHtml] = []
    page_map: dict[int, epub.EpubHtml] = {}

    if cfg.cover:
        path = Path(cfg.cover)
        cover_img = epub.EpubCover(file_name=f"images/{path.name}")
        cover_img.content = path.read_bytes()
        cover_img.media_type = _MEDIA_TYPES.get(path.suffix.lower(), "image/jpeg")
        book.add_item(cover_img)
        cover_page = epub.EpubCoverHtml(image_name=f"images/{path.name}", title="封面")
        book.add_item(cover_page)
        pages.append(cover_page)

    for node in _ordered(nodes):
        page = epub.EpubHtml(
            title=node.title,
            file_name=f"text/{node.anchor}.xhtml",
            content=_page_html(cfg, node).encode("utf-8"),
        )
        page.add_meta(charset="utf-8")
        page.add_link(href="../style.css", rel="stylesheet", type="text/css")
        book.add_item(page)
        page_map[id(node)] = page
        pages.append(page)

    has_toc = bool(nodes) and not cfg.no_toc
    if has_toc:
        book.toc = _build_toc(nodes, page_map, cfg.toc_depth)
        book.add_item(epub.EpubNav())
    book.add_item(epub.EpubNcx())

    book.spine = (["nav"] if has_toc else []) + [p for p in pages]
    epub.write_epub(output, book)