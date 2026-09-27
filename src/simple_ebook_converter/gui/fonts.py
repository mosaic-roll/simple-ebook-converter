"""界面字体（给 Tk 用）：枚举一小批常用字体，取第一个真实存在的，都不存在就用 Tk 默认。

**这里管的是界面本身的字形，与嵌入书里的正文字体无关** —— 后者是 `Config.font`
指向的 ttf/otf/woff，由 core 校验扩展名并嵌入，界面只提供一个文件选择框。

## 为什么要自己探一次

Tk 在字体名不存在时**静默回退**、不报错。后果是「想用等宽却没等宽」「中文变方块」，
而且没有任何提示。所以启动时探一次：沿候选链取第一个真实存在的族名，探不到就用
`TkDefaultFont` 的**实际**族名（也就是系统 UI 默认的无衬线体）。

探测只在启动时跑一次并缓存 —— 不是每次建控件都查一遍。

## 「主题自带字体」这件事

`ttk` 确实有默认字体（named font `TkDefaultFont`），`style.configure(".")`
不给 `font=` 时就用它。所以最省事的是**什么都不设**，让 Tk 用系统默认。之所以
仍然显式解析，是因为：

* 界面上有等宽需求（正则、规则、JSON 预览），`TkDefaultFont` 不是等宽，
  这部分必须自己指定；
* 统一解析后可以在状态栏/排查时报告「实际用的是哪个族名」——静默回退时无从查起。

候选链刻意短：只列各平台上真正常见的几个。列几十个不会更准，只是让「实际用了哪个」
更难预测。
"""

from __future__ import annotations

import tkinter as tk
import tkinter.font as tkfont

#: 界面字体的候选链，按偏好顺序。第一个真实存在的胜出。
UI_CANDIDATES = (
    "Microsoft YaHei UI",  # Windows 中文
    "Segoe UI",           # Windows
    "PingFang SC",        # macOS
    "Noto Sans CJK SC",   # Linux 常见
    "DejaVu Sans",        # Linux 兜底
    "Helvetica",          # macOS 兜底
)

#: 等宽字体的候选链（正则、替换规则、JSON 预览用）
MONO_CANDIDATES = (
    "Consolas",           # Windows
    "Cascadia Mono",      # Windows 新版
    "SF Mono",            # macOS
    "Menlo",              # macOS 兜底
    "Noto Sans Mono",     # Linux
    "DejaVu Sans Mono",
    "Courier New",        # 几乎处处都有
)

#: 首选名：诊断信息与「实际族名」的键用它
UI_FONT = "Segoe UI"
MONO_FONT = "Consolas"

#: 界面基准字号（磅）。负数表示像素、不随 tk scaling 缩放，高 DPI 下不变大，故不用
UI_SIZE = 10

#: 已解析的族名。`{候选链 id: 实际族名}`。启动时填好，之后只读
_ACTUAL: dict[str, str] = {}

#: 系统默认的**实际**族名（无衬线），作为所有候选都探不到时的兜底
_FALLBACK = "Helvetica"


def bind_fonts(root: tk.Misc) -> None:
    """启动时调一次（**必须在 `theme.apply()` 之前**）：把两条链都探到底。

    `theme.apply()` 只读 `font()`，不自己探测；少了这一步 `font()` 拿不到已解析的
    族名，样式会退回 Tk 默认。
    """
    _bind_chain(root, "ui", UI_CANDIDATES)
    _bind_chain(root, "mono", MONO_CANDIDATES)


def _bind_chain(root: tk.Misc, key: str, candidates: tuple[str, ...]) -> None:
    available = _available(root)
    actual = next((name for name in candidates if name in available), "")
    if not actual:
        actual = _default_family(root)
    _ACTUAL[key] = actual


def _available(root: tk.Misc) -> set[str]:
    """本机真实存在的族名集合；探测失败时返回空集（全部候选视为不可用）。

    探不到就当全都不存在、走默认族名，而不是抛错 —— 字体解析失败不该让 GUI 起不来。
    """
    try:
        return set(tkfont.families(root))
    except tk.TclError:
        return set()


def _default_family(root: tk.Misc) -> str:
    """`TkDefaultFont` 的实际族名，即系统 UI 默认的无衬线体。"""
    try:
        return str(tkfont.nametofont("TkDefaultFont", root=root).actual("family")) or _FALLBACK
    except (tk.TclError, KeyError):
        return _FALLBACK


def font(family: str = UI_FONT, size: int = UI_SIZE, weight: str = "") -> tuple:
    """字体规格 → Tk 字体元组。

    `family` 取 `"ui"` 或 `"mono"`（两条链的 id），也可以直接给族名。**必须先
    `bind_fonts()`**，否则会拿到未经解析的名字、由 Tk 静默回退 —— 那正是本模块要
    消除的情况。
    """
    actual = _ACTUAL.get(family, family)
    return (actual, size, weight) if weight else (actual, size)


def actual_family(family: str = "ui") -> str:
    """实际用了哪个族名。状态栏/排查用；没绑过就原样返回。"""
    return _ACTUAL.get(family, family)


def reset() -> None:
    """清空缓存。测试用。"""
    _ACTUAL.clear()
