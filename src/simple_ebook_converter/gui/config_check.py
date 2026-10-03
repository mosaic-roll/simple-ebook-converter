"""GUI 落盘前的净化：非法值存成空，下一次启动用 core 默认。

关窗保存走的是 `_on_close`，那里只接 `OSError`——校验不能在那里抛。而生成那条路
（`build_config()` → `resolve()`）会把非法参数当参数错误报给用户。用户在一个框里
敲了 `abc` 就关窗，不该被弹窗拦下，也不该把 `abc` 写进配置文件、让之后每次生成都
失败。所以这一层只做一件事：**把不合法的值换成空的**，让 core 默认接管。

合法性问 core，不在这里重述一遍：`options.is_valid()` 就是「单个字段合不合法」的
入口，与生成那条路共用同一套规则（见 `core.options.is_valid`）。只有 GUI 自己的
两个字段例外——`css_source` / `css_mode` 不进 `Config`，core 根本不认识它们。

唯一不「静默」的地方是额外层级的正则：它非法时只清空正则、保留级别与 class，
因为那一行是用户刻意加的（空行也是状态，下次启动还在），把整行丢掉等于替用户
做了决定。
"""

from __future__ import annotations

from typing import Any

from ..core.config import LevelRule
from ..core.levels import is_valid_level
from ..core.options import CONFIG_KINDS, is_valid
from .tabs.layout import CSS_MODES, CSS_SOURCE_FILE, CSS_SOURCE_TEXT

#: GUI 自己的字段 → 合法取值。core 不认这两个名字，所以问不了 core。
_GUI_VALUES: dict[str, tuple[str, ...]] = {
    "css_source": (CSS_SOURCE_TEXT, CSS_SOURCE_FILE),
    "css_mode": tuple(CSS_MODES),
}


def accepts(name: str, value: Any) -> bool:
    """这一个值能不能存。`None`（= 用默认）一律能。

    先问 GUI 自己的取值表，再问 core：GUI 字段 core 不认，反过来 core 字段也不会
    出现在 GUI 表里，两边不会互相误判。
    """
    if value is None:
        return True
    allowed = _GUI_VALUES.get(name)
    if allowed is not None:
        return value in allowed
    return is_valid(name, value)


def as_stored(name: str, text: str | None) -> Any:
    """界面文本 → 落盘值。`int` 字段存数字，其余存字符串；不合法一律 `None`。

    按 `CONFIG_KINDS`（core 字段类型真源）判断是哪种，免得 JSON 里出现
    `"indent": "2"` 这种和 `Config` 类型不一致的写法。

    两层，与 core 那边一样不重叠：先按类型转（`"abc"` 转不成整数），再问值域
    （`-1` 是整数但缩进不能为负）。

    `text` 是 `None` 时直接存 `None`：调用方可能手上根本没有文本可取（控件值
    不在映射表里），那与「用户没填」是同一件事。
    """
    if text is None:
        return None
    if CONFIG_KINDS.get(name) is int:
        stripped = text.strip()
        if not stripped:
            return None
        try:
            value: Any = int(stripped)
        except ValueError:
            return None
    else:
        value = text.strip() or None
    return value if accepts(name, value) else None


def level_number(selector: str) -> int | None:
    """级别选择器 `h4` / `4` → `4`，填不出来返 `None`。

    用户可能不带 `h`，core 只收数字。返 `None` 而不是 `0`：`0` 是个看着合法的
    整数，混进规则里会变成一条永远匹配不上任何标题的死规则——不报错，只是静默
    不生效。存盘与生成两处都要用它，「填不出来」得是一个能直接判断的值。
    """
    try:
        return int(selector.strip().lstrip("hH"))
    except ValueError:
        return None


def extra_level(level: str, class_name: str, regex: str) -> dict[str, str]:
    """一行额外层级 → 落盘值。整行照原样存（级别/class/正则都是文本）。

    正则非法或级别填不出来时把正则清空：留着级别与 class，用户下次打开还能看见
    自己加过什么、只改正则就行。整行丢掉是替用户做决定。
    """
    level, class_name, regex = level.strip(), class_name.strip(), regex.strip()
    number = level_number(level)
    if number is None or not is_valid_level(LevelRule(number, regex, class_name)):
        return {"level": level, "class": class_name, "regex": ""}
    return {"level": level, "class": class_name, "regex": regex}
