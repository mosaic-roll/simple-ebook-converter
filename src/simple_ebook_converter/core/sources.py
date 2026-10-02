"""前端预加载的资源内容：core 只消费内容，不读 `Config` 上的路径字段。

`Config` 里的 `css_file` / `css_append` / `font` / `cover` / `toc_file` 是**选项解析的
落点**——`options.build_config()` 得有个地方放 CLI 给的路径。它们的唯一消费者是本模块
的 `load_sources()`；转换流程（`pipeline` / `builder`）一次都不看。

GUI 不调 `load_sources()`：它的资源来自内存里的表单（CSS 文本框内容、目录面板条目），
自己构造 `Sources` 即可。两边共用本模块的 `font_resource()` / `cover_resource()` /
`read_text()` / `cover_for()`，所以「读文件 + 转可读 ValueError + 校验格式」与
「封面的优先级判断」都只有这一份实现——GUI 不自己写一遍封面发现逻辑。

单独成模块而不是放进 `pipeline`：`pipeline` 依赖 `builder`，`Sources` 若定义在
`pipeline` 里，`builder` 反过来导入它就会成环。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .config import Config
from .mediatypes import cover_media_type, font_media_type, sniff_image
from .toc import load_toc


@dataclass(frozen=True)
class Resource:
    """一份内嵌资源的**内容**。

    `name` 是文件名（不含目录）；写进 manifest 的路径由调用方按 `fonts/` / `images/`
    拼。`media_type` 在构造时就算好——调用方不必再拿路径问一次类型，
    也就不会出现「内容读到了、类型猜错了」这种半途状态。
    """

    name: str
    data: bytes
    media_type: str


@dataclass(frozen=True)
class Sources:
    """一次转换要用的全部预加载内容。构造后视为不可变。

    - `toc_entries`：扁平条目列表（同 `toc.to_json` 形态）。给了就跳过标题正则
    - `css_text`：整份**替代**内置样式的 CSS 文本
    - `css_append_text`：**追加**在内置样式之后的 CSS 文本
    - `font` / `cover`：内嵌资源的内容

    两个 CSS 字段互斥（与 `Config.css_file` / `css_append` 同一约束）。
    `Config.validate()` 只能管 CLI 那侧（GUI 恒为 `None`，它压根不碰），
    所以互斥在这里由 `__post_init__` 兜住，不靠前端自觉。
    """

    toc_entries: list[dict] | None = None
    css_text: str | None = None
    css_append_text: str | None = None
    font: Resource | None = None
    cover: Resource | None = None

    def __post_init__(self) -> None:
        if self.css_text is not None and self.css_append_text is not None:
            raise ValueError(
                "整份替代内置样式（css_text）与追加在内置样式之后（css_append_text）互斥"
            )


def font_resource(path: str | Path) -> Resource:
    """字体文件 → `Resource`。扩展名不认识、或读不出字节，就在这里报错。

    先认扩展名再读：实参是从左到右求值的，反过来写会先白读一遍字节，
    而且 `foo.xyz` 不存在时报的是"无法读取字体"而不是更贴切的"不支持的字体格式"。
    """
    path = Path(path)
    media_type = font_media_type(path)
    return Resource(path.name, _read_bytes(path, "字体"), media_type)


def cover_resource(path: str | Path) -> Resource:
    """封面图 → `Resource`。扩展名不认识、或读不出字节，就在这里报错。

    同 `font_resource`：先认扩展名再读字节（`foo.xyz` 报"格式不对"而不是"读不出"）。

    读完再用字节头复核一遍。扩展名对不上实际内容时，按实际格式写包内的文件名和
    media-type——两处都抄扩展名的话，epubcheck 会报 OPF-029 加 PKG-022。用户磁盘上
    那个文件不动，只改 EPUB 里叫什么。
    """
    path = Path(path)
    declared = cover_media_type(path)
    data = _read_bytes(path, "封面图")
    sniffed = sniff_image(data)
    if sniffed is None or sniffed[0] == declared:
        return Resource(path.name, data, declared)
    media_type, suffix = sniffed
    return Resource(path.with_suffix(suffix).name, data, media_type)


def read_text(path: str | Path, label: str = "文件") -> str:
    """读文本资源（UTF-8），读不了转可读的 `ValueError`。GUI 读外部 CSS 也走这里。"""
    try:
        return Path(path).read_text(encoding="utf-8")
    except OSError as e:
        raise ValueError(f"无法读取{label}：{e}") from e


def cover_for(
    explicit: str | Path | None,
    input_path: str | Path | None = None,
    text_cover: bool = True,
) -> Resource | None:
    """封面内容：显式给的路径优先，否则返回 `None` 由调用方处理。

    自动发现封面图片（同目录恰好一张 `cover.*`）只在「打开输入文件」时由
    GUI 调 `find_cover()` 预填路径；生成阶段只认显式给出的路径。
    两个前端共用：CLI 传 `cfg.cover` / `cfg.input` / `cfg.text_cover`，
    GUI 传封面输入框与输入输入框的内容及 `text_cover` 勾选项。
    """
    if explicit:
        return cover_resource(explicit)
    return None


def load_sources(cfg: Config) -> Sources:
    """把 `Config` 上的资源路径字段读成内容。**CLI 用**；GUI 从表单直接构造。

    封面走 `cover_for()`，与 GUI 同一个函数——两个前端的封面优先级必须一致，
    这里的「显式路径 / 同目录自动发现」判断只有这一份。
    """
    return Sources(
        toc_entries=load_toc(cfg.toc_file) if cfg.toc_file is not None else None,
        css_text=read_text(cfg.css_file, "外部 CSS") if cfg.css_file else None,
        css_append_text=(
            read_text(cfg.css_append, "附加 CSS") if cfg.css_append else None
        ),
        font=font_resource(cfg.font) if cfg.font else None,
        cover=cover_for(cfg.cover, cfg.input, cfg.text_cover),
    )


def _read_bytes(path: Path, label: str) -> bytes:
    try:
        return path.read_bytes()
    except OSError as e:
        raise ValueError(f"无法读取{label}：{e}") from e
