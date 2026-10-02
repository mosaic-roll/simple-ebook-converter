"""测试基建：临时输入、`Epub` 语义断言、CSS 解析、标题断言。

只放"读产物并按契约断言"的东西，不放业务规则——业务规则的期望值写在各测试里，
一眼能看出这个模块承诺什么。
"""

from __future__ import annotations

import posixpath
import re
import urllib.parse
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

#: 外部链接不检查可达：EPUB 里可以有指向站外的 href。
_EXTERNAL = re.compile(r"^(?:[a-z][a-z0-9+.-]*:|//)", re.IGNORECASE)

_OPF_NS = "{http://www.idpf.org/2007/opf}"
#: manifest 里只有这两类能靠字节头验出真伪；其余（css/xhtml/ncx）认不出就跳过。
_SNIFFABLE = ("image/", "font/")


def resolve_href(base_name: str, href: str) -> str:
    """包内相对链接 → 包根相对路径。

    `base_name` 是链接**所在**的包内路径：manifest 的 href 相对 OPF 自身，nav 的相对
    nav.xhtml，正文页的 `../style.css` 相对它所在的 `text/` 子目录——三种基准不同，
    都得拿所在文件去拼。片段与查询串剥掉，中文文件名按百分号解码。
    """
    path = urllib.parse.unquote(href.split("#")[0].split("?")[0])
    if not path:
        return base_name
    if path.startswith("/"):
        return posixpath.normpath(path.lstrip("/"))
    return posixpath.normpath(posixpath.join(posixpath.dirname(base_name), path))


class Epub:
    """一本构建好的 EPUB：解开成 `entries`，按契约而不是按内部编号来断言。

    页名（`p0001.xhtml`）、anchor（`p0002`）是实现策略，改了不算破坏；manifest 的
    `media-type` 与实际字节是否一致、链接是否可达才是对外承诺。
    """

    def __init__(self, path: Path):
        self.path = path
        with zipfile.ZipFile(path) as z:
            self.entries = {n: z.read(n) for n in z.namelist()}

    def has_entry(self, name: str) -> bool:
        return name in self.entries

    def set_opf(self, transform) -> None:
        """就地改写 OPF 文本（`transform` 收原文、返新文）。给"故意造坏"用。"""
        name = self.opf_name()
        self.entries[name] = transform(self.entries[name].decode("utf-8")).encode("utf-8")

    def html(self, name: str) -> str:
        return self.entries[name].decode("utf-8")

    def opf(self) -> str:
        return self.html(self.opf_name())

    def opf_name(self) -> str:
        """按 container.xml 指的路找 OPF，不假设路径就叫 content.opf。

        `full-path` 是**包根**相对，不能拿 `resolve_href` 以 container.xml 为基准拼——
        那样会得到 `META-INF/EPUB/content.opf`。
        """
        root = ET.fromstring(self.entries["META-INF/container.xml"])
        ns = "{urn:oasis:names:tc:opendocument:xmlns:container}"
        node = root.find(f"{ns}rootfiles/{ns}rootfile")
        full_path = node.get("full-path") if node is not None else None
        assert full_path, "container.xml 里没有 rootfile/@full-path"
        return posixpath.normpath(full_path)

    def nav(self) -> str:
        names = [n for n in self.entries if n.endswith(".xhtml") and _is_nav(n)]
        assert len(names) == 1, f"期望恰好一本 nav，实际：{names}"
        return self.html(names[0])

    def text_pages(self) -> list[str]:
        return sorted(n for n in self.entries if "/text/" in n and n.endswith(".xhtml"))

    def manifest_items(self) -> list[dict[str, str]]:
        opf_name = self.opf_name()
        root = ET.fromstring(self.entries[opf_name])
        items = []
        for item in root.iter(f"{_OPF_NS}item"):
            items.append(
                {
                    "id": item.get("id", ""),
                    "href": item.get("href", ""),
                    "media-type": item.get("media-type", ""),
                    "properties": item.get("properties", ""),
                }
            )
        return items

    def manifest_item(self, *, prop: str | None = None, suffix: str | None = None
                      ) -> dict[str, str]:
        """按 `properties`（如 `cover-image`）或 href 后缀取唯一一条 manifest item。"""
        hits = [
            it
            for it in self.manifest_items()
            if (prop is None or prop in it["properties"].split())
            and (suffix is None or it["href"].endswith(suffix))
        ]
        assert len(hits) == 1, (
            f"期望恰好一条 manifest item（prop={prop!r} suffix={suffix!r}），"
            f"实际 {len(hits)} 条：{hits}"
        )
        return hits[0]

    def spine_ids(self) -> list[str]:
        """spine 的 itemref 顺序（item id，不是文件名）。"""
        return [idref for idref, _linear in self.spine_items()]

    def spine_items(self) -> list[tuple[str, bool]]:
        """spine 解析成 `[(item id, 是否 linear)]`。

        `linear="no"` 是 EPUB3 里的"辅助内容"：不进正文流，只能靠链接到达。带
        `linear="no"` 又没有指向它的链接就是 OPF-096。
        """
        root = ET.fromstring(self.entries[self.opf_name()])
        spine = root.find(f"{_OPF_NS}spine")
        assert spine is not None, "OPF 里没有 spine"
        return [
            (item.get("idref", ""), item.get("linear", "yes") != "no")
            for item in spine.iter(f"{_OPF_NS}itemref")
        ]

    def itemref_target(self, idref: str) -> str:
        """spine 里的 idref → 包内实际路径，顺便验证 idref 有对应 manifest item。"""
        items = {it["id"]: it for it in self.manifest_items()}
        assert idref in items, f"spine 的 idref={idref!r} 在 manifest 里没有对应 item"
        return resolve_href(self.opf_name(), items[idref]["href"])

    # ---- 契约断言 ----

    def assert_links_reachable(self) -> None:
        """所有包内链接都指向存在的条目；带片段的还要在目标页里真有那个 id。

        nav、正文页、OPF manifest、container.xml 都扫。href 用正则取而不是解析 XML：
        替换阶段允许用户塞任意 HTML，页面未必是良构 XML，而漏掉一条链接的后果正是
        这条断言要拦的东西。
        """
        for name, text in self._html_like():
            for _, raw in _HREF_RE.findall(text):
                if _EXTERNAL.match(raw) or raw.startswith("#"):
                    continue
                target, _, frag = raw.partition("#")
                resolved = resolve_href(name, target)
                assert resolved in self.entries, (
                    f"{name} 里的链接 {raw!r} 指向不存在的条目：{resolved}\n"
                    f"包内条目：{sorted(self.entries)}"
                )
                if frag:
                    body = self.entries[resolved].decode("utf-8")
                    assert f'id="{urllib.parse.unquote(frag)}"' in body, (
                        f"{name} 里的片段 #{frag} 在 {resolved} 里找不到对应 id"
                    )

    def assert_manifest_media_types_match_bytes(self) -> None:
        """manifest 声明的 `media-type` 与文件实际字节一致。

        这条才是 OPF-029 / PKG-022 的根因：扩展名和声明可以各自合法、互相撒谎，
        只有按字节头复核才拦得住。声明成图片/字体却认不出字节，说明有格式没实现，
        按失败处理而不是跳过——跳过就等于在这类回归面前静默。
        """
        from simple_ebook_converter.core.mediatypes import sniff_font, sniff_image

        opf_name = self.opf_name()
        for item in self.manifest_items():
            declared = item["media-type"]
            if not declared.startswith(_SNIFFABLE):
                continue
            resolved = resolve_href(opf_name, item["href"])
            assert resolved in self.entries, f"manifest 指向不存在的条目：{resolved}"
            data = self.entries[resolved]
            sniffed = sniff_image(data) or sniff_font(data)
            assert sniffed is not None, (
                f"{item['href']} 声明 {declared!r}，但字节头认不出格式；"
                f"前 16 字节：{data[:16]!r}"
            )
            actual = sniffed[0]
            assert actual == declared, (
                f"{item['href']} 声明 {declared!r}，实际字节是 {actual!r}"
            )

    def _html_like(self) -> list[tuple[str, str]]:
        """`(包内路径, 文本)`：页面、OPF、NCX，加 container.xml。"""
        names = [n for n in self.entries if n.endswith((".xhtml", ".opf", ".ncx"))]
        names.append("META-INF/container.xml")
        return [(n, self.entries[n].decode("utf-8")) for n in names]


def _is_nav(name: str) -> bool:
    return name.endswith("nav.xhtml")


#: `href` / `src` 的属性值，单双引号都认：XML 声明那边是单引号，属性这边通常是双引号。
_HREF_RE = re.compile(r"""\b(?:href|src)\s*=\s*(["'])(.*?)\1""", re.IGNORECASE)


def parse_css(css: str) -> dict[str, dict[str, str]]:
    """CSS → `{选择器: {属性: 值}}`。

    注释先剥掉，免得 `/* 装饰符号宽度 */` 粘在上一条的值后面。`@font-face` 这类
    at-rule 当成一个选择器键返回，键是原样的 at  prelude。
    """
    stripped = re.sub(r"/\*.*?\*/", "", css, flags=re.DOTALL)
    out: dict[str, dict[str, str]] = {}
    for selector, body in re.findall(r"([^{}]+)\{([^{}]*)\}", stripped):
        decls = {}
        for decl in body.split(";"):
            prop, sep, value = decl.partition(":")
            if sep and prop.strip():
                decls[prop.strip()] = value.strip()
        # 一个规则组可能有多个选择器（`h1, h2, h3`），各自都能单独查到
        for one in (s.strip() for s in selector.split(",")):
            if one:
                out.setdefault(one, {}).update(decls)
    return out


def assert_heading(
    html: str, tag: str, text: str, class_name: str | None = None, has_id: bool = False
) -> None:
    """页里有这个标题，class / id 按需校验；失败时打出实际标签与整页。

    返回 `bool` 的 helper 只会说"不成立"，不说哪一处不成立——这里每条断言都带上
    实际拿到的属性串，失败信息能直接看出是 tag 不对、class 不对还是缺 id。
    """
    m = re.search(rf"<{tag}\b([^>]*)>\s*{re.escape(text)}\s*</{tag}>", html)
    assert m, f"页里没有 <{tag}>{text}</{tag}>；实际标题：{_headings(html)}；整页：\n{html}"
    attrs = m.group(1)
    if class_name is not None:
        found = re.search(r"""\bclass\s*=\s*["']([^"']*)["']""", attrs)
        assert found and class_name in found.group(1).split(), (
            f"<{tag}>{text}</{tag}> 的 class 不含 {class_name!r}，"
            f"实际：{found.group(1) if found else None!r}（属性串 {attrs!r}）"
        )
    if has_id:
        assert re.search(r"""\bid\s*=\s*["'][^"']+["']""", attrs), (
            f"<{tag}>{text}</{tag}> 缺 id，实际属性串：{attrs!r}"
        )


def _headings(html: str) -> list[str]:
    """页面里所有标题的标签+class+id+文本，失败信息里当目录用。"""
    out = []
    for m in re.finditer(r"<h([1-6])\b([^>]*)>(.*?)</h\1>", html, re.DOTALL):
        text = re.sub(r"<[^>]+>", "", m.group(3)).strip()
        out.append(f"h{m.group(1)} {m.group(2).strip()!r} {text!r}")
    return out
