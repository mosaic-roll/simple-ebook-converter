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
from .parser import Node

#: 封面页的语义角色，写进 `epub:type`（EPUB 3 结构语义词汇表里的标准声明）
COVER_SECTION_TYPE = "cover"

#: 内置字体的 CSS 家族名：@font-face 声明与正文引用共用这一份
_FONT_FAMILY = "sec-font"

#: 只给 h1~h3 单独建内容文档；更深的层级并入最近的上级页，作为页内锚点
PAGE_MAX_LEVEL = 3


def build_css(cfg: Config) -> str:
    """产出用的 CSS。

    三种情形：给了 `--css-file` 就以它为全部样式（**替代**内置）；给了 `--css-append`
    就把它追加在内置样式之后；都不给就是内置模板。三者不同时出现（`Config.validate()`
    会拦下 `--css-file` 与 `--css-append` 同给）。

    想在内置基础上大改，先用 `--dump-css` 导一份 `builtin_css()`，改完再当 `--css-file`
    传回来。
    """
    if cfg.css_file:
        return _read_css(cfg.css_file)
    css = builtin_css(cfg)
    if cfg.css_append:
        css = f"{css}\n{_read_css(cfg.css_append)}"
    return css


def builtin_css(cfg: Config) -> str:
    """内置 CSS 模板：@font-face → 正文样式 → 封面页样式。`--dump-css` 导出的就是这一份。"""
    css: list[str] = []
    if cfg.font:
        name = Path(cfg.font).name
        css.append(
            f'@font-face {{\n  font-family: "{_FONT_FAMILY}";\n  src: url("fonts/{name}");\n}}'
        )
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
}}
body {{
  text-align: {cfg.body_align};
}}"""
    )
    # 整本书只有封面页的 body 里直接挂 section，章节页没有，所以这组结构选择器
    # 只命中封面页。不用 epub|type 属性选择器：各家阅读器对它的支持并不一致；
    # 加 class="cover" 让 CSS 意图更明确。
    css.append(
        """.cover {
  margin: 0;
  text-align: center;
}
.cover h1 {
  margin: 2em 0 0.5em;
  font-size: 2em;
  text-indent: 0;
}
.cover p {
  margin: 0;
  text-indent: 0;
}
.cover img {
  display: block;
  margin: 0 auto;
  max-width: 100%;
  max-height: 100vh;
}"""
    )
    return "\n".join(css)


def _read_css(path: Path) -> str:
    try:
        return Path(path).read_text(encoding="utf-8")
    except OSError as e:
        raise ValueError(f"无法读取外部 CSS：{e}") from e


def image_cover_body(image_name: str, alt: str = "封面") -> str:
    """图片封面页的 body 片段：一个带 class="cover" 的封面容器。"""
    return (
        f'<section class="cover" epub:type="{COVER_SECTION_TYPE}">\n'
        f'  <img src="{escape(image_name)}" alt="{escape(alt)}"/>\n'
        "</section>"
    )


def text_cover_body(title: str, author: str = "") -> str:
    """文字封面页的 body 片段：书名 + 作者，没有图片。

    用 `h1` / `p` 而不是自定义 class——这一页的标题层级与署名段落本身就是那个意思。
    """
    parts = [f'<section class="cover" epub:type="{COVER_SECTION_TYPE}">']
    if title:
        parts.append(f"  <h1>{escape(title)}</h1>")
    if author:
        parts.append(f"  <p>{escape(author)}</p>")
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
        epub.EpubItem(
            uid="style", file_name="style.css", media_type="text/css", content=css.encode("utf-8")
        )
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

    roots = _page_roots(nodes)
    owner = _page_owner_by_anchor(roots)
    for root in roots:
        page = epub.EpubHtml(
            title=root.title,
            file_name=f"text/{root.anchor}.xhtml",
            content=_render_page(root).encode("utf-8"),
        )
        page.add_meta(charset="utf-8")
        page.add_link(href="../style.css", rel="stylesheet", type="text/css")
        book.add_item(page)
        page_map[root.anchor] = page
        pages.append(page)

    if nodes:
        book.toc = _toc_entries(nodes, page_map, owner, cfg.toc_depth)
    book.add_item(epub.EpubNav())
    book.add_item(epub.EpubNcx())
    book.spine = (["nav"] if cfg.toc_in_spine else []) + pages
    epub.write_epub(output, book, options={"compresslevel": 9})


def _is_page_root(node: Node, has_page_ancestor: bool) -> bool:
    """是否单独成页：h1~h3 一律成页；更深的层级若没有成页的祖先也成页
    （例如只启用 h4 当章），否则并入祖先页，避免正文无家可归。
    """
    return node.level <= PAGE_MAX_LEVEL or not has_page_ancestor


def _page_roots(nodes: list[Node]) -> list[Node]:
    """文档序返回所有需要单独成页的节点。"""
    roots: list[Node] = []

    def visit(items: list[Node], has_page_ancestor: bool) -> None:
        for node in items:
            is_root = _is_page_root(node, has_page_ancestor)
            if is_root:
                roots.append(node)
            visit(node.children, has_page_ancestor or is_root)

    visit(nodes, False)
    return roots


def _page_owner_by_anchor(roots: list[Node]) -> dict[str, str]:
    """每个节点 anchor → 它所在页面的 anchor（页内节点的片段链接要用）。"""
    owner: dict[str, str] = {}

    def collect(node: Node, root_anchor: str) -> None:
        owner[node.anchor] = root_anchor
        for child in node.children:
            if not _is_page_root(child, has_page_ancestor=True):
                collect(child, root_anchor)

    for root in roots:
        collect(root, root.anchor)
    return owner


def _render_page(root: Node) -> str:
    """一页的正文：根标题与段落，再递归并入所有不成页的后代（带 `id` 供片段链接）。"""
    blocks: list[str] = []

    def render(node: Node, is_root: bool) -> None:
        blocks.append(_heading(node, with_id=not is_root))
        blocks.extend(f"<p>{escape(p)}</p>" for p in node.paragraphs)
        for child in node.children:
            if not _is_page_root(child, has_page_ancestor=True):
                render(child, False)

    render(root, True)
    return "\n".join(blocks)


def _heading(node: Node, *, with_id: bool) -> str:
    level = max(1, node.level)
    # `title_html` 是 `process()` 转义并跑完 html 阶段替换的结果；没有时按原文转义。
    title = node.title_html or escape(node.title)
    # class 省略的层级（`--level h2:…`）不加 class，直接落到 `hN` 标签选择器上。
    class_attr = f' class="{escape(node.class_name)}"' if node.class_name else ""
    id_attr = f' id="{node.anchor}"' if with_id else ""
    return f"<h{level}{class_attr}{id_attr}>{title}</h{level}>"


def _toc_entries(
    nodes: list[Node], page_map: dict[str, epub.EpubHtml], owner: dict[str, str], depth: int
) -> list:
    """章节树转 ebooklib 的 toc 结构；超过 `depth` 的层级不写进目录。

    成页的节点直接引用其页面；并入上级页的节点（h4+）用页内片段链接。
    """
    out = []
    for node in nodes:
        if node.level > depth:
            continue
        entry = _toc_entry(node, page_map, owner)
        children = (
            _toc_entries(node.children, page_map, owner, depth) if node.level < depth else []
        )
        out.append((entry, children) if children else entry)
    return out


def _toc_entry(node: Node, page_map: dict[str, epub.EpubHtml], owner: dict[str, str]) -> object:
    root_anchor = owner[node.anchor]
    page = page_map[root_anchor]
    if node.anchor == root_anchor:
        return page
    return epub.Link(f"{page.file_name}#{node.anchor}", node.title, node.anchor)


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


def escape(text: str) -> str:
    return html.escape(text or "", quote=True)
