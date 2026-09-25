from __future__ import annotations

import re

from .config import LevelRule, default_levels

_PRESET_OPTIONS = {2: "--volume", 3: "--chapter", 4: "--section"}


def compile_pattern(pattern: str, source: str) -> re.Pattern[str]:
    """编译用户提供的正则，非法时抛 ValueError（CLI/GUI 共用，转成友好报错）。"""
    try:
        return re.compile(pattern)
    except re.error as e:
        raise ValueError(f"{source} 正则非法：{e}") from e


def parse_level_spec(spec: str) -> tuple[int, str, str]:
    """解析 `级别:正则[:类名]`，出错抛 ValueError。"""
    parts = spec.split(":", 2)
    if len(parts) < 2:
        raise ValueError(f"--level 格式应为 级别:正则[:类名]，收到：{spec}")
    try:
        level = int(parts[0])
    except ValueError:
        raise ValueError(f"--level 级别必须是数字，收到：{parts[0]}")
    if not 1 <= level <= 6:
        raise ValueError(f"--level 级别需在 1~6 之间，收到：{level}")
    class_name = parts[2] if len(parts) > 2 else f"level{level}"
    return level, parts[1], class_name


def build_levels(
    volume: str | None,
    chapter: str | None,
    section: str | None,
    extra: tuple[str, ...] = (),
) -> list[LevelRule]:
    """按 preset（卷/章/节）与 extra 规格生成层级规则。CLI 与 GUI 共用。"""
    levels = default_levels()
    presets = {2: ("volume", volume), 3: ("chapter", chapter), 4: ("section", section)}
    for level, (class_name, pat) in presets.items():
        if pat is not None:
            compile_pattern(pat, _PRESET_OPTIONS[level])
            for r in levels:
                if r.level == level:
                    r.pattern = pat
                    r.class_name = class_name
    for spec in extra:
        level, pattern, class_name = parse_level_spec(spec)
        compile_pattern(pattern, f"--level {spec}")
        for r in levels:
            if r.level == level:
                r.pattern = pattern
                r.class_name = class_name
                break
        else:
            levels.append(LevelRule(level, pattern, class_name))
    return levels