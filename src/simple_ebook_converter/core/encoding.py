from __future__ import annotations

from pathlib import Path

import chardet

_BOMS = (
    (b"\xef\xbb\xbf", "utf-8-sig"),
    (b"\xff\xfe", "utf-16-le"),
    (b"\xfe\xff", "utf-16-be"),
)

#: 自动探测时的候选编码顺序（加编码只改这里一处）
FALLBACK_ENCODINGS = ("utf-8", "gb18030", "big5", "cp932", "euc_jp")
AUTO_ENCODING = "auto"
#: `-e/--encoding` 的完整可选值：auto 加上全部候选
ENCODING_CHOICES = (AUTO_ENCODING, *FALLBACK_ENCODINGS)


class EncodingError(Exception):
    pass


def decode(raw: bytes, encoding: str = AUTO_ENCODING) -> tuple[str, str]:
    """解码字节，返回 (文本, 实际编码名)。"""
    if encoding and encoding.lower() != AUTO_ENCODING:
        try:
            return raw.decode(encoding), encoding
        except (UnicodeDecodeError, LookupError) as exc:
            raise EncodingError(f"无法用编码 {encoding} 解码") from exc
    for bom, enc in _BOMS:
        if raw.startswith(bom):
            if enc.startswith("utf-16"):
                text = raw[len(bom) :].decode(enc)
                if text.startswith("\ufeff"):
                    text = text[1:]
            else:
                text = raw[len(bom) :].decode(enc)
            return text, enc
    guess = chardet.detect(raw)
    guessed = None
    if guess and guess.get("encoding"):
        guessed = str(guess["encoding"]).lower()
    for enc in [guessed, *FALLBACK_ENCODINGS]:
        if not enc:
            continue
        try:
            return raw.decode(enc), enc
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("utf-8", errors="replace"), "utf-8(replace)"


def read_lines(path: Path | str, encoding: str = AUTO_ENCODING) -> tuple[list[str], str]:
    """读取文本文件并按行切分，返回 (行, 实际编码名)。"""
    text, used = decode(Path(path).read_bytes(), encoding)
    return text.splitlines(), used
