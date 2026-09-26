"""Tkinter 前端：表单按 `core.options` 的选项表生成，动作全部交给 core。

和 CLI 用的是同一张选项表、同一套缺省值、同一个 `core.pipeline`，所以两个界面上
同名选项的含义与缺省值必然一致；这里只负责摆控件、收值、显示结果。
"""

from __future__ import annotations

import tkinter as tk
from dataclasses import replace
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .._meta import DIST_NAME
from ..core.config import Config
from ..core.encoding import EncodingError, read_lines
from ..core.meta import resolve_metadata
from ..core.options import (
    OPTIONS,
    Option,
    build_config,
    option_default,
    option_groups,
)
from ..core.pipeline import (
    read_book,
    resolve as resolve_config,
    scan_toc,
    write_css,
    write_epub,
    write_text,
    write_toc,
)
from ..core.replace import (
    DEFAULT_SCOPE,
    SCOPE_LABELS,
    replacers_by_scope,
    rules_from_json,
    rules_from_rows,
    rules_to_json,
)
from ..core.toc import to_json

#: 替换规则下拉框用 core 的中文标签，两个方向都齐全
_DEFAULT_SCOPE_LABEL = SCOPE_LABELS[DEFAULT_SCOPE]

#: 替换规则的表格挂在「清理与替换」这一组下面
_REPLACE_GROUP = "清理与替换"


# ---------- 纯逻辑：不碰 Tk，测试直接调 ----------


def form_default(opt: Option):
    """控件初值。勾选框与正面字段同名同语义（`覆盖已有文件` 勾上就是覆盖），
    多行文本框（额外层级）一行一项，空就是空文本框。
    """
    value = option_default(opt)
    if opt.multiple:
        return "\n".join(str(item) for item in value)
    return "" if value is None else value


def replacement_json(rows) -> str:
    """替换规则表格 → JSON 文本。

    表格只是这个界面上的写法，core 和 CLI 内部只认 JSON，所以这里转成
    `replace_json` 的值再交出去（和 `--replace-json` 完全同一条路）。
    """
    return rules_to_json(rules_from_rows(rows))


def option_values(fields: dict) -> dict:
    """控件值 → `build_config()` 认的选项名。

    只做一件事：替换规则表格非空时以表格为准，转成 `replace_json` 填进去。
    """
    values = {opt.name: fields[opt.name] for opt in OPTIONS if opt.name in fields}
    if fields.get("replacements"):
        values["replace_json"] = replacement_json(fields["replacements"])
    return values


def make_config(fields: dict) -> Config:
    """界面字段 → `Config`。字段名就是选项名，所以直接交给 core 的 `build_config()`。"""
    return build_config(option_values(fields))


def preview_data(fields: dict) -> tuple[list[dict], object]:
    """扫出目录树（JSON 列表）与标题替换函数；树里只存原始标题，展示时现算。

    只走两阶段里的阶段一，不读正文内容之外的任何重活。
    """
    cfg = resolve_config(make_config(fields))
    try:
        lines, _ = read_lines(cfg.input, cfg.encoding)
    except EncodingError as e:
        raise ValueError(str(e)) from e
    except OSError as e:
        raise ValueError(f"无法读取输入文件：{e}") from e
    tree, _ = scan_toc(lines, cfg)
    titles, _ = replacers_by_scope(cfg.replacements)
    return to_json(tree, cfg.toc_depth), titles.text


def generate_output(fields: dict) -> Path:
    """按当前设置产出文件，返回写出的路径；出错抛 ValueError。

    产出方式与 CLI 的三个开关一一对应：只导出 CSS / 只输出目录 / 生成 EPUB。
    """
    cfg = make_config(fields)
    if cfg.dump_css:
        return write_css(cfg)
    if cfg.toc_only and not cfg.out:
        # 界面没有标准输出，目录默认写到输入旁边的同名 .md
        cfg = replace(cfg, out=Path(cfg.input).with_suffix(".md"))
    book = read_book(cfg)
    return write_toc(book) if cfg.toc_only else write_epub(book)


# ---------- 界面 ----------


class App:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        root.title(f"{DIST_NAME} — TXT 电子书生成器")
        root.geometry("1100x740")

        self.vars: dict[str, tk.Variable] = {}
        self.texts: dict[str, tk.Text] = {}
        self._tip_job: str | None = None
        self._tip_window: tk.Toplevel | None = None
        self.v_status = tk.StringVar(value="就绪")

        self._build_ui()

    # ---------- 变量 ----------

    def _make_var(self, opt: Option) -> tk.Variable:
        """整数也用字符串存：输入框清空时不会抛 TclError，缺省值交给 core 兜。"""
        if opt.kind is bool:
            return tk.BooleanVar(value=bool(form_default(opt)))
        return tk.StringVar(value=str(form_default(opt)))

    def _fields(self) -> dict:
        fields: dict = {}
        for opt in OPTIONS:
            if opt.name in self.vars:
                fields[opt.name] = self.vars[opt.name].get()
        for name, text in self.texts.items():
            fields[name] = text.get("1.0", "end")
        fields["replacements"] = [
            tuple(self.replace_tree.item(iid, "values")) or ("", "", _DEFAULT_SCOPE_LABEL)
            for iid in self.replace_tree.get_children()
        ]
        return fields

    # ---------- 布局 ----------

    def _build_ui(self) -> None:
        pane = ttk.Panedwindow(self.root, orient=tk.HORIZONTAL)
        pane.grid(row=0, column=0, sticky="nsew")
        self.root.rowconfigure(0, weight=1)
        self.root.columnconfigure(0, weight=1)

        tabs = ttk.Notebook(pane)
        pane.add(tabs, weight=3)
        for title, options in option_groups():
            self._build_tab(tabs, title, options)

        self._build_preview(pane)

        bar = ttk.Frame(self.root, padding=(8, 0, 8, 8))
        bar.grid(row=1, column=0, sticky="ew")
        ttk.Label(bar, textvariable=self.v_status).pack(side="left")
        ttk.Button(bar, text="刷新目录预览", command=self.do_preview).pack(side="right", padx=4)
        ttk.Button(bar, text="生成 EPUB", command=self.do_generate).pack(side="right")

    def _build_tab(self, nb: ttk.Notebook, title: str, options: tuple[Option, ...]) -> None:
        frame = ttk.Frame(nb, padding=8)
        nb.add(frame, text=title)
        row = 0
        for opt in options:
            row = self._build_row(frame, opt, row)
        if title == _REPLACE_GROUP:
            self._build_replace_table(frame, row)

    def _build_row(self, parent: ttk.Frame, opt: Option, row: int) -> int:
        """摆一行控件，返回下一个空行号。反面选项的勾选框自己带标签，独占一行。"""
        var = self._make_var(opt)
        self.vars[opt.name] = var

        if opt.kind is bool:
            widget = ttk.Checkbutton(parent, text=opt.label, variable=var)
            widget.grid(row=row, column=0, columnspan=3, sticky="w", pady=2)
            self._tip(widget, opt)
            return row + 1

        if opt.multiple:
            widget = tk.Text(parent, height=4, width=40)
            widget.insert("1.0", form_default(opt))
            self.texts[opt.name] = widget
            self._tip(widget, opt)
        else:
            widget = self._entry(parent, opt, var)
            self._tip(widget, opt)

        ttk.Label(parent, text=opt.label).grid(row=row, column=0, sticky="w", pady=2)
        widget.grid(row=row, column=1, sticky="ew", pady=2, padx=4)
        if opt.kind is Path:
            ttk.Button(parent, text="浏览", command=lambda o=opt: self._browse(o)).grid(
                row=row, column=2, sticky="w", pady=2
            )
        parent.columnconfigure(1, weight=1)
        return row + 1

    def _entry(self, parent: ttk.Frame, opt: Option, var: tk.Variable) -> ttk.Widget:
        if opt.choices:
            return ttk.Combobox(
                parent, textvariable=var, values=list(opt.choices), state="readonly"
            )
        if opt.kind is int:
            return ttk.Spinbox(parent, from_=0, to=1000, textvariable=var)
        return ttk.Entry(parent, textvariable=var)

    def _tip(self, widget: tk.Widget, opt: Option) -> None:
        """把选项说明挂成悬浮提示——说明文本在选项表里只写一份，CLI 与 GUI 共用。"""
        widget.bind("<Enter>", lambda _e, o=opt, w=widget: self._show_tip(w, o.help), add="+")
        widget.bind("<Leave>", lambda _e: self._hide_tip(), add="+")

    def _show_tip(self, widget: tk.Widget, text: str) -> None:
        self._hide_tip()
        self._tip_job = widget.after(400, lambda: self._place_tip(widget, text))

    def _place_tip(self, widget: tk.Widget, text: str) -> None:
        self._tip_job = None
        if not text:
            return
        self._tip_window = tk.Toplevel(self.root)
        self._tip_window.wm_overrideredirect(True)
        x = widget.winfo_rootx() + 12
        y = widget.winfo_rooty() + widget.winfo_height() + 4
        self._tip_window.wm_geometry(f"+{x}+{y}")
        ttk.Label(
            self._tip_window, text=text, wraplength=420, padding=(6, 4), background="#ffffe0"
        ).pack()

    def _hide_tip(self) -> None:
        self._cancel_tip()
        if self._tip_window is not None:
            self._tip_window.destroy()
            self._tip_window = None

    def _cancel_tip(self) -> None:
        if self._tip_job is not None:
            self.root.after_cancel(self._tip_job)
            self._tip_job = None

    # ---------- 替换规则表格 ----------

    def _build_replace_table(self, parent: ttk.Frame, row: int) -> None:
        ttk.Label(
            parent,
            text="逐条编辑（优先于上面的 JSON 入口）；按顺序生效，作用范围默认「标题」，"
            "留空正则的行被忽略",
            wraplength=520,
        ).grid(row=row, column=0, columnspan=3, sticky="w", pady=(8, 0))
        row += 1

        self.replace_tree = ttk.Treeview(
            parent, columns=("pattern", "replace", "scope"), show="headings", height=6
        )
        for column, heading, width in (
            ("pattern", "正则查找", 200),
            ("replace", "替换为", 200),
            ("scope", "作用范围", 80),
        ):
            self.replace_tree.heading(column, text=heading)
            self.replace_tree.column(column, width=width)
        self.replace_tree.grid(row=row, column=0, columnspan=3, sticky="ew", pady=4)
        row += 1

        self.v_rp = tk.StringVar()
        self.v_rr = tk.StringVar()
        self.v_rs = tk.StringVar(value=_DEFAULT_SCOPE_LABEL)
        edit = ttk.Frame(parent)
        edit.grid(row=row, column=0, columnspan=3, sticky="ew")
        ttk.Label(edit, text="查找").pack(side="left")
        ttk.Entry(edit, textvariable=self.v_rp).pack(side="left", fill="x", expand=True, padx=4)
        ttk.Label(edit, text="替换为").pack(side="left")
        ttk.Entry(edit, textvariable=self.v_rr).pack(side="left", fill="x", expand=True, padx=4)
        ttk.Label(edit, text="范围").pack(side="left", padx=(8, 0))
        ttk.Combobox(
            edit,
            textvariable=self.v_rs,
            values=list(SCOPE_LABELS.values()),
            state="readonly",
            width=6,
        ).pack(side="left", padx=4)
        row += 1

        buttons = ttk.Frame(parent)
        buttons.grid(row=row, column=0, columnspan=3, sticky="ew", pady=(4, 0))
        ttk.Button(buttons, text="添加", command=self._replace_add).pack(side="left")
        ttk.Button(buttons, text="更新", command=self._replace_update).pack(side="left", padx=4)
        ttk.Button(buttons, text="删除", command=self._replace_delete).pack(side="left")
        ttk.Button(buttons, text="导出 JSON", command=self._replace_export).pack(side="right")
        ttk.Button(buttons, text="从 JSON 导入", command=self._replace_import).pack(
            side="right", padx=4
        )

        self.replace_tree.bind("<Double-1>", self._replace_load_row)

    def _selected_replace(self) -> str:
        selected = self.replace_tree.selection()
        return selected[0] if selected else ""

    def _replace_load_row(self, event=None) -> None:
        iid = self._selected_replace()
        if not iid:
            return
        pattern, replace, scope = self.replace_tree.item(iid, "values")
        self.v_rp.set(pattern)
        self.v_rr.set(replace)
        self.v_rs.set(scope)

    def _replace_values(self) -> tuple[str, str, str]:
        return (self.v_rp.get().strip(), self.v_rr.get(), self.v_rs.get())

    def _replace_add(self) -> None:
        if not self.v_rp.get().strip():
            messagebox.showwarning("添加规则", "正则查找不能为空")
            return
        self.replace_tree.insert("", "end", values=self._replace_values())

    def _replace_update(self) -> None:
        iid = self._selected_replace()
        if iid:
            self.replace_tree.item(iid, values=self._replace_values())

    def _replace_delete(self) -> None:
        iid = self._selected_replace()
        if iid:
            self.replace_tree.delete(iid)

    def _replace_import(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("JSON", "*.json"), ("所有文件", "*.*")])
        if not path:
            return
        try:
            rules = rules_from_json(Path(path).read_text(encoding="utf-8"))
        except ValueError as e:
            messagebox.showerror("导入替换规则", str(e))
            return
        for rule in rules:
            self.replace_tree.insert(
                "", "end", values=(rule.pattern, rule.replace, SCOPE_LABELS[rule.scope])
            )

    def _replace_export(self) -> None:
        path = filedialog.asksaveasfilename(
            defaultextension=".json", filetypes=[("JSON", "*.json")]
        )
        if not path:
            return
        rows = [
            (pattern, replace, scope)
            for pattern, replace, scope in (
                self.replace_tree.item(iid, "values") for iid in self.replace_tree.get_children()
            )
            if pattern
        ]
        try:
            text = replacement_json(rows)
        except ValueError as e:
            messagebox.showerror("导出替换规则", str(e))
            return
        try:
            write_text(Path(path), text + "\n")
        except ValueError as e:
            messagebox.showerror("导出替换规则", str(e))

    # ---------- 文件选择 ----------

    def _browse(self, opt: Option) -> None:
        """路径类选项都给一个文件对话框；输入文件选完顺手猜书名和作者。"""
        if opt.name == "out":
            path = filedialog.asksaveasfilename(
                defaultextension=".epub", filetypes=[("EPUB", "*.epub")]
            )
        else:
            path = filedialog.askopenfilename(filetypes=[("所有文件", "*.*")])
        if not path:
            return
        self.vars[opt.name].set(path)
        if opt.name == "input":
            # 填过的书名/作者优先，否则从文件名猜（猜不到退回文件名本身）
            title, author = resolve_metadata(
                Path(path), self.vars["title"].get().strip(), self.vars["author"].get().strip()
            )
            self.vars["title"].set(title)
            self.vars["author"].set(author)

    # ---------- 动作 ----------

    def _run(self, fn):
        try:
            return fn()
        except ValueError as e:
            messagebox.showerror(DIST_NAME, str(e))
            return None

    def do_preview(self) -> None:
        result = self._run(lambda: preview_data(self._fields()))
        if result is None:
            return
        tree, shown = result
        self.preview_tree.delete(*self.preview_tree.get_children())

        def add(nodes: list[dict], parent: str = "") -> None:
            for node in nodes:
                depth = node["level"]
                raw = node["raw_title"]
                iid = self.preview_tree.insert(
                    parent, "end", text="  " * min(depth - 1, 3), values=(raw, shown(raw))
                )
                add(node["children"], iid)

        add(tree)
        self.v_status.set("目录预览已刷新")

    def do_generate(self) -> None:
        self.root.config(cursor="watch")
        try:
            out = generate_output(self._fields())
        except ValueError as e:
            self.root.config(cursor="")
            self.v_status.set("生成失败")
            messagebox.showerror(DIST_NAME, str(e))
            return
        self.root.config(cursor="")
        self.v_status.set(f"已生成：{out}")
        messagebox.showinfo(DIST_NAME, f"已生成：\n{out}")

    def _build_preview(self, pane: ttk.Panedwindow) -> None:
        frame = ttk.Frame(pane, padding=4)
        pane.add(frame, weight=2)
        ttk.Label(frame, text="目录预览（原始 → 替换后）").pack(anchor="w")
        self.preview_tree = ttk.Treeview(frame, columns=("raw", "title"), show="tree headings")
        self.preview_tree.heading("raw", text="原始标题")
        self.preview_tree.heading("title", text="替换后")
        self.preview_tree.column("raw", width=260)
        self.preview_tree.column("title", width=260)
        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=self.preview_tree.yview)
        self.preview_tree.configure(yscrollcommand=scrollbar.set)
        self.preview_tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")


def main() -> None:
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
