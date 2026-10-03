"""文本读取与编码识别。"""

from __future__ import annotations

import codecs
from pathlib import Path

import chardet

#: 自动探测时按顺序尝试的候选编码，顺序即偏好：简中 > 繁中 > 日文
FALLBACK_ENCODINGS = ("utf-8", "gb18030", "big5", "cp932", "euc_jp")

AUTO_ENCODING = "auto"

#: 编码下拉框的可选值 = auto + 全部候选
ENCODING_CHOICES = (AUTO_ENCODING, *FALLBACK_ENCODINGS)

_BOMS = (
    (b"\xef\xbb\xbf", "utf-8-sig"),
    (b"\xff\xfe", "utf-16-le"),
    (b"\xfe\xff", "utf-16-be"),
)


class EncodingError(Exception):
    """指定的编码解不了这个文件。"""


def decode(raw: bytes, encoding: str = AUTO_ENCODING) -> tuple[str, str]:
    """解码字节，返回 (文本, 实际编码名)。空编码名等同 auto。"""
    if encoding and encoding.lower() != AUTO_ENCODING:
        try:
            return raw.decode(encoding), codecs.lookup(encoding).name
        except (UnicodeDecodeError, LookupError) as exc:
            raise EncodingError(f"无法用编码 {encoding} 解码") from exc
    for bom, enc in _BOMS:
        if raw.startswith(bom):
            # 砍掉自己认出的那段 BOM；utf-16 解码还会再吐出一个 U+FEFF，一并去掉
            return raw[len(bom) :].decode(enc).lstrip("\ufeff"), enc
    guess = chardet.detect(raw)
    guessed = str(guess["encoding"]) if guess and guess.get("encoding") else ""
    for enc in (guessed, *FALLBACK_ENCODINGS):
        if not enc:
            continue
        try:
            return raw.decode(enc), _canonical(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("utf-8", errors="replace"), "utf-8(replace)"


def _canonical(encoding: str) -> str:
    """把 chardet 报的名字（GB18030、EUC-JP…）换成 Python 的规范写法。

    报出来的名字要能直接填回 `--encoding`，所以只认 `ENCODING_CHOICES` 里那套写法。
    """
    try:
        return codecs.lookup(encoding).name
    except LookupError:
        return encoding


def lines_from_bytes(
    raw: bytes, encoding: str = AUTO_ENCODING
) -> tuple[list[str], str]:
    """把字节解码并按行切分，返回 (行, 实际编码名)。`read_lines()` 的纯孪生。"""
    text, used = decode(raw, encoding)
    return text.splitlines(), used


def read_lines(
    path: Path | str, encoding: str = AUTO_ENCODING
) -> tuple[list[str], str]:
    """读取文本文件并按行切分，返回 (行, 实际编码名)。"""
    return lines_from_bytes(Path(path).read_bytes(), encoding)
