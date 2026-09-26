from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from sec.core.builder import build_css, build_epub
from sec.core.config import ALIGN_CHOICES, Config, config_defaults
from sec.core.encoding import ENCODING_CHOICES, read_lines
from sec.core.levels import build_levels
from sec.core.meta import resolve_metadata
from sec.core.pipeline import process
from sec.core.replace import (
    DEFAULT_SCOPE,
    SCOPE_CHOICES,
    SCOPE_LABELS,
    Rule,
    rules_from_json,
)
from sec.core.toc import to_json

#: 编码下拉框直接用 core 的候选链，core 加编码这里自动跟着变
_ENCODINGS = list(ENCODING_CHOICES)

#: 字段缺省值取自 sec.core 的 Config，界面不再另写一份字面量
_DEFAULTS = config_defaults()

#: 作用范围下拉框用 core 的中文标签，两个方向都齐全
_SCOPE_BY_LABEL = {label: scope for scope, label in SCOPE_LABELS.items()}
_SCOPE_LABELS_TUPLE = tuple(SCOPE_LABELS[s] for s in SCOPE_CHOICES)
_DEFAULT_SCOPE_LABEL = SCOPE_LABELS[DEFAULT_SCOPE]


def split_extra(text: str) -> tuple[str, ...]:
    """把「每行一条 级别:正则[:类名]」拆成规则元组。"""
    return tuple(line.strip() for line in text.splitlines() if line.strip())


def _parse_replacements(rows: list) -> list[Rule]:
    """把替换表格的行元组 `(查找, 替换为, 作用范围)` 变成 Rule；留空查找的行忽略。"""
    rules: list[Rule] = []
    for pattern, replace, scope in rows:
        if not pattern:
            continue
        try:
            resolved = _SCOPE_BY_LABEL[scope]
        except KeyError:
            raise ValueError(
                f"替换规则「{pattern}」的作用范围只能是 {'/'.join(_SCOPE_LABELS_TUPLE)}，"
                f"收到：{scope!r}"
            ) from None
        rules.append(Rule(pattern, replace, resolved))
    return rules


def make_config(fields: dict) -> Config:
    """把界面字段合并成 Config，出错抛 ValueError。GUI 与测试共用。"""
    src = Path(fields["input"])
    if not src.is_file():
        raise ValueError(f"输入文件不存在：{src}")

    try:
        max_title_len = int(fields["max_title_len"])
        toc_depth = int(fields.get("toc_depth", _DEFAULTS["toc_depth"]))
        indent = int(fields.get("indent", _DEFAULTS["indent"]))
    except (TypeError, ValueError) as e:
        raise ValueError("数字字段格式错误（标题最长/目录深度/段落缩进）") from e

    levels = build_levels(
        fields.get("volume") or None,
        fields.get("chapter") or None,
        fields.get("section") or None,
        split_extra(fields.get("extra_levels", "")),
    )
    replacements = _parse_replacements(fields.get("replacements", []))

    cover = (fields.get("cover") or "").strip()
    if cover and not Path(cover).is_file():
        raise ValueError(f"封面文件不存在：{cover}")

    return Config(
        input=src,
        encoding=fields.get("encoding") or _DEFAULTS["encoding"],
        overwrite=not bool(fields.get("no_overwrite")),
        title=fields.get("title") or None,
        author=fields.get("author") or "",
        date=(fields.get("date") or "").strip() or None,
        language=fields.get("language") or _DEFAULTS["language"],
        cover=Path(cover) if cover else None,
        levels=levels,
        max_title_len=max_title_len,
        preface_title=fields.get("preface_title") or _DEFAULTS["preface_title"],
        no_volume=bool(fields.get("no_volume")),
        replacements=replacements,
        no_clean=bool(fields.get("no_clean")),
        no_toc=bool(fields.get("no_toc")),
        toc_depth=toc_depth,
        indent=indent,
        line_height=fields.get("line_height") or _DEFAULTS["line_height"],
        para_spacing=fields.get("para_spacing") or _DEFAULTS["para_spacing"],
        chapter_align=fields.get("chapter_align") or _DEFAULTS["chapter_align"],
        volume_align=fields.get("volume_align") or _DEFAULTS["volume_align"],
        font=None,
        css_file=None,
    )


def preview_data(fields: dict) -> list[dict]:
    """按当前设置解析目录树（JSON 列表），供预览与测试。"""
    cfg = make_config(fields)
    src = cfg.input
    lines, _used = read_lines(src, cfg.encoding)
    tree, _stats = process(lines, cfg)
    return to_json(tree, cfg.toc_depth)


def build_book(fields: dict) -> Path:
    """按当前设置生成 EPUB，返回输出路径，出错抛 ValueError。"""
    cfg = make_config(fields)
    src = cfg.input
    lines, _used = read_lines(src, cfg.encoding)
    tree, _stats = process(lines, cfg)
    if not tree:
        raise ValueError("没有可生成的内容（文件为空或全是空行）")

    out_raw = (fields.get("output") or "").strip()
    out = Path(out_raw) if out_raw else src.with_suffix(".epub")
    if out.suffix.lower() != ".epub":
        out = out.with_name(out.name + ".epub")
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists() and not cfg.overwrite:
        raise ValueError(f"输出文件已存在：{out}")

    build_epub(cfg, tree, build_css(cfg), out)
    return out


class SecGui:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        root.title("sec-gui — TXT 电子书生成器")
        root.geometry("1100x740")

        self._build_vars()
        self._build_ui()

    # ---------- 变量 ----------
    def _build_vars(self) -> None:
        d = config_defaults()
        self.v_input = tk.StringVar()
        self.v_output = tk.StringVar()
        self.v_encoding = tk.StringVar(value=d["encoding"])
        self.v_no_overwrite = tk.BooleanVar(value=d["no_overwrite"])
        self.v_title = tk.StringVar(value=d["title"])
        self.v_author = tk.StringVar(value=d["author"])
        self.v_date = tk.StringVar(value=d["date"])
        self.v_language = tk.StringVar(value=d["language"])
        self.v_cover = tk.StringVar()
        self.v_volume = tk.StringVar(value=d["volume"])
        self.v_chapter = tk.StringVar(value=d["chapter"])
        self.v_section = tk.StringVar(value=d["section"])
        self.v_no_volume = tk.BooleanVar(value=d["no_volume"])
        self.v_extra_levels = tk.StringVar()
        self.v_max_title_len = tk.IntVar(value=d["max_title_len"])
        self.v_preface_title = tk.StringVar(value=d["preface_title"])
        self.v_no_clean = tk.BooleanVar(value=d["no_clean"])
        self.v_no_toc = tk.BooleanVar(value=d["no_toc"])
        self.v_toc_depth = tk.IntVar(value=d["toc_depth"])
        self.v_indent = tk.IntVar(value=d["indent"])
        self.v_line_height = tk.StringVar(value=d["line_height"])
        self.v_para_spacing = tk.StringVar(value=d["para_spacing"])
        self.v_chapter_align = tk.StringVar(value=d["chapter_align"])
        self.v_volume_align = tk.StringVar(value=d["volume_align"])
        self.v_status = tk.StringVar(value="就绪")

    def _fields(self) -> dict:
        extra = "\n".join(self.extra_text.get("1.0", "end").splitlines())
        rows = [
            tuple(self.replace_tree.item(iid, "values")) or ("", "", _DEFAULT_SCOPE_LABEL)
            for iid in self.replace_tree.get_children()
        ]
        return {
            "input": self.v_input.get().strip(),
            "output": self.v_output.get().strip(),
            "encoding": self.v_encoding.get(),
            "no_overwrite": self.v_no_overwrite.get(),
            "title": self.v_title.get(),
            "author": self.v_author.get(),
            "date": self.v_date.get(),
            "language": self.v_language.get(),
            "cover": self.v_cover.get(),
            "volume": self.v_volume.get(),
            "chapter": self.v_chapter.get(),
            "section": self.v_section.get(),
            "no_volume": self.v_no_volume.get(),
            "extra_levels": extra,
            "max_title_len": self.v_max_title_len.get(),
            "preface_title": self.v_preface_title.get(),
            "replacements": rows,
            "no_clean": self.v_no_clean.get(),
            "no_toc": self.v_no_toc.get(),
            "toc_depth": self.v_toc_depth.get(),
            "indent": self.v_indent.get(),
            "line_height": self.v_line_height.get(),
            "para_spacing": self.v_para_spacing.get(),
            "chapter_align": self.v_chapter_align.get(),
            "volume_align": self.v_volume_align.get(),
        }

    # ---------- 界面 ----------
    def _build_ui(self) -> None:
        top = ttk.Frame(self.root, padding=(8, 8))
        top.grid(row=0, column=0, sticky="ew")
        self.root.columnconfigure(0, weight=1)

        ttk.Label(top, text="输入 TXT").grid(row=0, column=0, sticky="w")
        ttk.Entry(top, textvariable=self.v_input).grid(row=0, column=1, sticky="ew", padx=4)
        ttk.Button(top, text="浏览", command=self._browse_input).grid(row=0, column=2)
        ttk.Label(top, text="输出(留空自动)").grid(row=1, column=0, sticky="w", pady=(4, 0))
        ttk.Entry(top, textvariable=self.v_output).grid(row=1, column=1, sticky="ew", padx=4, pady=(4, 0))
        ttk.Button(top, text="浏览", command=self._browse_output).grid(row=1, column=2, pady=(4, 0))
        top.columnconfigure(1, weight=1)

        pane = ttk.Panedwindow(self.root, orient=tk.HORIZONTAL)
        pane.grid(row=1, column=0, sticky="nsew", padx=8, pady=8)
        self.root.rowconfigure(1, weight=1)

        left = ttk.Notebook(pane)
        pane.add(left, weight=3)
        self._build_tab_meta(left)
        self._build_tab_chapter(left)
        self._build_tab_replace(left)
        self._build_tab_output(left)

        self._build_preview(pane)

        bar = ttk.Frame(self.root, padding=(8, 0, 8, 8))
        bar.grid(row=2, column=0, sticky="ew")
        ttk.Label(bar, textvariable=self.v_status).pack(side="left")
        ttk.Button(bar, text="刷新目录预览", command=self.do_preview).pack(side="right", padx=4)
        ttk.Button(bar, text="生成 EPUB", command=self.do_generate).pack(side="right")

    def _grid(self, parent: ttk.Frame, rows: list[tuple[str, tk.Widget]]) -> None:
        for r, (label, widget) in enumerate(rows):
            ttk.Label(parent, text=label).grid(row=r, column=0, sticky="w", pady=2)
            widget.grid(row=r, column=1, sticky="ew", pady=2, padx=4)
        parent.columnconfigure(1, weight=1)

    def _build_tab_meta(self, nb: ttk.Notebook) -> None:
        f = ttk.Frame(nb, padding=8)
        nb.add(f, text="元数据")
        self._grid(f, [
            ("书名", ttk.Entry(f, textvariable=self.v_title)),
            ("作者", ttk.Entry(f, textvariable=self.v_author)),
            ("日期", ttk.Entry(f, textvariable=self.v_date)),
            ("语言", ttk.Entry(f, textvariable=self.v_language)),
            ("编码", ttk.Combobox(f, textvariable=self.v_encoding, values=_ENCODINGS, state="readonly")),
        ])
        row = len(f.grid_slaves()) + 1
        ttk.Label(f, text="封面").grid(row=row, column=0, sticky="w", pady=2)
        ttk.Entry(f, textvariable=self.v_cover).grid(row=row, column=1, sticky="ew", padx=4, pady=2)
        ttk.Button(f, text="浏览", command=self._browse_cover).grid(row=row, column=2, sticky="w")

    def _build_tab_chapter(self, nb: ttk.Notebook) -> None:
        f = ttk.Frame(nb, padding=8)
        nb.add(f, text="章节")
        self._grid(f, [
            ("卷正则", ttk.Entry(f, textvariable=self.v_volume)),
            ("章正则", ttk.Entry(f, textvariable=self.v_chapter)),
            ("节正则", ttk.Entry(f, textvariable=self.v_section)),
            ("标题最长字数", ttk.Spinbox(f, from_=1, to=1000, textvariable=self.v_max_title_len)),
            ("前言名", ttk.Entry(f, textvariable=self.v_preface_title)),
        ])
        ttk.Checkbutton(f, text="无卷模式（卷不作为标题）", variable=self.v_no_volume).grid(
            row=7, column=0, columnspan=2, sticky="w", pady=2
        )
        ttk.Label(f, text="额外层级（每行一条：级别:正则[:类名]，如 1:^第一卷:volume）").grid(
            row=8, column=0, columnspan=3, sticky="w", pady=(6, 0)
        )
        self.extra_text = tk.Text(f, height=4)
        self.extra_text.grid(row=9, column=0, columnspan=3, sticky="ew", pady=2)
        self.extra_text.insert("1.0", self.v_extra_levels.get())
        f.columnconfigure(1, weight=1)

    def _build_tab_replace(self, nb: ttk.Notebook) -> None:
        f = ttk.Frame(nb, padding=8)
        nb.add(f, text="替换规则")
        ttk.Label(
            f,
            text="按顺序生效；作用范围默认「标题」，留空 pattern 的行被忽略",
        ).pack(anchor="w")

        self.replace_tree = ttk.Treeview(
            f, columns=("pattern", "replace", "scope"), show="headings", height=8
        )
        self.replace_tree.heading("pattern", text="正则查找")
        self.replace_tree.heading("replace", text="替换为")
        self.replace_tree.heading("scope", text="作用范围")
        self.replace_tree.column("pattern", width=200)
        self.replace_tree.column("replace", width=200)
        self.replace_tree.column("scope", width=80)
        self.replace_tree.pack(fill="both", expand=True, pady=4)

        self.v_rp = tk.StringVar()
        self.v_rr = tk.StringVar()
        self.v_rs = tk.StringVar(value=_DEFAULT_SCOPE_LABEL)
        edit = ttk.Frame(f)
        edit.pack(fill="x")
        ttk.Label(edit, text="查找").pack(side="left")
        ttk.Entry(edit, textvariable=self.v_rp).pack(side="left", fill="x", expand=True, padx=4)
        ttk.Label(edit, text="替换为").pack(side="left")
        ttk.Entry(edit, textvariable=self.v_rr).pack(side="left", fill="x", expand=True, padx=4)
        ttk.Label(edit, text="范围").pack(side="left", padx=(8, 0))
        ttk.Combobox(
            edit,
            textvariable=self.v_rs,
            values=list(_SCOPE_LABELS_TUPLE),
            state="readonly",
            width=6,
        ).pack(side="left", padx=4)

        btns = ttk.Frame(f)
        btns.pack(fill="x", pady=(4, 0))
        ttk.Button(btns, text="添加", command=self._replace_add).pack(side="left")
        ttk.Button(btns, text="更新", command=self._replace_update).pack(side="left", padx=4)
        ttk.Button(btns, text="删除", command=self._replace_delete).pack(side="left")
        ttk.Button(btns, text="从 JSON 导入", command=self._replace_import).pack(side="right")

        self.replace_tree.bind("<Double-1>", self._replace_load_row)

    def _build_tab_output(self, nb: ttk.Notebook) -> None:
        f = ttk.Frame(nb, padding=8)
        nb.add(f, text="输出")
        self._grid(f, [
            ("行高", ttk.Entry(f, textvariable=self.v_line_height)),
            ("段间距", ttk.Entry(f, textvariable=self.v_para_spacing)),
        ("章对齐", ttk.Combobox(f, textvariable=self.v_chapter_align, values=list(ALIGN_CHOICES), state="readonly")),
        ("卷对齐", ttk.Combobox(f, textvariable=self.v_volume_align, values=list(ALIGN_CHOICES), state="readonly")),
            ("目录深度", ttk.Spinbox(f, from_=1, to=6, textvariable=self.v_toc_depth)),
            ("段落缩进", ttk.Spinbox(f, from_=0, to=10, textvariable=self.v_indent)),
        ])
        ttk.Checkbutton(f, text="不覆盖已存在文件", variable=self.v_no_overwrite).grid(
            row=7, column=0, columnspan=2, sticky="w", pady=2
        )
        ttk.Checkbutton(f, text="目录不出现在书页中", variable=self.v_no_toc).grid(
            row=8, column=0, columnspan=2, sticky="w", pady=2
        )
        ttk.Checkbutton(f, text="关闭默认清理（保留空行等）", variable=self.v_no_clean).grid(
            row=9, column=0, columnspan=2, sticky="w", pady=2
        )

    def _build_preview(self, pane: ttk.Panedwindow) -> None:
        f = ttk.Frame(pane, padding=4)
        pane.add(f, weight=2)
        ttk.Label(f, text="目录预览（原始 → 替换后）").pack(anchor="w")
        self.preview_tree = ttk.Treeview(f, columns=("raw", "title"), show="tree headings")
        self.preview_tree.heading("raw", text="原始标题")
        self.preview_tree.heading("title", text="替换后")
        self.preview_tree.column("raw", width=260)
        self.preview_tree.column("title", width=260)
        sy = ttk.Scrollbar(f, orient="vertical", command=self.preview_tree.yview)
        self.preview_tree.configure(yscrollcommand=sy.set)
        self.preview_tree.pack(side="left", fill="both", expand=True)
        sy.pack(side="right", fill="y")

    def _selected_replace(self) -> str:
        sel = self.replace_tree.selection()
        return sel[0] if sel else ""

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

    def _browse_input(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("TXT 文本", "*.txt"), ("所有文件", "*.*")])
        if not path:
            return
        self.v_input.set(path)
        p = Path(path)
        # 已在输入框里填过的书名/作者优先，否则从文件名猜（猜不到退回文件名本身）
        title, author = resolve_metadata(p, self.v_title.get().strip(), self.v_author.get().strip())
        self.v_title.set(title)
        self.v_author.set(author)
        if not self.v_output.get():
            self.v_output.set(str(p.with_suffix("")))

    def _browse_output(self) -> None:
        path = filedialog.asksaveasfilename(defaultextension=".epub", filetypes=[("EPUB", "*.epub")])
        if path:
            self.v_output.set(Path(path).with_suffix("").as_posix())

    def _browse_cover(self) -> None:
        path = filedialog.askopenfilename(
            filetypes=[("图片", "*.jpg *.jpeg *.png *.webp *.avif"), ("所有文件", "*.*")]
        )
        if path:
            self.v_cover.set(path)

    def _run(self, fn) -> None:
        try:
            fn()
        except ValueError as e:
            messagebox.showerror("sec-gui", str(e))

    def do_preview(self) -> None:
        tree = []
        self._run(lambda: tree.extend(preview_data(self._fields())))
        if not tree:
            return
        self.preview_tree.delete(*self.preview_tree.get_children())

        def add(nodes: list[dict], parent: str = "") -> None:
            for node in nodes:
                depth = node["level"]
                raw = node["raw_title"] or node["title"]
                iid = self.preview_tree.insert(
                    parent, "end", text="  " * min(depth - 1, 3), values=(raw, node["title"])
                )
                add(node["children"], iid)

        add(tree)
        self.v_status.set("目录预览已刷新")

    def do_generate(self) -> None:
        self.root.config(cursor="watch")
        try:
            out = build_book(self._fields())
        except ValueError as e:
            self.root.config(cursor="")
            messagebox.showerror("sec-gui", str(e))
            self.v_status.set("生成失败")
            return
        self.root.config(cursor="")
        self.v_status.set(f"已生成：{out}")
        messagebox.showinfo("sec-gui", f"已生成：\n{out}")


def main() -> None:
    root = tk.Tk()
    SecGui(root)
    root.mainloop()


if __name__ == "__main__":
    main()
