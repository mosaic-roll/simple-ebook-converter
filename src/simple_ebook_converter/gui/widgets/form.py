"""声明式表单：用数据描述「分节 + 字段」，构建器负责排版。

## 为什么

原来的页签 `__init__` 是一长串 `ttk.Label(...).pack(...)` / `ttk.Entry(...).grid(...)`，
要读好几行才知道「这一页有哪些项、怎么分组」。这里把**结构**抽成数据：

    SPEC = (
        Section("文件", (
            Field("input", "输入文件", Path(kind="input")),
            Field("encoding", "编码", Choice(ENCODING_CHOICES, default="auto")),
            ...
        )),
        ...
    )

页签只声明「有什么」，不再重复「标签放左、输入框放右、帮助放下一行」这些排版细节。

## 边界

只管**规则的**「标签 + 一个输入 + 可选帮助」。不规则的组合（识别页的层级行、CSS
编辑器、目录表格）不硬塞进来 —— 那些是独立的组合控件，页签直接放它们即可。硬做
通用化只会得到一套又难懂又难改的抽象。
"""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable, Iterable
from dataclasses import dataclass

import tkinter.ttk as ttk

from ..metrics import s
from .path_row import PathRow


# ---------- 控件类型（纯描述，不含状态） ----------


@dataclass(frozen=True)
class Text:
    """单行输入。`help` 非空时在输入框**下方**显示一行说明。"""

    default: str = ""
    help: str = ""


@dataclass(frozen=True)
class Spin:
    """整数微调框。取值时按 `[low, high]` 夹紧。"""

    low: int = 0
    high: int = 100
    default: int = 0
    help: str = ""


@dataclass(frozen=True)
class Path:
    """路径输入（`PathRow`：标签 + 输入框 + 浏览/清除）。"""

    kind: str = "output"
    hide_hint: bool = False
    help: str = ""


@dataclass(frozen=True)
class Choice:
    """只读下拉。

    `labels` 非空时：下拉里显示 `labels`，`get()` 返回对应的 `choices` 里的
    底层值。对齐方式就是这样——界面显示「左对齐」，core 收 `left`。
    """

    choices: tuple[str, ...] = ()
    default: str = ""
    labels: tuple[str, ...] = ()


@dataclass(frozen=True)
class Check:
    """复选框。"""

    default: bool = True


@dataclass(frozen=True)
class Field:
    """一个字段：`name` 是取值用的键，`label` 是界面文字。"""

    name: str
    label: str
    control: object


@dataclass(frozen=True)
class Section:
    """一组字段，渲染成一个 `LabelFrame`。"""

    title: str
    fields: tuple[Field, ...]


# ---------- 构建出来的控件（有状态） ----------


class _Control:
    """控件的统一取值接口。`widget` / `var` 让调用方能拿到具体控件。"""

    def get(self):  # noqa: ANN201 - 子类各自返回 str / bool
        raise NotImplementedError

    def set(self, value) -> None:  # noqa: ANN001
        raise NotImplementedError

    @property
    def widget(self) -> tk.Misc:
        raise NotImplementedError

    @property
    def var(self) -> tk.Variable | None:
        return None


class _TextControl(_Control):
    def __init__(self, parent, field: Field, spec: Text, on_change, on_path_valid) -> None:
        frame = ttk.Frame(parent)
        frame.pack(fill="x", pady=(0, s(4)))
        top = ttk.Frame(frame)
        top.pack(fill="x")
        ttk.Label(top, text=field.label, width=8).pack(side="left")
        self._var = tk.StringVar(value=spec.default)
        entry = ttk.Entry(top, textvariable=self._var)
        entry.pack(side="left", fill="x", expand=True, padx=(s(6), 0))
        entry.bind("<FocusOut>", lambda _e: on_change(field.name), add="+")
        if spec.help:
            ttk.Label(frame, text=spec.help).pack(
                anchor="w", padx=(s(8), 0)
            )

    def get(self) -> str:
        return self._var.get()

    def set(self, value) -> None:
        self._var.set(value)

    @property
    def widget(self) -> tk.Misc:
        return self._var

    @property
    def var(self) -> tk.StringVar:
        return self._var


class _ChoiceControl(_Control):
    def __init__(self, parent, field: Field, spec: Choice, on_change, on_path_valid) -> None:
        self._spec = spec
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=(s(6), 0))
        ttk.Label(row, text=field.label).pack(side="left")
        self._var = tk.StringVar(value=self._display(spec.default))
        combo = ttk.Combobox(
            row,
            textvariable=self._var,
            values=spec.labels or spec.choices,
            state="readonly",
            width=18)
        combo.pack(side="left", padx=(s(6), 0))
        combo.bind("<<ComboboxSelected>>", lambda _e: on_change(field.name))

    def _display(self, value: str) -> str:
        if self._spec.labels and value in self._spec.choices:
            return self._spec.labels[self._spec.choices.index(value)]
        return value

    def _value(self, display: str) -> str:
        if self._spec.labels and display in self._spec.labels:
            return self._spec.choices[self._spec.labels.index(display)]
        return display

    def get(self) -> str:
        return self._value(self._var.get())

    def set(self, value) -> None:
        self._var.set(self._display(value))

    @property
    def widget(self) -> tk.Misc:
        return self._var

    @property
    def var(self) -> tk.StringVar:
        return self._var


class _SpinControl(_Control):
    def __init__(self, parent, field: Field, spec: Spin, on_change, on_path_valid) -> None:
        frame = ttk.Frame(parent)
        frame.pack(fill="x", pady=(0, s(4)))
        top = ttk.Frame(frame)
        top.pack(fill="x")
        ttk.Label(top, text=field.label, width=8).pack(side="left")
        self._var = tk.IntVar(value=spec.default)
        spin = ttk.Spinbox(top, from_=spec.low, to=spec.high, width=6, textvariable=self._var)
        spin.pack(side="left", padx=(s(6), 0))
        # Spinbox 敲键时 `command` 不一定触发，两个都接上
        spin.bind("<FocusOut>", lambda _e: on_change(field.name), add="+")
        spin.configure(command=lambda: on_change(field.name))
        self._low, self._high = spec.low, spec.high
        if spec.help:
            ttk.Label(frame, text=spec.help).pack(
                anchor="w", padx=(s(8), 0)
            )

    def get(self) -> int:
        try:
            value = int(self._var.get())
        except (tk.TclError, ValueError):
            return self._low
        return max(self._low, min(self._high, value))

    def set(self, value) -> None:
        self._var.set(int(value))

    @property
    def widget(self) -> tk.Misc:
        return self._var

    @property
    def var(self) -> tk.IntVar:
        return self._var


class _CheckControl(_Control):
    def __init__(self, parent, field: Field, spec: Check, on_change, on_path_valid) -> None:
        self._var = tk.BooleanVar(value=spec.default)
        ttk.Checkbutton(
            parent,
            text=field.label,
            variable=self._var,
            command=lambda: on_change(field.name)).pack(anchor="w", pady=(s(4), 0))

    def get(self) -> bool:
        return bool(self._var.get())

    def set(self, value) -> None:
        self._var.set(value)

    @property
    def widget(self) -> tk.Misc:
        return self._var

    @property
    def var(self) -> tk.BooleanVar:
        return self._var


class _PathControl(_Control):
    def __init__(self, parent, field: Field, spec: Path, on_change, on_path_valid) -> None:
        self._row = PathRow(
            parent,
            field.label,
            kind=spec.kind,
            on_change=lambda: on_change(field.name),
            on_valid=lambda path: on_path_valid(field.name, path))
        self._row.pack(fill="x", pady=(s(6), 0))
        if spec.hide_hint:
            self._row.hint.grid_forget()
        if spec.help:
            ttk.Label(parent, text=spec.help).pack(
                anchor="w", pady=(0, s(2))
            )

    def get(self) -> str:
        return self._row.get()

    def set(self, value) -> None:
        self._row.set(value)

    @property
    def widget(self) -> tk.Misc:
        return self._row


_BUILDERS = {
    Text: _TextControl,
    Spin: _SpinControl,
    Choice: _ChoiceControl,
    Check: _CheckControl,
    Path: _PathControl,
}


class Form(ttk.Frame):
    """把 `Section`/`Field` 描述渲染成控件，并统一取值/设值。

    `on_change(name)` 在任何字段变化时调用（页签据此做 dirty 跟踪 / 触发重扫）。
    `on_path_valid(name, path)` 只在路径字段校验后调用。
    """

    def __init__(
        self,
        master: tk.Misc,
        spec: Iterable[Section],
        *,
        on_change: Callable[[str], None] | None = None,
        on_path_valid: Callable[[str, object], None] | None = None,
        padding: tuple[int, int] = (0, 0),
        **kwargs) -> None:
        super().__init__(master, padding=padding, **kwargs)
        self._on_change = on_change
        self._on_path_valid = on_path_valid
        self._controls: dict[str, _Control] = {}

        first = True
        for section in spec:
            box = ttk.LabelFrame(self, text=section.title, padding=(s(8), s(6)))
            box.pack(fill="x", pady=(0 if first else s(10), 0))
            first = False
            for field in section.fields:
                builder = _BUILDERS[type(field.control)]
                self._controls[field.name] = builder(
                    box, field, field.control, self._field_changed, self._path_valid
                )

    # ---------- 回调适配 ----------

    def _field_changed(self, name: str) -> None:
        if self._on_change is not None:
            self._on_change(name)

    def _path_valid(self, name: str, path) -> None:
        if self._on_path_valid is not None:
            self._on_path_valid(name, path)

    # ---------- 取值 / 设值 ----------

    def control(self, name: str) -> _Control:
        return self._controls[name]

    def value(self, name: str):
        return self._controls[name].get()

    def set_value(self, name: str, value) -> None:
        self._controls[name].set(value)

    def values(self) -> dict:
        return {name: control.get() for name, control in self._controls.items()}

    def set_values(self, data: dict) -> None:
        for name, control in self._controls.items():
            if name in data:
                control.set(data[name])
