"""把章节树组装成 EPUB3：CSS、章节页、封面页、目录。

封面页只往 `epub.EpubHtml` 塞 `<body>` 片段，`<head>` 交给 `add_meta()` / `add_link()`：
`EpubHtml.get_content()` 会丢掉外部传入的 head 自己重拼，直接给完整文档会把 charset
与 CSS 链接弄丢。

本模块不读文件：CSS、字体、封面都以**内容**形式由 `Sources` 送来。
"""

from __future__ import annotations

import io
import uuid

from ebooklib import epub

from .cleaner import escape
from .config import Config
from .parser import Node
from .sources import Resource, Sources

#: 封面页的语义角色，写进 `epub:type`（EPUB 3 结构语义词汇表里的标准声明）
COVER_SECTION_TYPE = "cover"

#: 内嵌字体的 CSS 家族名：@font-face 声明与正文引用共用这一份
_FONT_FAMILY = "sec-font"

#: 内嵌资源在 EPUB 内的目录（写进 manifest 的 href 前缀，与 CSS 里的 url() 对应）
FONT_DIR = "fonts"
IMAGE_DIR = "images"

#: 只给 h1~h3 单独建内容文档；更深的层级并入最近的上级页，作为页内锚点
PAGE_MAX_LEVEL = 3


def build_css(cfg: Config, sources: Sources | None = None) -> str:
    """产出用的 CSS。三种情形：整份替代内置、追加在内置之后、纯内置。

    - `sources.css_text` 非空：以它为**全部**样式（替代内置）
    - `sources.css_append_text` 非空：把它**追加**在内置样式之后
    - 都不给：内置模板

    前两者互斥（`Sources.__post_init__` 兜住），不会同时出现。
    想在内置基础上大改，先用 `--dump-css` 导一份 `builtin_css()`，改完再作为整份替代传回来。
    """
    sources = sources or Sources()
    if sources.css_text is not None:
        return sources.css_text
    css = builtin_css(cfg, sources.font.name if sources.font else None)
    if sources.css_append_text is not None:
        css = f"{css}\n{sources.css_append_text}"
    return css


def builtin_css(cfg: Config, font_name: str | None = None) -> str:
    """内置 CSS 模板：@font-face → 正文样式 → 封面页样式。`--dump-css` 导出的就是这一份。

    `font_name` 是字体**文件名**（不含目录），不是路径：`@font-face` 里的
    `src: url("fonts/<name>")` 只需要文件名，用不到字体的实际字节——所以导出模板这条
    路径不必加载字体资源。
    """
    css: list[str] = []
    if font_name:
        css.append(
            f'@font-face {{\n  font-family: "{_FONT_FAMILY}";\n'
            f'  src: url("{FONT_DIR}/{font_name}");\n}}'
        )
    family = f'"{_FONT_FAMILY}", ' if font_name else ""

    css.append(f"""body {{
  line-height: 1.2;
  font-family: {family}sans-serif;
}}
h1, h2, h3, h4, h5, h6 {{
  text-align: center;
  font-weight: bold;
}}
h2.volume {{
  margin: 1.5em 0 1em 0;
  padding: 0.5em 0;
  border-top: 3px double;
  border-bottom: 3px double;
  text-align: {cfg.volume_align};
  font-size: 2.2em;
}}
h3.chapter {{
  margin: 1em 0;
  text-align: {cfg.chapter_align};
  font-size: 1.8em;
}}
.main-content p {{
  margin: 0 0 {cfg.para_spacing} 0;
  text-indent: {cfg.indent}em;
  text-align: {cfg.para_align};
  line-height: {cfg.line_height};
}}
""")
    # 封面容器按 class 命中，不写 body > section：正文页也有 section，结构选择器
    # 各家阅读器支持还不一致。书名/作者另挂 class，好从上面 `h1~h6` 的居中里摘出来。
    css.append(""".cover {
  margin: 0;
}
.cover .book-title {
  margin-top: 3em;
  margin-bottom: 0;
  font-size: 3em;
  text-align: center;
}
.cover .book-author {
  margin-top: 1em;
  margin-bottom: 0;
  padding-left: 1.5em;  /* 装饰符号宽度 */
  text-indent: -1.5em;
  font-size: 1.5em;
  text-align: center;
}
.cover .book-author::before {
  content: "◎";
  margin-right: 0.5em;
}
.cover img {
  display: block;
  margin: 0 auto;
  max-width: 100%;
  max-height: 100vh;
}""")
    return "\n".join(css)


def image_cover_body(image_name: str, alt: str = "封面") -> str:
    """图片封面页的 body 片段：一个带 class="cover" 的封面容器。"""
    return (
        f'<section class="cover" epub:type="{COVER_SECTION_TYPE}">\n'
        f'  <img src="{escape(image_name)}" alt="{escape(alt)}"/>\n'
        "</section>"
    )


def text_cover_body(title: str, author: str = "") -> str:
    """文字封面页的 body 片段：书名 + 作者，没有图片。

    标签用 `h1` / `p`，另挂 class 供样式定位。
    """
    parts = [f'<section class="cover" epub:type="{COVER_SECTION_TYPE}">']
    if title:
        parts.append(f'  <h1 class="book-title">{escape(title)}</h1>')
    if author:
        parts.append(f'  <p class="book-author">{escape(author)}</p>')
    parts.append("</section>")
    return "\n".join(parts)


def build_epub(
    cfg: Config, nodes: list[Node], sources: Sources | None
) -> bytes:
    """把 `nodes` 组装成 EPUB 字节。CSS、字体、封面都从 `sources` 取，不读也不写文件。

    返回字节而不是收 sink，是为了让「组装」完整跑完再落盘：写盘失败或组装失败都
    不会留下半个 EPUB。落盘的事交给 `pipeline.write_epub`。
    """
    sources = sources or Sources()
    css = build_css(cfg, sources)
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
            uid="style",
            file_name="style.css",
            media_type="text/css",
            content=css.encode("utf-8"),
        )
    )
    if sources.font is not None:
        _add_font(book, sources.font)

    pages: list[epub.EpubHtml] = []
    page_map: dict[str, epub.EpubHtml] = {}
    cover_page = _add_cover(book, cfg, sources.cover)

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
    # 封面 → nav → 正文，跟纸质书一样；两个封面页都是 linear="yes"，这就是阅读顺序。
    book.spine = (
        ([cover_page] if cover_page is not None else [])
        + (["nav"] if cfg.toc_in_spine else [])
        + pages
    )
    buf = io.BytesIO()
    # `raise_exceptions` 是改 `ebooklib` 的默认行为：它默认自己 `except OSError`、
    # `warnings.warn` 后返回 False，写盘失败会被静默吞掉，调用方只会看到
    # 「生成成功」却拿不到东西。
    epub.write_epub(
        buf, book, options={"compresslevel": 9, "raise_exceptions": True}
    )
    return buf.getvalue()


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
    """一页的正文：根标题与段落，再递归并入所有不成页的后代（带 `id` 供片段链接）。

    整页装进 `<section class="main-content">`，卷页/章页/前言页同壳：正文段落一律是
    `p`，要单独上样式挂 `.main-content p` 即可，标题仍由 `h2.volume` 等规则管。
    """
    blocks: list[str] = []

    def render(node: Node, is_root: bool) -> None:
        blocks.append(_heading(node, with_id=not is_root))
        blocks.extend(f"<p>{escape(p)}</p>" for p in node.paragraphs)
        for child in node.children:
            if not _is_page_root(child, has_page_ancestor=True):
                render(child, False)

    render(root, True)
    return '<section class="main-content">\n' + "\n".join(blocks) + "\n</section>"


def _heading(node: Node, *, with_id: bool) -> str:
    # 前言/兜底单章（level 0）没有标题行，按「章」渲染成 h3（不占用 h1——那通常
    # 留给书名，或用户用 `--level h1:…` 显式定义的层级）。level 1~6 照常映射 h1~h6。
    level = node.level if node.level > 0 else 3
    # `title_html` 是 `process()` 转义并跑完 html 阶段替换的结果；没有时按原文转义。
    title = node.title_html or escape(node.title)
    # class 省略的层级（`--level h2:…`）不加 class，直接落到 `hN` 标签选择器上。
    class_attr = f' class="{escape(node.class_name)}"' if node.class_name else ""
    id_attr = f' id="{node.anchor}"' if with_id else ""
    return f"<h{level}{class_attr}{id_attr}>{title}</h{level}>"


def _toc_entries(
    nodes: list[Node],
    page_map: dict[str, epub.EpubHtml],
    owner: dict[str, str],
    depth: int,
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
            _toc_entries(node.children, page_map, owner, depth)
            if node.level < depth
            else []
        )
        out.append((entry, children) if children else entry)
    return out


def _toc_entry(
    node: Node, page_map: dict[str, epub.EpubHtml], owner: dict[str, str]
) -> object:
    root_anchor = owner[node.anchor]
    page = page_map[root_anchor]
    if node.anchor == root_anchor:
        return page
    return epub.Link(f"{page.file_name}#{node.anchor}", node.title, node.anchor)


def _add_font(book: epub.EpubBook, font: Resource) -> None:
    """内嵌字体：按 `Resource.media_type` 登记，路径与 CSS 里的 `url()` 对应。"""
    book.add_item(
        epub.EpubItem(
            uid="font",
            file_name=f"{FONT_DIR}/{font.name}",
            media_type=font.media_type,
            content=font.data,
        )
    )


def _add_cover(
    book: epub.EpubBook,
    cfg: Config,
    cover: Resource | None,
) -> epub.EpubHtml | None:
    """装配封面页并返回它；没有封面时返回 `None`（调用方据此决定 spine 开头）。

    `cover` 是内容而非路径——上游 `sources.cover_for()` 已经判完有没有封面、是哪一张。
    两种封面页都不设 `is_linear`：默认的 `linear="yes"` 就是打开书的第一页。
    """
    if cover is not None:
        image = f"{IMAGE_DIR}/{cover.name}"
        book.set_cover(image, cover.data, create_page=False)
        item = book.get_item_with_id("cover-img")
        if item is None:
            # 拿不到就修不了 media_type，产出打不开的 epub，不如报错
            raise ValueError(f"未能取得封面图片项，封面类型无法修正：{cover.name}")
        item.media_type = cover.media_type
        title, body = "封面", image_cover_body(image, alt=cfg.book_title)
    elif cfg.text_cover:
        title, body = cfg.book_title, text_cover_body(cfg.book_title, cfg.author)
    else:
        return None

    page = epub.EpubHtml(uid="cover", file_name="cover.xhtml", title=title)
    page.content = body.encode("utf-8")
    page.add_meta(charset="utf-8")
    page.add_link(href="style.css", rel="stylesheet", type="text/css")
    book.add_item(page)
    return page
