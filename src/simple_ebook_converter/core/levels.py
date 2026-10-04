"""标题层级：结构化规则（`LevelRule`）的校验与排序。

core 内部一律用 `LevelRule(level, pattern, class_name)` 三项说话——级别、class、
正则分开是本来该有的样子，合成一个 `hN[.class]:正则` 字符串再解析回来只是白折腾。

`hN[.class]:正则` 是 **CLI 的 `--level` 参数语法**，由 `cli._convert()` 调
`parse_level_spec()` 拆成 `LevelRule` 之后才进 core。GUI 那边本来就是三个输入框，
直接构造 `LevelRule`。

所以校验也在这条入口上：`build_rules()` 是所有调用方（`options._level_rules()` 与
core 的直接调用者）共用的那道关，它查级别范围与正则；`is_valid_level()` 只是把
同一处的 `ValueError` 翻成布尔，给 GUI 存盘前问一句真假。
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from .config import LEVEL_PRESETS, LevelRule

#: 额外层级的统称，用于错误消息
_EXTRA = "额外层级"

#: 级别取值范围：`h1`~`h6`，与 CSS 标题层级一致。CLI 的选择器正则与结构化规则的
#: 范围检查共用这一份——同一个事实不该在一个文件里写两遍。
_LEVEL_MIN, _LEVEL_MAX = 1, 6

#: 层级选择器：`h1`~`h6`，可选 `.class`（CSS 标识符）——只用于解析 CLI 的 `--level`
_SPEC_RE = re.compile(
    rf"^h([{_LEVEL_MIN}-{_LEVEL_MAX}])(?:\.([A-Za-z_][A-Za-z0-9_-]*))?$"
)

#: 预设层级的 class 名 → 中文名，错误消息里指名道姓用
_PRESET_LABELS = {name: label for _level, name, label, _pattern in LEVEL_PRESETS}


def check_pattern(pattern: str, label: str) -> None:
    """只校验正则不保留编译结果——`parse()` 会把整批规则各编译一次。"""
    try:
        re.compile(pattern)
    except re.error as e:
        raise ValueError(f"{label}正则非法：{e}") from e


def build_rules(rules: Iterable[LevelRule] = ()) -> list[LevelRule]:
    """层级规则 → 校验过的、按级别排序的规则列表。

    每条规则就是一条独立规则，没有「后写的顶掉先写的」这回事——同 class 也可以有多条，
    按书写顺序排下去（正则难写就拆成几条，一行没命中的交给下一行）。排序键只有级别，
    而排序稳定，所以同一级保持传入顺序：调用方把内置卷/章排在前面，它们就占着
    同级里的高优先级（`parse()` 照此顺序试，命中即止）。

    级别要在这里查，不能只靠 `parse_level_spec()`：那是 CLI 的入口，GUI 直接构造
    `LevelRule`，core 的调用方也可能是任何一段代码。不查的话 `h7` 或者级别框里
    填坏的 `0` 会变成一条**永远匹配不上**的规则——不报错，只是静默不生效。
    """
    checked = []
    for rule in rules:
        label = _PRESET_LABELS.get(rule.class_name) or f"{_EXTRA} h{rule.level}"
        if not _LEVEL_MIN <= rule.level <= _LEVEL_MAX:
            raise ValueError(
                f"{_EXTRA}级别需在 {_LEVEL_MIN}~{_LEVEL_MAX} 之间，收到：{rule.level}"
            )
        check_pattern(rule.pattern, label)
        checked.append(rule)
    return sorted(checked, key=lambda rule: rule.level)


def is_valid_level(rule: LevelRule) -> bool:
    """单条层级规则能不能用——给 GUI 存盘前查。

    与 `build_rules()` 同一条路，只是把 `ValueError` 翻译成布尔，省得调用方写
    try/except 只为问一句真假。
    """
    try:
        build_rules([rule])
    except ValueError:
        return False
    return True


def parse_level_spec(spec: str) -> LevelRule:
    """**CLI 专用**：`--level hN[.class]:正则` → `LevelRule`，出错抛 `ValueError`。

    `hN` 是级别 `h1`~`h6`，与 CSS 选择器一致；`.class` 可省略（省略即不给该标题加
    class）；冒号后整段都是正则，所以正则里可以有 `:`，不必转义。

    这个字符串格式是命令行参数的样子，不是 core 的内部表示——两个前端都不该拿它
    传数据，见模块 docstring。
    """
    head, sep, pattern = spec.partition(":")
    if not sep:
        raise ValueError(f"{_EXTRA}格式应为 hN[.class]:正则，收到：{spec!r}")
    match = _SPEC_RE.match(head.strip())
    if match is None:
        raise ValueError(
            f"{_EXTRA}选择器应为 h{_LEVEL_MIN}~h{_LEVEL_MAX}[.class]，收到：{head!r}"
        )
    return LevelRule(int(match.group(1)), pattern, match.group(2) or "")
