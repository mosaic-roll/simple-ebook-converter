"""标题层级：把 `hN[.class]:正则` 规格合成 `Config.levels`。

选择器与 CSS 一致：`hN` 是级别，`.class` 可省略（省略即不给该标题加 class）；冒号后
整段都是正则，所以正则里可以有 `:`，不必转义。
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from .config import LEVEL_PRESETS, LevelRule, default_levels

#: 额外层级的统称，用于错误消息
_EXTRA = "额外层级"

#: 层级选择器：`h1`~`h6`，可选 `.class`（CSS 标识符）
_SPEC_RE = re.compile(r"^h([1-6])(?:\.([A-Za-z_][A-Za-z0-9_-]*))?$")

#: 预设层级的 class 名 → 中文名，错误消息里指名道姓用
_PRESET_LABELS = {name: label for _level, name, label, _pattern in LEVEL_PRESETS}


def check_pattern(pattern: str, label: str) -> None:
    """只校验正则不保留编译结果——`parse()` 会把整批规则各编译一次。"""
    try:
        re.compile(pattern)
    except re.error as e:
        raise ValueError(f"{label}正则非法：{e}") from e


def parse_level_spec(spec: str) -> tuple[int, str, str]:
    """解析 `hN[.class]:正则` → (级别, 正则, class 名)，出错抛 ValueError。

    `class` 省略时返回空串（标题不加 class）。冒号后整段都是正则，可含 `:`。
    """
    head, sep, pattern = spec.partition(":")
    if not sep:
        raise ValueError(f"{_EXTRA}格式应为 hN[.class]:正则，收到：{spec!r}")
    match = _SPEC_RE.match(head.strip())
    if match is None:
        raise ValueError(f"{_EXTRA}选择器应为 h1~h6[.class]，收到：{head!r}")
    return int(match.group(1)), pattern, match.group(2) or ""


def build_levels(specs: Iterable[str] = ()) -> list[LevelRule]:
    """`hN[.class]:正则` 规格列表 → 层级规则，按级别排序。

    未提及的层级保持内置值；空正则不启用该层级；同一级别后面的规格覆盖前面的。
    """
    by_level = {rule.level: rule for rule in default_levels()}
    for spec in specs:
        level, pattern, class_name = parse_level_spec(spec)
        check_pattern(pattern, _PRESET_LABELS.get(class_name) or f"{_EXTRA} h{level}")
        if rule := by_level.get(level):
            rule.pattern, rule.class_name = pattern, class_name
        else:
            by_level[level] = LevelRule(level, pattern, class_name)
    return sorted(by_level.values(), key=lambda rule: rule.level)
