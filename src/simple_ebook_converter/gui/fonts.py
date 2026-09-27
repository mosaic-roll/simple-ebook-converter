"""字体解析：把「想要的字体名」变成「这台机器上真实存在的字体元组」。

Tk 在字体不存在时**静默回退**、不报错，表现是「等宽字体没等宽」「中文变方块」，
很难一眼看出原因。所以在 `theme.apply()` 之前把要用的字体全部查一遍、缓存起来，
后面各处只读 `font()`。

字号一律用**正数（磅）**：负数字号表示像素，不随 `tk scaling` 缩放，高 DPI 下不变大。
"""

from __future__ import annotations

import tkinter as tk
import tkinter.font as tkfont

#: 界面字体与等宽字体的首选名，以及各自的回退链
UI_FONT = "Segoe UI"
MONO_FONT = "Consolas"
UI_SIZE = 10

#: 首选名查不到时按顺序试。键是上一环的名字，值是下一环（`None` = 到此为止）
FALLBACKS: dict[str, str | None] = {
    "Segoe UI": "Microsoft YaHei UI",   # Windows 中文回退
    "Microsoft YaHei UI": "Noto Sans CJK SC",
    "Noto Sans CJK SC": "SimHei",
    "SimHei": "PingFang SC",            # macOS
    "PingFang SC": "DejaVu Sans",
    "Consolas": "Cascadia Mono",         # Windows 新版等宽
    "Cascadia Mono": "Menlo",           # macOS 等宽
    "Menlo": "DejaVu Sans Mono",
    "DejaVu Sans Mono": "Courier New",
    "Courier New": "Liberation Mono",
}

#: (family, size, weight) → 字体元组。由 `bind_fonts()` 填，之后各处只读
_RESOLVED: dict[tuple[str, int, str], tuple] = {}

#: 启动时解析出来的实际族名，状态栏/排查用。键是首选名
_ACTUAL: dict[str, str] = {}


def _walk_family(family: str, available: set[str]) -> str:
    """沿回退链走到底，返回第一个真实存在的族名；全都不存在就返回原始首选名。"""
    seen: set[str] = set()
    current = family
    while current not in available and current not in seen:
        seen.add(current)
        nxt = FALLBACKS.get(current)
        if not nxt:
            break
        current = nxt
    return current if current in available else family


def _resolve(root: tk.Misc, family: str, size: int, weight: str) -> tuple:
    """解析一个字体规格 → Tk 字体元组（带缓存）。查不到就用 Tk 的默认字体兜。"""
    key = (family, size, weight)
    if key in _RESOLVED:
        return _RESOLVED[key]

    try:
        available = set(tkfont.families(root))
    except tk.TclError:
        available = set()
    actual = _walk_family(family, available) if available else family
    _ACTUAL[family] = actual

    try:
        # named font 不能配 size/weight，所以这里只用元组形式。
        value: tuple = (actual, size, weight) if weight else (actual, size)
        tkfont.Font(root=root, font=value)  # 试建一次：字体名不合法会抛 TclError
    except tk.TclError:
        value = (tkfont.nametofont("TkDefaultFont", root=root).actual("family"), size)
    _RESOLVED[key] = value
    return value


def bind_fonts(root: tk.Misc) -> None:
    """启动时调一次（**必须在 `theme.apply()` 之前**）。把要用的字体全部解析好。

    把普通与粗体两个字重都预热，因为 `theme.apply()` 里的标题样式会用粗体。
    """
    for family in (UI_FONT, MONO_FONT):
        _resolve(root, family, UI_SIZE, "")
        _resolve(root, family, UI_SIZE, "bold")


def font(family: str, size: int = UI_SIZE, weight: str = "") -> tuple | None:
    """取 `bind_fonts()` 解析好的字体元组；没绑过或字号不在预热范围里返回 `None`。

    返回 `None` 是**故意**的：让调用方能把「没绑字体」和「拿到一个 None 字体元组」
    区分开 —— 后者会让 Tk 画出一片空白，而前者至少能在启动时被发现。
    """
    return _RESOLVED.get((family, size, weight))


def actual_family(family: str) -> str:
    """首选名对应的实际族名（回退之后的结果），没绑过就原样返回。"""
    return _ACTUAL.get(family, family)


def resolved() -> dict[tuple[str, int, str], tuple]:
    """已解析的字体表，测试与排查用。"""
    return dict(_RESOLVED)


def reset() -> None:
    """清空缓存。测试用。"""
    _RESOLVED.clear()
    _ACTUAL.clear()
