"""标题层级：把 `级别:正则[:类名]` 规格合成 `Config.levels`。"""

from __future__ import annotations

import re
from collections.abc import Iterable

from .config import LEVEL_PRESETS, LevelRule, default_levels

#: 额外层级的统称，用于错误消息
_EXTRA = "额外层级"

#: 预设层级的 class 名 → 中文名，错误消息里指名道姓用
_PRESET_LABELS = {name: label for _level, name, label, _pattern in LEVEL_PRESETS}


def check_pattern(pattern: str, label: str) -> None:
    """只校验正则不保留编译结果——`parse()` 会把整批规则各编译一次。"""
    try:
        re.compile(pattern)
    except re.error as e:
        raise ValueError(f"{label}正则非法：{e}") from e


def parse_level_spec(spec: str) -> tuple[int, str, str]:
    """解析 `级别:正则[:类名]` → (级别, 正则, class 名)，出错抛 ValueError。"""
    level, sep, rest = spec.partition(":")
    if not sep or not rest:
        raise ValueError(f"{_EXTRA}格式应为 级别:正则[:类名]，收到：{spec}")
    try:
        level = int(level)
    except ValueError:
        raise ValueError(f"{_EXTRA}级别需为数字，收到：{level}") from None
    if not 1 <= level <= 6:
        raise ValueError(f"{_EXTRA}级别需在 1~6 之间，收到：{level}")
    pattern, _, class_name = rest.partition(":")
    return level, pattern, class_name or f"level{level}"


def build_levels(specs: Iterable[str] = ()) -> list[LevelRule]:
    """`级别:正则[:类名]` 规格列表 → 层级规则，按级别排序。

    未提及的层级保持内置值；空正则不启用该层级；同一级别后面的规格覆盖前面的。
    """
    by_level = {rule.level: rule for rule in default_levels()}
    for spec in specs:
        level, pattern, class_name = parse_level_spec(spec)
        check_pattern(pattern, _PRESET_LABELS.get(class_name) or f"{_EXTRA} {level}")
        if rule := by_level.get(level):
            rule.pattern, rule.class_name = pattern, class_name
        else:
            by_level[level] = LevelRule(level, pattern, class_name)
    return sorted(by_level.values(), key=lambda rule: rule.level)
