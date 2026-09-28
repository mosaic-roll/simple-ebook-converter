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
from ..models import levels_state
from ..widgets.extra_levels import ExtraLevelsEditor
from ..widgets.form import Field, Form, Section, Spin, Text
from ..widgets.regex_entry import regex_entry
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
        #: 选项名 → (启用勾选的 BooleanVar, 正则框的 StringVar)
        self._levels: dict[str, tuple[tk.BooleanVar, tk.StringVar]] = {}
        #: 选项名 → 用户动过没有。三态里的 `None` 靠它，不能从控件状态推
        self._touched: dict[str, bool] = {}
        for index, (name, label) in enumerate(_TITLES):
            self._levels[name] = self._level_row(box, name, label, index)
            # 初始都算「没动过」。不预置的话，没调过 `set()` 就 `get()` 会 KeyError
            # （App 里 `set()` 先跑所以看不出来，但控件不该依赖调用顺序）。
            self._touched[name] = False

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
            levels=self._levels_state(),
            level_rows=self.extra.get(),
            max_title_len=_clamp(self.form.value("max_title_len"), *MAX_LEN_RANGE),
            preface_title=self.form.value("preface_title").strip(),
        )

    def set(self, values: IdentifyValues) -> None:
        self._suspend = True
        try:
            for name, (enabled, pattern) in self._levels.items():
                given = values.levels.get(name)
                default = str(option_default(_option(name)))
                on, text, touched = levels_state.from_saved(given, default)
                enabled.set(on)
                pattern.set(text)
                self._touched[name] = touched
            self.extra.set([dict(row) for row in values.level_rows])
            self.form.set_value("max_title_len", values.max_title_len)
            self.form.set_value("preface_title", values.preface_title)
        finally:
            self._suspend = False
        self._clear_dirty()

    def _levels_state(self) -> dict[str, str | None]:
        """收集三态。

        `None`（未动过）**不能**从「勾选框 + 文本框」的状态推出来 —— 框里总有内容，
        哪怕是 core 缺省正则。必须另记一个「用户动过没有」的标记，否则每次 `get()`
        都会发出去一个显式正则，core 的缺省从此再也改不动。

        * 未动过 → `None`：不发这个键，core 用 `option_default`
        * 取消勾选 → `""`：显式关闭
        * 动过且框里有内容 → 该正则
        * 动过但框被清空 → `""`（空正则在 core 里就是不启用）

        **正则原样收，不做 `strip`**：首尾空格在正则里是有意义的（比如要匹配段首的
        空白、或故意匹配行尾空格）。core 的 `parse_level_spec()` 也只在 `:` 之前
        `strip`，冒号之后整段保留。
        """
        return {
            name: levels_state.to_saved(
                enabled.get(), self._touched[name], pattern.get()
            )
            for name, (enabled, pattern) in self._levels.items()
        }

    # ---------- 内部 ----------

    def _level_row(
        self, parent: ttk.Frame, name: str, label: str, row: int
    ) -> tuple[tk.BooleanVar, tk.StringVar]:
        """一行：启用勾选 + 正则框 + 恢复默认。返回 (启用变量, 正则变量)。"""
        frame = ttk.Frame(parent)
        frame.grid(row=row, column=0, sticky="ew", pady=(0, s(4)))
        parent.columnconfigure(0, weight=1)
        frame.columnconfigure(1, weight=1)

        default = str(option_default(_option(name)))
        enabled = tk.BooleanVar(value=bool(default))
        box = ttk.Checkbutton(
            frame, text=label, variable=enabled, command=lambda n=name: self._on_toggle(n)
        )
        box.grid(row=0, column=0, sticky="w")

        pattern = tk.StringVar(value=default)
        # **先放「恢复默认」再放正则框**：正则框 `fill=x, expand`，pack 会把空间
        # 优先给它、把后放的控件挤出可视区。按钮先占住右边，框再吃剩下的，
        # 窄窗口下按钮才不会被挤没。改用 ButtonRow + spacer 保持同样的效果。
        btns = ButtonRow(frame)
        btns.grid(row=0, column=2, sticky="e", padx=(s(6), 0))
        btns.add_spacer_expand()
        btns.add("恢复默认", lambda n=name, v=pattern: self._restore_default(n, v), width=8)
        entry = regex_entry(frame, textvariable=pattern, width=40)
        entry.grid(row=0, column=1, sticky="ew", padx=(s(6), s(4)))
        pattern.trace_add("write", lambda *_, n=name: self._on_pattern(n))
        return enabled, pattern

    def _on_pattern(self, name: str) -> None:
        """正则框内容变了 → 算「用户动过」。`set()` 也会触发，故那里先重置标记。"""
        self._touched[name] = True
        self._changed()

    def _restore_default(self, name: str, var: tk.StringVar) -> None:
        """「恢复默认」：填回 core 缺省并**标记为未动过**。

        填回内容 + 清除 touched 两件事必须一起做，否则框里显示的是缺省正则、
        发出去的却还是用户之前那条 —— 看着对、跑起来是另一回事。
        """
        var.set(str(option_default(_option(name))))
        self._touched[name] = False
        self._on_toggle(name)

    def _on_toggle(self, name: str | None = None) -> None:
        """勾选状态变化：让额外层级的冲突判断跟着重算。

        勾选也是「动过」——用户主动关掉一条层级，和它一直用着缺省是两回事。
        但 `_restore_default()` 会在填回缺省后调到这里，所以那里已先把 touched 清了。
        """
        if name is not None and self._levels[name][0].get():
            self._touched[name] = True
        self.revalidate_extra()
        self._changed()

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

