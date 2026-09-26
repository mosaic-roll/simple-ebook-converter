"""资源扩展名 → MIME 类型，以及封面的自动发现。"""

from __future__ import annotations

from pathlib import Path

FONT_TYPES = {
    ".ttf": "font/ttf",
    ".otf": "font/otf",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
}

COVER_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".svg": "image/svg+xml",
    ".webp": "image/webp",
    ".avif": "image/avif",
}


def font_media_type(path: Path) -> str:
    """字体格式不认识就抛 ValueError，交给调用方转成前端友好的报错。"""
    return _media_type(path, FONT_TYPES, "字体")


def cover_media_type(path: Path) -> str:
    """封面图格式不认识就抛 ValueError。

    不用标准库 `mimetypes`：它不认 `.webp`/`.avif`，猜不出就会在 manifest 里写出空的
    media-type。
    """
    return _media_type(path, COVER_TYPES, "封面图")


def _media_type(path: Path, table: dict[str, str], label: str) -> str:
    media = table.get(path.suffix.lower())
    if media is None:
        supported = "/".join(suffix.lstrip(".") for suffix in table)
        raise ValueError(f"不支持的{label}格式：{path.name}（仅支持 {supported}）")
    return media


def find_cover(input_path: Path) -> Path | None:
    """在输入文件同目录找一张名为 `cover` 的图片，不唯一或没有就返回 None。

    扩展名取 `COVER_TYPES` 全集，大小写不敏感。命中多张说明作者没拿准，静默挑一张
    反而会咬人，所以不猜。
    """
    try:
        entries = list(input_path.parent.iterdir())
    except OSError:
        return None
    hits = [
        path
        for path in entries
        if path.is_file() and path.stem.lower() == "cover" and path.suffix.lower() in COVER_TYPES
    ]
    return hits[0] if len(hits) == 1 else None
