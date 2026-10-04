"""界面读 core 默认值的唯一入口。

默认值的真源是 `core.config.DEFAULTS`，由 `core.options.option_default()` 取出。界面
一律走这里，**不手抄第二份字面量**——手抄的那份迟早和 core 走偏（对齐默认值就出过
一次：GUI 写死「居中」，core 改值时两边对不上）。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..core.options import OPTIONS, option_default
from .constants import ALIGN_LABELS

_OPTION_BY_NAME = {opt.name: opt for opt in OPTIONS}

#: core 对齐取值（left/center/right/justify）→ 菜单里的中文标签
_ALIGN_LABEL_BY_VALUE = {value: label for label, value in ALIGN_LABELS.items()}


def default_text(name: str, saved: Mapping[str, Any] | None = None) -> str:
    """某个选项的初始文本：存档里有就用存档值，否则 core 的默认值。

    `Config` 里可能是 int（如 `max_title_len`）、`None`（如 `cover`），统一转成字符串；
    `None` 当空串。未知选项名抛 `KeyError`。

    传 `saved`（配置文件内容）时优先取存档值——这是「启动时读配置」的入口；
    「恢复默认」要的是 core 默认值，调用时不传 `saved`。
    """
    if saved is not None and name in saved:
        value = saved[name]
        # None 在 Config 里表示「未显式指定」，等同于用核心默认；展示时
        # placeholder 也该回退到核心默认，否则框里什么都没有
        return default_text(name) if value is None else str(value)
    value = option_default(_OPTION_BY_NAME[name])
    return "" if value is None else str(value)


def default_align_label(name: str, saved: Mapping[str, Any] | None = None) -> str:
    """对齐菜单的初始中文标签：存档值非法时退回 core 默认值。

    菜单存中文、收集时换回 core 取值，所以默认值也要走中文这一侧，不能直接喂
    `center` 这种 core 取值。配置文件是用户可手改的，非法值不该让启动崩掉。
    """
    value = default_text(name, saved)
    if value not in _ALIGN_LABEL_BY_VALUE:
        value = default_text(name)
    return _ALIGN_LABEL_BY_VALUE[value]
