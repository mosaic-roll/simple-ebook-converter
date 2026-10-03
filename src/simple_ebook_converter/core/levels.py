"""标题层级：结构化规则（`LevelRule`）的校验与排序。

core 内部一律用 `LevelRule(level, pattern, class_name)` 三项说话——级别、class、
正则分开是本来该有的样子，合成一个 `hN[.class]:正则` 字符串再解析回来只是白折腾：
`options._level_rules()` 拼好字符串，`build_levels()` 立刻又把它拆回三项。

`hN[.class]:正则` 是 **CLI 的 `--level` 参数语法**，由 `cli._convert()` 调
`parse_level_spec()` 拆成 `LevelRule` 之后才进 core。GUI 那边本来就是三个输入框，
直接构造 `LevelRule`。
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from .config import LEVEL_PRESETS, LevelRule

#: 额外层级的统称，用于错误消息
_EXTRA = "额外层级"

#: 层级选择器：`h1`~`h6`，可选 `.class`（CSS 标识符）——只用于解析 CLI 的 `--level`
_SPEC_RE = re.compile(r"^h([1-6])(?:\.([A-Za-z_][A-Za-z0-9_-]*))?$")

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
    而排序稳定，所以同一级保持传入顺序：调用方把内置卷/章/节排在前面，它们就占着
    同级里的高优先级（`parse()` 照此顺序试，命中即止）。
    """
    checked = []
    for rule in rules:
        label = _PRESET_LABELS.get(rule.class_name) or f"{_EXTRA} h{rule.level}"
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
        raise ValueError(f"{_EXTRA}选择器应为 h1~h6[.class]，收到：{head!r}")
    return LevelRule(int(match.group(1)), pattern, match.group(2) or "")
