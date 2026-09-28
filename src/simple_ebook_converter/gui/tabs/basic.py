"""「基础」页签：输入、输出、书籍信息、清理开关。

值收集只做一件事：把控件内容搬进 `BasicValues`，**不做解释**。校验在
`build_config_from_ui()` 之后由 core 兜底，这里只管即时反馈（红/黄框 + 提示）。
"""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from dataclasses import asdict

import tkinter.ttk as ttk

from ...core.encoding import AUTO_ENCODING, ENCODING_CHOICES
from ...core.options import OPTIONS
from ..build_config_from_ui import BasicValues
from ..metrics import s
from ..models.autofill import AutofillPolicy
from ..widgets.form import Check, Choice, Field, Form, Path, Section, Text
from ..widgets.scroll_frame import ScrollFrame

#: 自动填充会覆盖的字段（其余是开关或没有 core 来源）
_AUTOFILL_KEYS = ("out", "encoding", "title", "author", "cover")


def _help(name: str) -> str:
    """取 core 里该选项的帮助文字。界面不另抄一份说明，避免和 CLI `--help` 分叉。"""
    return next(opt for opt in OPTIONS if opt.name == name).help


#: 基础页的布局：**这一页长什么样，看这张表就够了。**
SPEC: tuple[Section, ...] = (
    Section(
        "文件",
        (
            Field("input", "输入文件", Path(kind="input", hide_hint=True)),
            Field("encoding", "编码", Choice(ENCODING_CHOICES, default=AUTO_ENCODING)),
            Field("out", "输出文件", Path(kind="output")),
            Field("overwrite", "覆盖已有文件", Check(default=True)),
        ),
    ),
    Section(
        "书籍信息",
        (
            Field("title", "书名", Text()),
            Field("author", "作者", Text()),
            Field("date", "出版日期", Text(help=_help("date"))),
            Field("language", "语言", Text(help=_help("language"))),
        ),
    ),
    Section(
        "封面",
        (
            Field("cover", "封面图", Path(kind="image")),
            Field("text_cover", "无封面图时生成文字封面页", Check(default=True)),
        ),
    ),
    Section(
        "清理",
        (Field("clean", "清理文本（去段首段尾空格、删空行）", Check(default=True)),),
    ),
)


class BasicTab(ttk.Frame):
    """基础设置。`get()` 收成一个 `BasicValues`。"""

    def __init__(
        self,
        master: tk.Misc,
        *,
        on_change: Callable[[], None] | None = None,
        on_input_chosen: Callable[[str], None] | None = None,
        **kwargs,
    ) -> None:
        super().__init__(master, **kwargs)
        self.on_change = on_change
        self.on_input_chosen = on_input_chosen
        #: 自动填充的覆盖规则（哪些动过、上次自动填了什么）。规则在 models 里，
        #: 与 Tk 无关，可单测。
        self._policy = AutofillPolicy(_AUTOFILL_KEYS, AUTO_ENCODING)
        #: 自动填充期间挂起 on_change，免得填值本身触发一次重扫
        self._suspend = False
        self._rescan_for_input = False
        #: 上次已确认的输入路径。只在真的换了文件时才标记「这次重扫要自动填充」，
        #: 点进点出没改不算。
        self._last_input = ""

        wrap = ScrollFrame(self)
        wrap.pack(fill="both", expand=True)

        self.form = Form(
            wrap.inner,
            SPEC,
            on_change=self._field_changed,
            on_path_valid=self._path_valid,
            padding=(s(12), s(12)),
        )
        self.form.pack(fill="both", expand=True)

        # 对外仍暴露这些控件/变量（App 与测试在用）。声明式只管布局，
        # 不改变「页签暴露什么」。
        self.input_row = self.form.control("input").widget
        self.out_row = self.form.control("out").widget
        self.cover_row = self.form.control("cover").widget
        self._encoding = self.form.control("encoding").var
        self._title = self.form.control("title").var
        self._author = self.form.control("author").var
        self._date = self.form.control("date").var
        self._language = self.form.control("language").var

    # ---------- 值 ----------

    def get(self) -> BasicValues:
        values = self.form.values()
        # 书名/作者/日期/语言两头的空白是手误，收掉；路径/编码不动（原样交给 core）。
        for key in ("title", "author", "date", "language"):
            values[key] = values[key].strip()
        return BasicValues(**values)

    def set(self, values: BasicValues) -> None:
        self._suspend = True
        try:
            data = asdict(values)
            # 空编码 = 没指定 = 自动检测。显示成 `auto` 而不是空白。
            data["encoding"] = values.encoding or AUTO_ENCODING
            self.form.set_values(data)
            # 从设置里读回来的非空字段算「用户已定」，自动填充不许冲掉。
            # 空的（out/encoding 可能是空）留给自动填充。
            self._policy.seed_from_values(
                {key: getattr(values, key) for key in _AUTOFILL_KEYS}
            )
        finally:
            self._suspend = False

    def autofill(self, desired: dict[str, str | None]) -> bool:
        """按设计 §7.4 的 dirty 规则自动填充，返回是否改动了任何字段。

        `desired` 的键是 `out` / `encoding` / `title` / `author` / `cover`，值给
        `None` 表示「这次没有可填的值」（比如没找到封面），跳过。

        **dirty 规则**：只有当字段为空、或仍等于上次自动填的值时才覆盖；用户改过的
        永不复位。规则细节见 `models.autofill.AutofillPolicy`。日期/语言没有 core
        来源，不在自动填充范围内。
        """
        current = {key: self._get_field(key) for key in desired}
        self._suspend = True
        try:
            updates = self._policy.plan(current, desired)
            for key, value in updates.items():
                self._set_field(key, value)
        finally:
            self._suspend = False
        return bool(updates)

    def _get_field(self, key: str) -> str:
        return self.form.value(key)

    def _set_field(self, key: str, value: str) -> None:
        self.form.set_value(key, value)

    def _field_changed(self, key: str) -> None:
        """控件被用户改动：记下「动过」，再走常规变更通知。"""
        if not self._suspend:
            self._policy.mark_touched(key)
        self._changed()

    def _path_valid(self, name: str, _path) -> None:
        """输入文件**真的换了**才标记「下次重扫要自动填充」。其余路径字段不处理。"""
        if name != "input" or self.on_input_chosen is None:
            return
        current = self.input_row.get()
        if current == self._last_input:
            return
        self._last_input = current
        self._rescan_for_input = True
        self.on_input_chosen(current)

    def set_input(self, path: str) -> None:
        """外部（拖入/命令行/最近文件）改了输入路径时同步。只在真的变了才回调。"""
        if self.input_row.get() == path:
            return
        self.input_row.set(path)
        self._last_input = path
        self._rescan_for_input = True
        self._changed()
        # 换文件要自动识别一次目录
        if self.on_input_chosen is not None:
            self.on_input_chosen(path)

    # ---------- 内部 ----------

    def _changed(self) -> None:
        if self._suspend:
            return  # 自动填充写入值不该被当成「用户改了设置」再触发一次重扫
        if self.on_change is not None:
            self.on_change()
