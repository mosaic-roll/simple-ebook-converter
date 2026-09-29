"""Simple Ebook Converter — GUI 骨架（CTk 布局版，无业务逻辑）

依赖：customtkinter
    pip install "simple-ebook-converter[gui-ctk]"
"""

from __future__ import annotations

import os
import subprocess
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import customtkinter as ctk


# ---------- 跨平台：用系统默认程序打开文件 ----------
def open_with_default_app(path: str) -> None:
    if not path or not os.path.exists(path):
        raise FileNotFoundError(path)
    if sys.platform == "win32":
        os.startfile(path)  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.run(["open", path], check=False)
    else:
        subprocess.run(["xdg-open", path], check=False)


class App(ctk.CTk):
    PAD = 10
    GAP = 8
    ALIGNS = ["left", "center", "right"]
    HEADINGS = ["h1", "h2", "h3", "h4", "h5", "h6"]

    def __init__(self):
        super().__init__()
        self.title("Simple Ebook Converter")
        self.geometry("720x680")
        self.minsize(640, 600)

        ctk.set_appearance_mode("light")
        ctk.set_default_color_theme("blue")

        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self._build_topbar()
        self._build_main()
        self._build_bottombar()

    # ==================== 顶部栏 ====================
    def _build_topbar(self):
        bar = ctk.CTkFrame(self, height=44, corner_radius=0)
        bar.grid(row=0, column=0, sticky="ew")
        bar.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            bar, text="  Simple Ebook Converter",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).grid(row=0, column=0, sticky="w", padx=14, pady=8)

        self.theme_seg = ctk.CTkSegmentedButton(
            bar, values=["浅色", "深色"], command=self._on_theme_change,
        )
        self.theme_seg.set("浅色")
        self.theme_seg.grid(row=0, column=1, sticky="e", padx=14, pady=6)

    def _on_theme_change(self, value: str):
        ctk.set_appearance_mode("dark" if value == "深色" else "light")

    # ==================== 主体 ====================
    def _build_main(self):
        main = ctk.CTkFrame(self, fg_color="transparent")
        main.grid(row=1, column=0, sticky="nsew", padx=self.PAD, pady=(self.PAD, 0))
        main.grid_rowconfigure(0, weight=1)
        main.grid_columnconfigure(0, weight=1)
        main.grid_columnconfigure(1, weight=0)

        self.tabs = ctk.CTkTabview(main)
        self.tabs.grid(row=0, column=0, sticky="nsew", padx=(0, self.GAP))
        for name in ("基础", "规则", "排版", "替换"):
            self.tabs.add(name)

        self._build_basic_tab(self.tabs.tab("基础"))
        self._build_rules_tab(self.tabs.tab("规则"))
        self._build_layout_tab(self.tabs.tab("排版"))
        self._build_replace_tab(self.tabs.tab("替换"))

        self._build_toc_panel(main)

    # ---------- 基础 Tab ----------
    def _build_basic_tab(self, parent):
        parent.grid_columnconfigure(0, weight=1)

        # 文件
        f = self._group(parent, "文件", 0)
        f.grid_columnconfigure(1, weight=1)
        self.input_entry = self._file_row(f, 1, "源文件", self._pick_input)
        self.output_entry = self._file_row(f, 2, "目标  ", self._pick_output)
        ctk.CTkLabel(f, text="编码", anchor="e").grid(
            row=3, column=0, padx=(10, 6), pady=6, sticky="e")
        self.encoding_menu = ctk.CTkOptionMenu(
            f, values=["auto", "utf-8", "gb18030", "big5", "shift_jis", "euc_jp"])
        self.encoding_menu.set("auto")
        self.encoding_menu.grid(row=3, column=1, columnspan=2,
                                padx=(0, 10), pady=6, sticky="ew")

        # 书籍信息（2×2）
        m = self._group(parent, "书籍信息", 1)
        for c in (1, 3):
            m.grid_columnconfigure(c, weight=1)
        self.book_title = self._label_entry(m, 1, 0, "书名", "书名")
        self.book_author = self._label_entry(m, 1, 2, "作者", "作者")
        self.book_date = self._label_entry(m, 2, 0, "日期", "2024-05-13")
        ctk.CTkLabel(m, text="语言", anchor="e").grid(
            row=2, column=2, padx=(10, 6), pady=6, sticky="e")
        self.lang_menu = ctk.CTkOptionMenu(m, values=["zh", "en", "jp"])
        self.lang_menu.set("zh")
        self.lang_menu.grid(row=2, column=3, padx=(0, 10), pady=6, sticky="ew")

        # 封面
        c = self._group(parent, "封面", 2)
        c.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(c, text="路径", anchor="e").grid(
            row=1, column=0, padx=(10, 6), pady=6, sticky="e")
        self.cover_entry = ctk.CTkEntry(c)
        self.cover_entry.grid(row=1, column=1, pady=6, sticky="ew")
        ctk.CTkButton(c, text="浏览", width=60, command=self._pick_cover).grid(
            row=1, column=2, padx=(6, 4), pady=6)
        ctk.CTkButton(c, text="打开", width=60, command=self._open_cover).grid(
            row=1, column=3, padx=(0, 10), pady=6)
        self.text_cover_var = tk.BooleanVar(value=True)
        ctk.CTkCheckBox(c, text="无封面时生成文字封面",
                        variable=self.text_cover_var).grid(
            row=2, column=0, columnspan=4, padx=10, pady=(0, 10), sticky="w")

    # ---------- 规则 Tab ----------
    def _build_rules_tab(self, parent):
        parent.grid_columnconfigure(0, weight=1)

        b = self._group(parent, "基础规则", 0)
        b.grid_columnconfigure(1, weight=1)
        rows = [
            ("卷", "^第…[卷部]"),
            ("章", "^第…[章节回]"),
            ("节", ""),
            ("字数上限", "35"),
            ("无标题章节", "前言"),
        ]
        self.rules_entries = []
        for i, (label, hint) in enumerate(rows, start=1):
            ctk.CTkLabel(b, text=label, anchor="e").grid(
                row=i, column=0, padx=(10, 6), pady=6, sticky="e")
            e = ctk.CTkEntry(b, placeholder_text=hint)
            e.grid(row=i, column=1, padx=(0, 10), pady=6, sticky="ew")
            self.rules_entries.append(e)

        a = self._group(parent, "额外规则", 1)
        a.grid_columnconfigure(0, weight=1)
        self.extra_rows = []
        for i in range(2):
            self.extra_rows.append(self._extra_level_row(a, i + 1))

        btns = ctk.CTkFrame(a, fg_color="transparent")
        btns.grid(row=99, column=0, pady=(4, 10))
        ctk.CTkButton(btns, text="＋ 添加", width=90,
                      command=self._add_extra_rule).pack(side="left", padx=4)
        ctk.CTkButton(btns, text="－ 删除", width=90,
                      command=self._remove_extra_rule).pack(side="left", padx=4)

    def _extra_level_row(self, parent, r):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.grid(row=r, column=0, sticky="ew", padx=10, pady=4)
        row.grid_columnconfigure(2, weight=1)
        level = ctk.CTkOptionMenu(row, values=self.HEADINGS, width=70)
        level.set("h2")
        level.grid(row=0, column=0, padx=(0, 6))
        cls = ctk.CTkEntry(row, width=80, placeholder_text="class")
        cls.grid(row=0, column=1, padx=(0, 6))
        regex = ctk.CTkEntry(row, placeholder_text="正则")
        regex.grid(row=0, column=2, sticky="ew")
        return row

    # ---------- 排版 Tab ----------
    def _build_layout_tab(self, parent):
        parent.grid_columnconfigure(0, weight=1)

        # 段落 2×2
        p = self._group(parent, "段落", 0)
        for c in (1, 3):
            p.grid_columnconfigure(c, weight=1)
        self.indent = self._label_entry(p, 1, 0, "缩进", "2")
        self.line_height = self._label_entry(p, 1, 2, "行高", "1.5")
        self.para_spacing = self._label_entry(p, 2, 0, "段间距", "1em")
        self.margin = self._label_entry(p, 2, 2, "页边距", "20")

        # 对齐方式 2×2
        al = self._group(parent, "对齐方式", 1)
        for c in (1, 3):
            al.grid_columnconfigure(c, weight=1)
        self.align_volume = self._align_row(al, 1, 0, "卷", "center")
        self.align_chapter = self._align_row(al, 1, 2, "章", "center")
        self.align_section = self._align_row(al, 2, 0, "节", "left")
        self.align_body = self._align_row(al, 2, 2, "正文", "left")

        # 嵌入字体
        fo = self._group(parent, "嵌入字体", 2)
        fo.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(fo, text="路径", anchor="e").grid(
            row=1, column=0, padx=(10, 6), pady=6, sticky="e")
        self.font_entry = ctk.CTkEntry(fo)
        self.font_entry.grid(row=1, column=1, pady=6, sticky="ew")
        ctk.CTkButton(fo, text="浏览", width=60,
                      command=self._pick_font).grid(
            row=1, column=2, padx=(6, 10), pady=6)

        # 自定义 CSS
        css = self._group(parent, "自定义 CSS", 3)
        css.grid_columnconfigure(0, weight=1)
        css.grid_rowconfigure(1, weight=1)
        self.css_mode = ctk.CTkSegmentedButton(css, values=["忽略", "追加", "覆盖"])
        self.css_mode.set("忽略")
        self.css_mode.grid(row=0, column=0, padx=10, pady=(6, 4), sticky="w")
        self.css_text = ctk.CTkTextbox(css, height=160)
        self.css_text.grid(row=1, column=0, padx=10, pady=(0, 10), sticky="nsew")

        parent.grid_rowconfigure(3, weight=1)  # CSS 块可随 Tab 拉高

    # ---------- 替换 Tab ----------
    def _build_replace_tab(self, parent):
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(0, weight=1)

        holder = ctk.CTkFrame(parent)
        holder.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        holder.grid_rowconfigure(0, weight=1)
        holder.grid_columnconfigure(0, weight=1)

        self.replace_table = ttk.Treeview(
            holder, columns=("enabled", "pattern", "replace", "stage"),
            show="headings", height=12,
        )
        for col, text, w in (
            ("enabled", "启用", 50),
            ("pattern", "正则", 200),
            ("replace", "替换为", 150),
            ("stage", "阶段", 60),
        ):
            self.replace_table.heading(col, text=text)
            self.replace_table.column(col, width=w, anchor="w")
        self.replace_table.grid(row=0, column=0, sticky="nsew")

        btns = ctk.CTkFrame(parent, fg_color="transparent")
        btns.grid(row=1, column=0, pady=(0, 10))
        for text in ("上移", "下移", "添加", "删除", "导入", "导出"):
            ctk.CTkButton(btns, text=text, width=60).pack(side="left", padx=4)

    # ---------- 右侧目录面板 ----------
    def _build_toc_panel(self, parent):
        panel = ctk.CTkFrame(parent, width=300)
        panel.grid(row=0, column=1, sticky="nsew")
        panel.grid_propagate(False)
        panel.grid_rowconfigure(1, weight=1)
        panel.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            panel, text="目录", font=ctk.CTkFont(size=13, weight="bold"),
        ).grid(row=0, column=0, sticky="w", padx=12, pady=(10, 4))

        self.toc_table = ttk.Treeview(
            panel, columns=("enabled", "title", "preview"),
            show="headings", height=16,
        )
        for col, text, w in (
            ("enabled", "启用", 50),
            ("title", "标题", 140),
            ("preview", "预览", 90),
        ):
            self.toc_table.heading(col, text=text)
            self.toc_table.column(col, width=w, anchor="w")
        self.toc_table.grid(row=1, column=0, sticky="nsew", padx=12)

        btns = ctk.CTkFrame(panel, fg_color="transparent")
        btns.grid(row=2, column=0, pady=8)
        ctk.CTkButton(btns, text="重新扫描", width=90).pack(side="left", padx=4)
        ctk.CTkButton(btns, text="导入", width=60).pack(side="left", padx=4)
        ctk.CTkButton(btns, text="导出", width=60).pack(side="left", padx=4)

        opts = ctk.CTkFrame(panel, fg_color="transparent")
        opts.grid(row=3, column=0, sticky="ew", padx=12, pady=(0, 4))
        ctk.CTkLabel(opts, text="目录深度").pack(side="left")
        self.toc_depth = ctk.CTkOptionMenu(
            opts, values=[str(i) for i in range(1, 7)], width=70)
        self.toc_depth.set("6")
        self.toc_depth.pack(side="left", padx=6)

        self.toc_in_book_var = tk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            panel, text="目录页出现在书中", variable=self.toc_in_book_var,
        ).grid(row=4, column=0, sticky="w", padx=12, pady=(0, 12))

    # ==================== 底部栏 ====================
    def _build_bottombar(self):
        bar = ctk.CTkFrame(self, height=52, corner_radius=0)
        bar.grid(row=2, column=0, sticky="ew", pady=(self.GAP, 0))
        bar.grid_columnconfigure(1, weight=1)

        ctk.CTkButton(
            bar, text="⚙  开始生成", width=140, height=32,
            font=ctk.CTkFont(weight="bold"),
            command=self._on_generate,
        ).grid(row=0, column=0, padx=14, pady=10, sticky="w")

        self.clean_var = tk.BooleanVar(value=True)
        ctk.CTkCheckBox(bar, text="清理文本",
                        variable=self.clean_var).grid(
            row=0, column=2, padx=14, pady=10, sticky="e")

    # ==================== 复用组件 ====================
    def _group(self, parent, title, row):
        frame = ctk.CTkFrame(parent, border_width=1, corner_radius=4)
        frame.grid(row=row, column=0, sticky="ew", padx=10, pady=(10, 0))
        frame.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            frame, text=title,
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=("gray30", "gray70"),
        ).grid(row=0, column=0, sticky="w", padx=10, pady=(6, 2))
        return frame

    def _file_row(self, parent, r, label, command):
        ctk.CTkLabel(parent, text=label, anchor="e").grid(
            row=r, column=0, padx=(10, 6), pady=6, sticky="e")
        entry = ctk.CTkEntry(parent)
        entry.grid(row=r, column=1, pady=6, sticky="ew")
        ctk.CTkButton(parent, text="浏览", width=60, command=command).grid(
            row=r, column=2, padx=(6, 10), pady=6)
        return entry

    def _label_entry(self, parent, r, c, label, placeholder=""):
        ctk.CTkLabel(parent, text=label, anchor="e").grid(
            row=r, column=c, padx=(10, 6), pady=6, sticky="e")
        entry = ctk.CTkEntry(parent, placeholder_text=placeholder)
        entry.grid(row=r, column=c + 1, padx=(0, 10), pady=6, sticky="ew")
        return entry

    def _align_row(self, parent, r, c, label, default):
        ctk.CTkLabel(parent, text=label, anchor="e").grid(
            row=r, column=c, padx=(10, 6), pady=6, sticky="e")
        menu = ctk.CTkOptionMenu(parent, values=self.ALIGNS)
        menu.set(default)
        menu.grid(row=r, column=c + 1, padx=(0, 10), pady=6, sticky="ew")
        return menu

    # ==================== 业务占位（全部 pass） ====================
    def _pick_input(self): ...
    def _pick_output(self): ...
    def _pick_cover(self): ...
    def _pick_font(self): ...
    def _on_generate(self): ...
    def _add_extra_rule(self): ...
    def _remove_extra_rule(self): ...

    # 这个是纯 UI，直接可用
    def _open_cover(self):
        path = self.cover_entry.get().strip()
        if not path:
            return
        try:
            open_with_default_app(path)
        except FileNotFoundError:
            messagebox.showerror("打开失败", f"文件不存在：\n{path}")


if __name__ == "__main__":
    App().mainloop()
