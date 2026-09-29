"""界面字体：预设解析 + 共享的 CTkFont 实例。

**这里管的是界面本身的字形，与嵌入书里的正文字体无关** —— 后者是 `Config.font`
指向的 ttf/otf/woff，由 core 校验扩展名并嵌入，界面只提供一个文件选择框。

之所以要自己把「显示名」解析成实际族名：Tk 在字体不存在时**静默回退**、不报错，
用户选了什么就无从查起。这里按操作系统给出候选表，`resolve_family()` 一次解析，
结果存在 `FontManager` 里全窗口共享。
"""

from __future__ import annotations

import sys

import customtkinter as ctk

from .constants import DEFAULT_FONT_LABEL, DEFAULT_TOC_SIZE, FONT_PRESETS_BY_OS

# 派生偏移属于 FontManager 的内部实现，留在本模块
FONT_TITLE_OFFSET = 1  # 标题比正文大 1 号
FONT_TAB_OFFSET = -1  # Tab 标签比正文小 1 号
FONT_TAB_MIN = 9  # Tab 字号下限


def font_presets() -> dict[str, str]:
    """按当前系统返回预设字体表。"""
    if sys.platform == "win32":
        return FONT_PRESETS_BY_OS["win32"]
    if sys.platform == "darwin":
        return FONT_PRESETS_BY_OS["darwin"]
    return FONT_PRESETS_BY_OS["linux"]


def resolve_family(label: str) -> str:
    """显示名 → 实际字体族名；不在预设里就当用户自定义。"""
    return font_presets().get(label, label)


class FontManager:
    """共享的 CTkFont 实例与字号/字体族状态。

    控件建好之后调 `refresh()` 会**就地更新**这些实例，已存在的控件跟着变，
    不需要重建界面。先建空字体再由 `refresh()` 填值，是因为构造时就得把实例
    交给控件，而实际族名/字号此时已经定好了。
    """

    def __init__(
        self,
        ui_size: int,
        family_label: str = DEFAULT_FONT_LABEL,
        toc_size: int = DEFAULT_TOC_SIZE,
    ) -> None:
        self.ui_size = ui_size
        self.toc_size = toc_size
        self.family_label = family_label
        self.family = resolve_family(family_label)

        self.base = ctk.CTkFont()
        self.bold = ctk.CTkFont(weight="bold")
        self.title = ctk.CTkFont(weight="bold")
        self.tab = ctk.CTkFont()

        self.refresh()

    def refresh(self) -> None:
        """把当前 family/size 应用到所有共享字体实例。"""
        s = self.ui_size
        fam = self.family
        self.base.configure(size=s, family=fam)
        self.bold.configure(size=s, family=fam, weight="bold")
        self.title.configure(size=s + FONT_TITLE_OFFSET, family=fam, weight="bold")
        self.tab.configure(size=max(s + FONT_TAB_OFFSET, FONT_TAB_MIN), family=fam)

    def set_ui_size(self, size: int) -> None:
        self.ui_size = size
        self.refresh()

    def set_toc_size(self, size: int) -> None:
        """目录表格字号：走 ttk，不动 CTk 字体实例。

        调用方要自己补一句 `theme.apply_toc_font()` 才生效。
        """
        self.toc_size = size

    def set_family_label(self, label: str) -> None:
        self.family_label = label
        self.family = resolve_family(label)
        self.refresh()
