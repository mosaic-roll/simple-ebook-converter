"""资源扩展名 → MIME 类型。独立的叶子模块：只依赖 pathlib，便于 core 内部各处复用。

把格式判定从 builder 里抽出来，是为了让 `Config.validate()` 能在真正读文件之前就
拒掉不认识的格式——CLI 与 GUI 因此拿到同一套校验，不必各自预检。
"""

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
    """字体格式不认识就抛 ValueError，由调用方转成前端友好的报错。"""
    mt = FONT_TYPES.get(path.suffix.lower())
    if mt is None:
        supported = "/".join(s.lstrip(".") for s in FONT_TYPES)
        raise ValueError(f"不支持的字体格式：{path.name}（仅支持 {supported}）")
    return mt


def cover_media_type(path: Path) -> str:
    """封面图格式不认识就抛 ValueError。

    过去这里是 `COVER_TYPES.get(suffix, "image/jpeg")`，也就是把 .txt 之类的
    未知后缀悄悄当 jpeg 塞进 EPUB；现在与字体一样显式报错。
    """
    mt = COVER_TYPES.get(path.suffix.lower())
    if mt is None:
        supported = "/".join(s.lstrip(".") for s in COVER_TYPES)
        raise ValueError(f"不支持的封面图格式：{path.name}（仅支持 {supported}）")
    return mt


def find_cover(input_path: Path) -> Path | None:
    """在输入文件同目录找一张名为 `cover` 的图片，找不到或不唯一就返回 None。

    不指定 `--cover` 时的便利行为：只认扩展名在 `COVER_TYPES` 里的 `cover.*`
    （大小写不敏感），并且**恰好一个**才采用——命中多个说明作者没拿准，
    静默挑一张反而会咬人。
    """
    try:
        entries = sorted(input_path.parent.iterdir())
    except OSError:
        return None
    hits = [
        p
        for p in entries
        if p.is_file() and p.stem.lower() == "cover" and p.suffix.lower() in COVER_TYPES
    ]
    return hits[0] if len(hits) == 1 else None

