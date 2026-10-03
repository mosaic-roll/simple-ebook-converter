"""取值校验：单字段的值域 + 整份配置的跨字段约束。

**校验规则只有一份。** 单字段的值域拆成纯函数登记在 `_CHECKS` 表里，
`validate_config()` 遍历它（整份配置），`field_error()` 只查一个（GUI 存盘时手里
只有单个字段的原始值）。两个入口共用同一张表，所以存盘与生成的合法性判定不会漂移。

**为什么校验不住在 `config.py` 里。** `config` 讲的是「配置长什么样」——字段、默认值、
取值集合；这里讲的是「配置合不合法」。两者是独立的关注点。证据很直接：`_check_*` 里
没有一个引用 `Config`，它们只用到值域常量（`ALIGN_CHOICES` / `FORMATS`）与标准库。
所以 `validation` 单向依赖 `config`，而 `config` 不知道 `validation` 存在——依赖方向
是直的，不需要在调用方做延迟导入来回避一个环。

按**约束**拆检查，不按字段拆：三个 align 是同一条约束，用一个 `_align_check(label)`
构造器，不必写三遍。每个检查住在它约束的真源旁边——值域常量在 `config`，扩展名表在
`mediatypes`（`_media_check` 只是把已在抛的 `ValueError` 收成 `str | None`）。
"""

from __future__ import annotations

import codecs
import re
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from .config import ALIGN_CHOICES, FORMATS, Config
from .encoding import AUTO_ENCODING
from .mediatypes import cover_media_type, font_media_type

# 每个检查是一个纯函数：合法返回 None，非法返回可直接展示的说明。


def _check_encoding(value: str) -> str | None:
    # `auto` 跳过；空串在 `decode` 里也当 auto，所以这里只判 `auto` 本身
    if not value or value.lower() == AUTO_ENCODING:
        return None
    try:
        codecs.lookup(value)
    except LookupError:
        return (
            f"未知编码：{value}（要填 Python 的 codec 名，如 utf-8 / gb18030 / cp932）"
        )
    return None


def _check_max_title_len(value: int) -> str | None:
    return None if value >= 1 else f"标题最大字数需为正整数，收到：{value}"


def _check_toc_depth(value: int) -> str | None:
    return None if 1 <= value <= 6 else f"目录深度需在 1~6 之间，收到：{value}"


def _check_toc_format(value: str) -> str | None:
    if value in FORMATS:
        return None
    return f"目录格式只能是 {'/'.join(FORMATS)}，收到：{value}"


def _check_indent(value: int) -> str | None:
    return None if value >= 0 else f"段落缩进字数不能为负，收到：{value}"


def _check_exclude(value: str) -> str | None:
    """`exclude` 是唯一直接躺在 `Config` 上的正则字段。

    卷/章走 `levels.build_rules()`、替换规则走 `replace.replacers_by_stage()`，都在各自
    的入口编译校验，只有这条曾经没人管——非法正则一路留到 `parser.parse()` 才炸，而
    `re.error` 不是 `ValueError`，GUI 的 `except ValueError` 接不住。
    """
    if not value:
        return None
    try:
        re.compile(value)
    except re.error as e:
        return f"排除规则正则非法：{value}（{e}）"
    return None


def _align_check(label: str) -> Callable[[str], str | None]:
    def check(value: str) -> str | None:
        if value in ALIGN_CHOICES:
            return None
        return f"{label}只能是 {'/'.join(ALIGN_CHOICES)}，收到：{value}"

    return check


def _check_date(value: str | None) -> str | None:
    if not value:
        return None
    try:
        datetime.fromisoformat(value)
    except ValueError:
        return f"日期格式错误：{value}（应为 YYYY-MM-DD 或 YYYY-MM-DD HH:MM[:SS]）"
    return None


def _media_check(check: Callable[[Path], Any]) -> Callable[[Path | None], str | None]:
    """`mediatypes` 那两个已经是「非法就抛」的检查，这里只把异常收成消息。"""

    def run(value: Path | None) -> str | None:
        if not value:
            return None
        try:
            check(Path(value))
        except ValueError as e:
            return str(e)
        return None

    return run


#: 字段名 → 单字段校验函数。**插入顺序就是校验顺序**，第一个错先冒出来。
#:
#: 这张表是「哪些字段有值域约束」的唯一真源：加字段只需写 `_check_xxx` 再插一条，
#: `validate_config()` 不用动。跨字段约束不在这里——见 `_CROSS_CHECKS`。
_CHECKS: dict[str, Callable[[Any], str | None]] = {
    "encoding": _check_encoding,
    "max_title_len": _check_max_title_len,
    "toc_depth": _check_toc_depth,
    "toc_format": _check_toc_format,
    "indent": _check_indent,
    "exclude": _check_exclude,
    "chapter_align": _align_check("章对齐"),
    "volume_align": _align_check("卷对齐"),
    "para_align": _align_check("正文对齐"),
    "date": _check_date,
    # 扩展名只做快检：`sources.font_resource` / `cover_resource` 读字节时还会再调一遍
    # 同样两个函数。保留它，是因为用户可能想在加载资源、解析输入之前就看到"字体格式
    # 不对"，而不是先等半天读文件才报同一件事。
    "font": _media_check(font_media_type),
    "cover": _media_check(cover_media_type),
}

#: 跨字段约束：接收整份 `Config`，合法返回 None，非法返回消息。
#:
#: 现在只有 `css_file` 与 `css_append` 互斥一条。它依赖两个字段同时存在，**没有归属的
#: 字段**，所以不进 `_CHECKS`——那张表的键是字段名，跨字段规则挂不上去。
#:
#: 加第二条时往这个元组里 `+` 一项即可，不用回头改 `validate_config()`。判断依据始终
#: 是那句：这个约束依赖别的字段吗？依赖就进这里，不依赖就进 `_CHECKS`。
_CROSS_CHECKS: tuple[Callable[[Config], str | None], ...] = (
    lambda c: (
        "--css-file 与 --css-append 互斥：前者替代内置样式，后者追加在内置样式之后"
        if c.css_file and c.css_append
        else None
    ),
)


def field_error(name: str, value: Any) -> str | None:
    """单个字段的值域是否合法。合法返回 None，否则返回可直接展示的说明。

    `validate_config()` 遍历 `_CHECKS` 查全部字段；`options.is_valid()` 只查一个——
    GUI 存盘时手里只有单个字段的原始值，需要的正是这条单字段入口。

    收的是**已类型化**的值（`int` / `Path` / `str`），不是前端原始文本；类型那一层由
    `options._convert()` 管。两者不重叠。

    「已类型化」是**约定不是强制**：签名故意留在 `Any` 上（`_CHECKS` 里那些检查要接
    `int` / `Path` / `str` 三种类型，标窄了就要一堆 cast），签名再准也拦不住调用方
    传错类型——`field_error("encoding", 123)` 该崩还是崩（`123.lower()` 没有）。
    真要防就在 `_CHECKS` 那一层统一包 `try`，代价是稀释每个检查自己的责任，不值。
    约定的测试在 `tests/core/test_validation.py`。
    """
    check = _CHECKS.get(name)
    return check(value) if check else None


def validate_config(cfg: Config) -> None:
    """校验整份配置，非法抛 `ValueError`（消息可直接展示给用户）。

    `pipeline.resolve()` 会自动调它，所以两个前端不必各自记得校验；直接调
    `build_epub()` 的调用方应自己先过一遍。

    这里只做调度：先遍历 `_CHECKS` 查单字段的值域，再走 `_CROSS_CHECKS` 查跨字段的。
    任何一条检查逻辑都不该留在这个函数里。
    """
    for name, check in _CHECKS.items():
        error = check(getattr(cfg, name))
        if error is not None:
            raise ValueError(error)
    for cross in _CROSS_CHECKS:
        error = cross(cfg)
        if error is not None:
            raise ValueError(error)