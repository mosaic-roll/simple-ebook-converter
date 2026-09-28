"""「识别」页签：三条内置层级 + 额外层级 + 标题长度。

## 内置层级的三态

`IdentifyValues.levels` 的值是 `str | None`：

* `None` —— 用户没动过。**不写进 `values`**，由 core 的 `option_default()` 决定，
  改了 core 的默认正则界面自动跟着变。
* `""` —— 用户显式关了这条层级（如「这本书没有卷」）。必须写出空串。
* 非空 —— 显式正则。

所以「关掉卷」不是「把框清空」（清空也是 `""`，与用户没碰过的 `None` 区分不开），
而是那个独立的「启用」勾选框取消勾选 → 写 `""`。这是三态唯一可靠的来源。
"""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
import tkinter.ttk as ttk

from ...core.config import LEVEL_PRESETS
from ...core.options import OPTIONS, option_default
from ..build_config_from_ui import IdentifyValues
from ..metrics import s
from ..widgets.builtin_levels import BuiltinLevelsEditor
from ..widgets.extra_levels import ExtraLevelsEditor
from ..widgets.form import Field, Form, Section, Spin, Text
from ..widgets.scroll_frame import ScrollFrame
from ..widgets.button_row import ButtonRow

#: (选项名, 中文名) —— class 名就是选项名（core 的约定）
_TITLES = tuple((name, label) for _level, name, label, _pattern in LEVEL_PRESETS)

#: 标题最长字数的范围
MAX_LEN_RANGE = (1, 200)


class IdentifyTab(ttk.Frame):
    """章节识别设置。"""

    def __init__(
        self,
        master: tk.Misc,
        *,
        on_change: Callable[[], None] | None = None,
        **kwargs,
    ) -> None:
        super().__init__(master, **kwargs)
        self.on_change = on_change
        #: 建立界面期间挂起：子控件初始化时的 `_changed` 不是用户改动
        self._suspend = True
        #: 有没有尚未应用的改动。改动只置脏，点「应用」才真正重扫目录
        self._dirty = False
        #: 未应用提示文字。**建得早**：子控件（额外层级编辑器）构造时就会触发
        #: `_changed`，那时若还没这个变量就会 AttributeError。
        self.v_dirty = tk.StringVar(value="")

        wrap = ScrollFrame(self)
        wrap.pack(fill="both", expand=True)
        body = ttk.Frame(wrap.inner, padding=(s(12), s(12)))
        body.pack(fill="both", expand=True)

        box = ttk.LabelFrame(body, text="内置层级", padding=(s(8), s(6)))
        box.pack(fill="x")
        # 三行内置层级的布局与三态规则在组件里（这里是页面，不再写 grid）
        self.builtin = BuiltinLevelsEditor(
            box,
            titles=_TITLES,
            default_of=lambda name: option_default(_option(name)),
            on_change=self._changed,
            # 勾选变化要让额外层级的冲突判断重算
            on_toggle=self._on_levels_toggled,
        )
        self.builtin.pack(fill="x")
        #: 对外仍暴露这两个映射（测试与冲突判断在用）
        self._levels = self.builtin.levels
        self._touched = self.builtin.touched

        extra = ttk.LabelFrame(body, text="额外层级", padding=(s(8), s(6)))
        extra.pack(fill="both", expand=True, pady=(s(12), 0))
        self.extra = ExtraLevelsEditor(
            extra,
            on_change=self._changed,
            # 冲突判断要看内置层级当前是否启用
            is_builtin_enabled=lambda name: self._levels[name][0].get(),
        )
        # 内部状态变了要让编辑器重算（它问 is_builtin_enabled 才知道冲突）
        self.revalidate_extra = self.extra._revalidate

        # 识别设置：**不即时重扫**，攒到点「应用」再扫。
        # 底部用声明式 Form 声明，`on_change` 统一触发 `_changed`。
        self.form = Form(
            body,
            (Section("识别设置", (
                Field("max_title_len", "标题最长字数", Spin(MAX_LEN_RANGE[0], MAX_LEN_RANGE[1], default=6)),
                Field("preface_title", "前言标题", Text()),
            ),),),
            on_change=self._changed,
            padding=(s(8), 0),
        )
        self.form.pack(fill="x", pady=(s(10), 0))
        self._max_len = self.form.control("max_title_len").var
        self._preface = self.form.control("preface_title").var

        # 按钮先占右边：提示文字可长可短，别把按钮挤出可视区
        actions = ttk.Frame(body)
        actions.pack(fill="x", pady=(s(10), 0))
        row = ButtonRow(actions)
        row.pack(side="right")
        row.add_spacer_expand()
        self.btn_apply = row.add("应用", self._apply)
        ttk.Label(actions, textvariable=self.v_dirty).pack(side="left")

        self._suspend = False

    # ---------- 值 ----------

    def get(self) -> IdentifyValues:
        return IdentifyValues(
            levels=self.builtin.state(),
            level_rows=self.extra.get(),
            max_title_len=_clamp(self.form.value("max_title_len"), *MAX_LEN_RANGE),
            preface_title=self.form.value("preface_title").strip(),
        )

    def set(self, values: IdentifyValues) -> None:
        self._suspend = True
        try:
            self.builtin.set_state(values.levels)
            self.extra.set([dict(row) for row in values.level_rows])
            self.form.set_value("max_title_len", values.max_title_len)
            self.form.set_value("preface_title", values.preface_title)
        finally:
            self._suspend = False
        self._clear_dirty()

    # ---------- 内部 ----------

    def _on_levels_toggled(self) -> None:
        """内置层级勾选变化 → 额外层级的冲突判断要重算。"""
        self.revalidate_extra()

    def _changed(self) -> None:
        """控件改了：只置脏，不重扫。真正重扫在 `_apply()`。"""
        if self._suspend:
            return
        self._dirty = True
        self.v_dirty.set("识别设置已改动，点「应用」重新识别目录")

    def _clear_dirty(self) -> None:
        self._dirty = False
        self.v_dirty.set("")

    def _apply(self) -> None:
        """用户点「应用」：把当前设置交给外部（重扫目录）。"""
        self._clear_dirty()
        if self.on_change is not None:
            self.on_change()


def _option(name: str):
    """按名字取 `core.options.OPTIONS` 里的一条。

    本地薄封装：core 把这个查找函数写成下划线私有的，GUI 侧有四五处要查，
    在这里聚成一个公开名字比逐处 import 私有名更清楚。
    """
    return next(opt for opt in OPTIONS if opt.name == name)


def _clamp(value, low: int, high: int) -> int:
    try:
        return max(low, min(high, int(value)))
    except (TypeError, ValueError):
        return low

