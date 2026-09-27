"""额外层级编辑器：可动态增删的 `hN[.class]:正则` 行。

**规格格式归 core 所有**：`core.options._level_specs()` 按 `hN[.class]:正则` 拼、
`core.levels.build_levels()` 按同一个格式拆。本组件只负责**拼**，不自己拆、也不另立
一套字段名 —— 拼错的代价是 core 静默把这一层当没配。

`hN` 唯一性在这里校验（红框 + 提示，不等到生成）。规则与 webview 版一致：**已禁用**
的内置层级不参与冲突判断（§8.1 的三态里 `""` 和 `None` 都算「不启用」）。
"""

from __future__ import annotations

import re
import tkinter as tk
from collections.abc import Callable
import ttkbootstrap as ttk

from ..metrics import s
from ..theme import COLORS
from .regex_entry import regex_entry

#: 层级选择器，可选 `.class`
_SELECTOR_RE = re.compile(r"^h([1-6])$")

#: class 名的合法形状（与 `core.levels._SPEC_RE` 一致）
_CLASS_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*$")

#: 内置三层级的 hN。冲突判断时**跳过禁用的**
BUILTIN_LEVELS = {"volume": 2, "chapter": 3, "section": 4}

#: 最多几行
MAX_ROWS = 10

_HINT = "hN（h1~h6）+ 可选 .class + 冒号 + 正则，如 h5.scene:^场景"


class ExtraLevelsEditor(ttk.Frame):
    """额外层级的行列表。`get_specs()` 产出交给 core 的规格字符串。"""

    def __init__(
        self,
        master: tk.Misc,
        *,
        on_change: Callable[[], None] | None = None,
        is_builtin_enabled: Callable[[str], bool] | None = None,
        **kwargs,
    ) -> None:
        super().__init__(master, **kwargs)
        self.on_change = on_change
        #: 判断某个内置层级当前是否启用（`is_builtin_enabled("volume")`）
        self._is_enabled = is_builtin_enabled or (lambda _name: True)

        self.rows: list[dict] = []
        ttk.Label(self, text=_HINT, bootstyle="secondary", wraplength=s(420)).pack(
            anchor="w", pady=(0, s(4)
            )
        )
        self.body = ttk.Frame(self)
        self.body.pack(fill="x")
        self._build_buttons()
        self._changed()

    def _build_buttons(self) -> None:
        bar = ttk.Frame(self)
        bar.pack(fill="x", pady=(s(6), 0))
        ttk.Button(bar, text="添加", command=self.add, width=8).pack(side="left")
        self.v_hint = ttk.Label(bar, text="", bootstyle="secondary", foreground=COLORS["error"])
        self.v_hint.pack(side="left", padx=(s(8), 0))

    # ---------- 值 ----------

    def get_specs(self) -> list[str]:
        """`["h5.scene:^场景", ...]`，只含校验通过的行。

        这是 core 认的格式，**不要**在这里拆开再重新拼回去。
        """
        return [row["spec"] for row in self.rows if row.get("valid") and row.get("spec")]

    def get(self) -> list[dict]:
        """UI 自己的中间结构（给 `settings.py` 存），不是 `values` 的键。

        取 `.get()` 拿实际字符串：`row["h"]` / `row["class_name"]` 存的是 Tk 变量，
        直接存进设置文件会写出 `<StringVar object ...>`。
        """
        return [
            {
                "h": row["h"].get(),
                "class_name": row["class_name"].get().strip(),
                "regex": row["regex"],
            }
            for row in self.rows
        ]

    def set(self, rows: list[dict]) -> None:
        for row in self.rows:
            row["frame"].destroy()
        self.rows.clear()
        for data in rows[:MAX_ROWS]:
            self._append(data.get("h", "h5"), data.get("class_name", ""), data.get("regex", ""))
        self._changed()

    # ---------- 增删 ----------

    def add(self) -> None:
        """加一行。**动态新建的控件必须接上 `on_change` + 补 bindtag。**"""
        if len(self.rows) >= MAX_ROWS:
            self._hint(f"最多 {MAX_ROWS} 条")
            return
        used = self._used_levels()
        free = next((f"h{n}" for n in range(1, 7) if n not in used), "h1")
        self._append(free, "", "")

    def remove(self, index: int) -> None:
        if not 0 <= index < len(self.rows):
            return
        self.rows.pop(index)["frame"].destroy()
        self._changed()

    def _append(self, level: str, class_name: str, regex: str) -> None:
        frame = ttk.Frame(self.body)
        frame.pack(fill="x", pady=(0, s(4)))
        index = len(self.rows)  # 先取序号：self.rows.append 在下面，会变

        v_h = tk.StringVar(value=level)
        v_class = tk.StringVar(value=class_name)
        ttk.Combobox(
            frame, textvariable=v_h, values=[f"h{n}" for n in range(1, 7)], state="readonly", width=4
        ).pack(side="left")
        v_regex = regex_entry(frame, width=32)
        v_regex.pack(side="left", fill="x", expand=True, padx=s(4))
        if regex:
            v_regex.insert(0, regex)
        ttk.Label(frame, text=".").pack(side="left")
        e_class = ttk.Entry(frame, textvariable=v_class, width=14)
        e_class.pack(side="left", padx=(0, s(4)))
        ttk.Button(
            frame, text="删除", width=6, command=lambda i=index: self.remove(i)
        ).pack(side="left")

        row = {
            "frame": frame,
            "h": v_h,
            "class_name": v_class,
            "regex_box": v_regex,
            "class_box": e_class,
        }
        self.rows.append(row)

        for var in (v_h, v_class):
            var.trace_add("write", lambda *_: self._changed())
        v_regex.bind("<KeyRelease>", lambda _e: self._changed(), add="+")
        self._changed()

    # ---------- 校验 ----------

    def _changed(self) -> None:
        self._revalidate()
        if self.on_change is not None:
            self.on_change()

    def _revalidate(self) -> None:
        """逐行重算 `spec` 与 `valid`。hN / class 重复或不合法 → 该行标红并跳过。"""
        seen: dict[int, bool] = {}
        for row in self.rows:
            level = _level_of(row["h"].get())
            class_name = row["class_name"].get().strip()
            # 正则**原样收**，不 strip：首尾空格在正则里有意义（core 也只 strip
            # 选择器那一段，冒号之后整段保留）。
            regex = row["regex_box"].get()
            row["regex"] = regex

            if level is None:
                self._mark(row, False, "层级应是 h1~h6")
                continue
            if class_name and not _CLASS_RE.match(class_name):
                self._mark(row, False, "class 名不合法")
                continue
            if level in seen and self._is_enabled_level(level):
                self._mark(row, False, f"h{level} 重复")
                continue
            if not regex.strip():
                # 空（或只有空白）= 这一行还没填完，跳过。不拼出 `h1:` 那种 core
                # 读不出意思的串。只对「是否为空」做 strip，regex 本身原样保留。
                row["valid"] = False
                self._mark(row, False, "正则不能为空")
                continue
            try:
                re.compile(regex)
            except re.error as exc:
                self._mark(row, False, f"正则非法：{exc}")
                continue
            seen[level] = True
            # 格式归 core 所有：hN + (.class)? + ":" + 正则。冒号后整段都是正则，
            # 所以正则里可以有冒号、不必转义。
            head = f"h{level}.{class_name}" if class_name else f"h{level}"
            row["spec"] = f"{head}:{regex}"
            self._mark(row, True, "")

    def _mark(self, row: dict, ok: bool, message: str) -> None:
        row["valid"] = ok
        row["error"] = message
        # ttkbootstrap 的复位值是 "default"，空串不会复位
        bootstyle = "default" if ok else "danger"
        row["regex_box"].configure(bootstyle=bootstyle)
        row["class_box"].configure(bootstyle=bootstyle)
        self.v_hint.configure(text=message if not ok else "")

    def _hint(self, message: str) -> None:
        self.v_hint.configure(text=message)

    def _used_levels(self) -> set[int]:
        used = {n for n, name in BUILTIN_LEVELS.items() if self._is_enabled(name)}
        for row in self.rows:
            level = _level_of(row["h"].get())
            if level is not None:
                used.add(level)
        return used

    def _is_enabled_level(self, level: int) -> bool:
        """这个 hN 是否被一个**已启用**的内置层级占了。"""
        for name, builtin in BUILTIN_LEVELS.items():
            if builtin == level:
                return self._is_enabled(name)
        return True


def _level_of(selector: str) -> int | None:
    match = _SELECTOR_RE.match((selector or "").strip())
    return int(match.group(1)) if match else None
