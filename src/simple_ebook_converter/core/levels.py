"""标题层级：把卷/章/节三条预设与额外层级规格合成 `Config.levels`。"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping

from .config import LEVEL_PRESETS, LevelRule, default_levels

#: 额外层级的统称，用于错误消息
_EXTRA = "额外层级"


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


def build_levels(patterns: Mapping[str, str], extra: Iterable[str] = ()) -> list[LevelRule]:
    """生成层级规则。`patterns` 的键是层级名（volume/chapter/section，同 `LEVEL_PRESETS`）：

    - 键缺失：沿用内置正则
    - 值为空串：不识别该层级
    - 其他值：覆盖内置正则

    `extra` 是 `级别:正则[:类名]` 规格，同级别覆盖预设，不同级别追加。
    """
    by_level = {rule.level: rule for rule in default_levels()}
    for level, name, label in LEVEL_PRESETS:
        if name not in patterns:
            continue
        pattern = patterns[name] or ""
        check_pattern(pattern, label)
        by_level[level].pattern = pattern
        by_level[level].class_name = name
    for spec in extra:
        level, pattern, class_name = parse_level_spec(spec)
        check_pattern(pattern, f"{_EXTRA} {level}")
        rule = by_level.get(level)
        if rule is None:
            by_level[level] = LevelRule(level, pattern, class_name)
        else:
            rule.pattern, rule.class_name = pattern, class_name
    return sorted(by_level.values(), key=lambda rule: rule.level)
