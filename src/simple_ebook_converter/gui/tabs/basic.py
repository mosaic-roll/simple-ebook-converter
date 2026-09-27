"""「基础」页签：输入、输出、书籍信息、清理开关。

值收集只做一件事：把控件内容搬进 `BasicValues`，**不做解释**。校验在
`build_config_from_ui()` 之后由 core 兜底，这里只管即时反馈（红/黄框 + 提示）。
"""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
import ttkbootstrap as ttk

from ...core.encoding import AUTO_ENCODING, ENCODING_CHOICES
from ..build_config_from_ui import BasicValues
from ..metrics import s
from ..widgets.path_row import PathRow
from ..widgets.scroll_frame import ScrollFrame


def _help(name: str) -> str:
    """取 core 里该选项的帮助文字。界面不另抄一份说明，避免和 CLI `--help` 分叉。"""
    from ...core.options import OPTIONS

    return next(opt for opt in OPTIONS if opt.name == name).help


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
        #: 用户动过的字段（自动填充永不复位它们）
        self._touched: set[str] = set()
        #: 字段 → 上次自动填的值（用于「仍等于上次自动值就允许再覆盖」）
        self._auto: dict[str, str] = {}
        #: 自动填充期间挂起 on_change，免得填值本身触发一次重扫
        self._suspend = False

        wrap = ScrollFrame(self)
        wrap.pack(fill="both", expand=True)
        body = ttk.Frame(wrap.inner, padding=(s(12), s(12)))
        body.pack(fill="both", expand=True)

        # 分组（文件 / 书籍信息 / 封面 / 清理）：每个开关都放进它管的那一组里，
        # 而不是散在组之间用空行隔开 —— 「覆盖已有文件」属于输出，「文字封面页」
        # 属于封面，放在各自组的末尾才看得出归属。
        files = ttk.LabelFrame(body, text="文件", padding=(s(8), s(6)))
        files.pack(fill="x")
        self.input_row = PathRow(
            files, "输入文件", kind="input", on_change=self._changed, on_valid=self._input_valid
        )
        self.input_row.pack(fill="x")
        self.input_row.hint.grid_forget()  # 输入行有专用提示，不重复占位

        # 编码候选取自 core 的 ENCODING_CHOICES（首项就是 auto），不另抄一份。
        # 默认就选 `auto`（不是空串）：空白下拉看着像「没检测到」而不是「自动检测」。
        self._encoding = self._choice_row(
            files, "编码", ENCODING_CHOICES, "自动检测",
            key="encoding", default=AUTO_ENCODING,
        )
        self.out_row = PathRow(
            files, "输出文件", kind="output", on_change=lambda: self._field_changed("out")
        )
        self.out_row.pack(fill="x", pady=(s(6), 0))
        self.v_overwrite = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            files, text="覆盖已有文件", variable=self.v_overwrite, command=self._changed
        ).pack(anchor="w", pady=(s(4), 0))

        meta = ttk.LabelFrame(body, text="书籍信息", padding=(s(8), s(6)))
        meta.pack(fill="x", pady=(s(10), 0))
        # 属性名与 BasicValues 的字段一一对应，get()/set() 直接引用
        self._title = self._text_row(meta, "书名", key="title")
        self._author = self._text_row(meta, "作者", key="author")
        # 日期/语言没有 core 来源，不参与自动填充，故没有 key；帮助文字取自 core
        self._date = self._text_row(meta, "出版日期", help_text=_help("date"))
        self._language = self._text_row(meta, "语言", help_text=_help("language"))

        cover = ttk.LabelFrame(body, text="封面", padding=(s(8), s(6)))
        cover.pack(fill="x", pady=(s(10), 0))
        self.cover_row = PathRow(
            cover, "封面图", kind="image", picker="image",
            on_change=lambda: self._field_changed("cover"),
        )
        self.cover_row.pack(fill="x")
        self.v_text_cover = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            cover, text="无封面图时生成文字封面页", variable=self.v_text_cover, command=self._changed
        ).pack(anchor="w", pady=(s(4), 0))

        clean = ttk.LabelFrame(body, text="清理", padding=(s(8), s(6)))
        clean.pack(fill="x", pady=(s(10), 0))
        self.v_clean = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            clean, text="清理文本（去段首段尾空格、删空行）",
            variable=self.v_clean, command=self._changed,
        ).pack(anchor="w")

        wrap.retag_all()

    # ---------- 值 ----------

    def get(self) -> BasicValues:
        return BasicValues(
            input=self.input_row.get(),
            encoding=self._encoding.get(),
            out=self.out_row.get(),
            overwrite=bool(self.v_overwrite.get()),
            clean=bool(self.v_clean.get()),
            title=self._title.get().strip(),
            author=self._author.get().strip(),
            date=self._date.get().strip(),
            language=self._language.get().strip(),
            cover=self.cover_row.get(),
            text_cover=bool(self.v_text_cover.get()),
        )

    def set(self, values: BasicValues) -> None:
        self._suspend = True
        try:
            self.input_row.set(values.input)
            # 空编码 = 没指定 = 自动检测。显示成 `auto` 而不是空白。
            self._encoding.set(values.encoding or AUTO_ENCODING)
            self.out_row.set(values.out)
            self.v_overwrite.set(values.overwrite)
            self.v_clean.set(values.clean)
            self._title.set(values.title)
            self._author.set(values.author)
            self._date.set(values.date)
            self._language.set(values.language)
            self.cover_row.set(values.cover)
            self.v_text_cover.set(values.text_cover)
            # 从设置里读回来的非空字段算「用户已定」，自动填充不许冲掉。
            # 空的（out/encoding 可能是空）留给自动填充。
            self._touched = {
                key
                for key, value in {
                    "out": values.out,
                    "encoding": values.encoding,
                    "title": values.title,
                    "author": values.author,
                    "cover": values.cover,
                }.items()
                if value
            }
            self._auto.clear()
        finally:
            self._suspend = False

    def autofill(self, desired: dict[str, str | None]) -> bool:
        """按设计 §7.4 的 dirty 规则自动填充，返回是否改动了任何字段。

        `desired` 的键是 `out` / `encoding` / `title` / `author` / `cover`，值给
        `None` 表示「这次没有可填的值」（比如没找到封面），跳过。

        **dirty 规则**：只有当字段为空、或仍等于上次自动填的值时才覆盖；用户改过的
        （`_touched`）永不复位。日期/语言没有 core 来源，不在自动填充范围内。
        """
        changed = False
        self._suspend = True
        try:
            for key, value in desired.items():
                if value is None:
                    continue
                current = self._get_field(key)
                if current == value:
                    self._auto[key] = value
                    continue
                # 设计 §7.4：只有「空」或「仍等于上次自动值」才覆盖。
                if not self._fillable(key, current):
                    continue
                self._set_field(key, value)
                self._auto[key] = value
                changed = True
        finally:
            self._suspend = False
        return changed

    def _fillable(self, key: str, current: str) -> bool:
        if not current or current == self._auto.get(key):
            return True
        # 编码的默认值是 `auto`（非空串），但它表示「还没定」。只有用户**显式**
        # 选过 auto 时才不该被覆盖 —— 这个「显式」靠 `_touched` 记。
        return (
            key == "encoding"
            and current == AUTO_ENCODING
            and key not in self._touched
        )

    def _get_field(self, key: str) -> str:
        if key == "out":
            return self.out_row.get()
        if key == "cover":
            return self.cover_row.get()
        return {"encoding": self._encoding, "title": self._title, "author": self._author}[
            key
        ].get()

    def _set_field(self, key: str, value: str) -> None:
        if key == "out":
            self.out_row.set(value)
        elif key == "cover":
            self.cover_row.set(value)
        else:
            {"encoding": self._encoding, "title": self._title, "author": self._author}[
                key
            ].set(value)

    def _field_changed(self, key: str) -> None:
        """控件被用户改动：记下「动过」，再走常规变更通知。"""
        if not self._suspend:
            self._touched.add(key)
        self._changed()

    def set_input(self, path: str) -> None:
        """外部（拖入/命令行/最近文件）改了输入路径时同步。只在真的变了才回调。"""
        if self.input_row.get() == path:
            return
        self.input_row.set(path)
        self._changed()

    # ---------- 内部 ----------

    def _text_row(
        self, parent: ttk.Frame, label: str, *, key: str | None = None, help_text: str = ""
    ) -> tk.StringVar:
        """一行「标签 + Entry」，帮助文字另起一行放在**输入框下方**。

        `key` 给了才参与自动填充的 dirty 判断：用户敲键即算「动过」。
        帮助文字单占一行而不是挤在右边：右边那种写法在窄窗口里会被顶出去，而且
        长一点的说明（比如日期格式）根本放不下。
        """
        frame = ttk.Frame(parent)
        frame.pack(fill="x", pady=(0, s(4)))
        top = ttk.Frame(frame)
        top.pack(fill="x")
        ttk.Label(top, text=label, width=8).pack(side="left")
        var = tk.StringVar()
        entry = ttk.Entry(top, textvariable=var)
        entry.pack(side="left", fill="x", expand=True, padx=(s(6), 0))
        notify = (lambda: self._field_changed(key)) if key else self._changed
        entry.bind("<KeyRelease>", lambda _e: notify(), add="+")
        if help_text:
            ttk.Label(frame, text=help_text, bootstyle="secondary").pack(
                anchor="w", padx=(s(8), 0)
            )
        return var

    def _choice_row(
        self, parent: ttk.Frame, label: str, choices, hint: str = "",
        *, key: str | None = None, default: str = "",
    ):
        """一行标签 + 只读下拉。返回 StringVar。"""
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=(s(8), 0))
        ttk.Label(row, text=label).pack(side="left")
        var = tk.StringVar(value=default)
        combo = ttk.Combobox(row, textvariable=var, values=choices, state="readonly", width=18)
        combo.pack(side="left", padx=(s(6), 0))
        notify = (lambda: self._field_changed(key)) if key else self._changed
        combo.bind("<<ComboboxSelected>>", lambda _e: notify())
        if hint:
            ttk.Label(row, text=hint, bootstyle="secondary").pack(side="left", padx=(s(8), 0))
        return var

    def _input_valid(self, _path) -> None:
        """输入文件确定后告知外部（要重扫目录）。"""
        if self.on_input_chosen is not None:
            self.on_input_chosen(self.input_row.get())

    def _changed(self) -> None:
        if self._suspend:
            return  # 自动填充写入值不该被当成「用户改了设置」再触发一次重扫
        if self.on_change is not None:
            self.on_change()
