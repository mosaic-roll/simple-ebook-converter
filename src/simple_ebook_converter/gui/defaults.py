"""界面读 core 默认值的唯一入口。

默认值的真源是 `core.config.DEFAULTS`，由 `core.options.option_default()` 取出。界面
一律走这里，**不手抄第二份字面量**——手抄的那份迟早和 core 走偏（对齐默认值就出过
一次：GUI 写死「居中」，core 改值时两边对不上）。
"""

from __future__ import annotations

from ..core.options import OPTIONS, option_default
from .constants import ALIGN_LABELS

_OPTION_BY_NAME = {opt.name: opt for opt in OPTIONS}

#: core 对齐取值（left/center/right/justify）→ 菜单里的中文标签
_ALIGN_LABEL_BY_VALUE = {value: label for label, value in ALIGN_LABELS.items()}


def default_text(name: str) -> str:
    """core 里某个选项的默认值，转成输入框能直接显示的文本。

    `Config` 里可能是 int（如 `max_title_len`）、`None`（如 `cover`），统一转成字符串；
    `None` 当空串。未知选项名抛 `KeyError`。
    """
    value = option_default(_OPTION_BY_NAME[name])
    return "" if value is None else str(value)


def default_align_label(name: str) -> str:
    """core 的对齐默认值 → 选项菜单里的中文标签。

    菜单存中文、收集时换回 core 取值，所以默认值也要走中文这一侧，不能直接喂
    `center` 这种 core 取值。
    """
    return _ALIGN_LABEL_BY_VALUE[default_text(name)]
