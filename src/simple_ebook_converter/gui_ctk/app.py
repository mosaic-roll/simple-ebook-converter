"""Simple Ebook Converter — GUI 骨架（CTk 布局版，无业务逻辑）

依赖：customtkinter, tksheet
    pip install customtkinter tksheet
"""

from __future__ import annotations

import os
import subprocess
import sys
import tkinter as tk
from tkinter import messagebox

import customtkinter as ctk
from tksheet import Sheet


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
    PAD = 6
    GAP = 6
    ALIGNS = ["left", "center", "right"]
    HEADINGS = ["h1", "h2", "h3", "h4", "h5", "h6"]

    # 行内间距（统一在这里改）
    LABEL_PADX = (10, 6)
    FIELD_PADX = (0, 10)
    BTN_PADX = (6, 10)
    ROW_PADY = 5

    # 替换规则阶段
    STAGES = ["raw", "html"]

    def __init__(self):
        super().__init__()
        self.title("Simple Ebook Converter")
        self.geometry("900x720")
        self.minsize(720, 600)

        ctk.set_appearance_mode("light")
        ctk.set_default_color_theme("blue")

        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self._build_topbar()
        self._build_main()
        self._build_bottombar()

    # ==================== 顶部栏 ====================
    def _build_topbar(self):
        bar = ctk.CTkFrame(self, height=40, corner_radius=0)
        bar.grid(row=0, column=0, sticky="ew")
        bar.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            bar,
            text="Simple Ebook Converter",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).grid(row=0, column=0, sticky="w", padx=14, pady=6)

        self.theme_seg = ctk.CTkSegmentedButton(
            bar,
            values=["浅色", "深色"],
            command=self._on_theme_change,
        )
        self.theme_seg.set("浅色")
        self.theme_seg.grid(row=0, column=1, sticky="e", padx=14, pady=6)

    def _on_theme_change(self, value: str):
        ctk.set_appearance_mode("dark" if value == "深色" else "light")

    # ==================== 主体 ====================
    def _build_main(self):
        self.main = ctk.CTkFrame(self, fg_color="transparent")
        self.main.grid(
            row=1, column=0, sticky="nsew", padx=self.PAD, pady=(self.PAD, 0)
        )
        self.main.grid_rowconfigure(0, weight=1)
        # 左右各 50%，比例固定
        self.main.grid_columnconfigure(0, weight=1, uniform="col")
        self.main.grid_columnconfigure(1, weight=1, uniform="col")

        self.tabs = ctk.CTkTabview(self.main, border_width=0)
        self.tabs.grid(row=0, column=0, sticky="nsew", padx=(0, self.GAP // 2))
        for name in ("基础", "规则", "排版", "替换"):
            self.tabs.add(name)

        self._build_basic_tab(self.tabs.tab("基础"))
        self._build_rules_tab(self.tabs.tab("规则"))
        self._build_layout_tab(self.tabs.tab("排版"))
        self._build_replace_tab(self.tabs.tab("替换"))

        self._build_toc_panel(self.main)

    # ==================== 基础 Tab ====================
    def _build_basic_tab(self, parent):
        parent.grid_columnconfigure(0, weight=1)

        # 文件
        f = self._group(parent, "文件", 0)
        self.input_entry = self._field_btn(f, 1, "源文件", self._pick_input)
        self.output_entry = self._field_btn(f, 2, "目标", self._pick_output)
        self.encoding_menu = self._field_menu(
            f, 3, "编码", ["auto", "utf-8", "gb18030", "big5", "shift_jis", "euc_jp"]
        )

        # 书籍信息（2×2）
        m = self._group(parent, "书籍信息", 1)
        self.book_title = self._field(m, 1, "书名", "书名", col=0)
        self.book_author = self._field(m, 1, "作者", "作者", col=2)
        self.book_date = self._field(m, 2, "日期", "2024-05-13", col=0)
        self.lang_menu = self._field_menu(m, 2, "语言", ["zh", "en", "jp"], col=2)

        # 封面
        c = self._group(parent, "封面", 2)
        self.cover_entry = self._field_btn(
            c, 1, "路径", self._pick_cover, extra_btn=("查看", self._open_cover)
        )
        self.text_cover_var = tk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            c, text="无封面时生成文字封面", variable=self.text_cover_var
        ).grid(row=2, column=0, columnspan=4, padx=10, pady=(0, 10), sticky="w")

        # 其他
        o = self._group(parent, "其他", 3)
        self.clean_var = tk.BooleanVar(value=True)
        ctk.CTkCheckBox(o, text="清理段首空格及空行", variable=self.clean_var).grid(
            row=1, column=0, columnspan=4, padx=10, pady=(0, 10), sticky="w"
        )

    # ==================== 规则 Tab ====================
    def _build_rules_tab(self, parent):
        parent.grid_columnconfigure(0, weight=1)

        b = self._group(parent, "基础规则", 0)
        rows = ["卷", "章", "节", "字数上限", "无标题章节"]
        self.rule_entries: dict[str, ctk.CTkEntry] = {}
        for i, label in enumerate(rows, start=1):
            entry = self._field_btn(
                b,
                i,
                label,
                command=lambda lbl=label: self._restore_rule_default(lbl),
                btn_text="恢复默认",
                btn_width=80,
            )
            self.rule_entries[label] = entry

        a = self._group(parent, "额外规则", 1)
        self.extra_rows = []
        for i in range(2):
            self.extra_rows.append(self._extra_level_row(a, i + 1))

        btns = ctk.CTkFrame(a, fg_color="transparent")
        btns.grid(row=99, column=0, columnspan=4, pady=(4, 10))
        ctk.CTkButton(
            btns, text="＋ 添加", width=90, command=self._add_extra_rule
        ).pack(side="left", padx=4)
        ctk.CTkButton(
            btns, text="－ 删除", width=90, command=self._remove_extra_rule
        ).pack(side="left", padx=4)

    def _extra_level_row(self, parent, r):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.grid(row=r, column=0, columnspan=4, sticky="ew", padx=10, pady=4)
        row.grid_columnconfigure(2, weight=1)
        level = ctk.CTkOptionMenu(row, values=self.HEADINGS, width=70, anchor="center")
        level.set("h2")
        level.grid(row=0, column=0, padx=(0, 6))
        cls = ctk.CTkEntry(row, width=80, placeholder_text="class")
        cls.grid(row=0, column=1, padx=(0, 6))
        regex = ctk.CTkEntry(row, placeholder_text="正则")
        regex.grid(row=0, column=2, sticky="ew")
        return row

    def _restore_rule_default(self, label: str):
        """占位：恢复默认值。业务逻辑接 core 后填。"""
        entry = self.rule_entries.get(label)
        if entry is None:
            return
        entry.delete(0, "end")

    # ==================== 排版 Tab ====================
    def _build_layout_tab(self, parent):
        parent.grid_columnconfigure(0, weight=1)

        p = self._group(parent, "段落", 0)
        self.indent = self._field(p, 1, "缩进", "2", col=0)
        self.line_height = self._field(p, 1, "行高", "1.5", col=2)
        self.para_spacing = self._field(p, 2, "段间距", "1em", col=0)
        self.margin = self._field(p, 2, "页边距", "20", col=2)

        al = self._group(parent, "对齐方式", 1)
        self.align_volume = self._field_menu(
            al, 1, "卷", self.ALIGNS, default="center", col=0
        )
        self.align_chapter = self._field_menu(
            al, 1, "章", self.ALIGNS, default="center", col=2
        )
        self.align_section = self._field_menu(
            al, 2, "节", self.ALIGNS, default="left", col=0
        )
        self.align_body = self._field_menu(
            al, 2, "正文", self.ALIGNS, default="left", col=2
        )

        fo = self._group(parent, "嵌入字体", 2)
        self.font_entry = self._field_btn(fo, 1, "路径", self._pick_font)

        # 自定义 CSS：在 parent 里 sticky="nsew"，让自身能纵向长高；
        # pady 显式用 (8, 0) 与其他组一致。
        css = self._group(parent, "自定义 CSS", 3)
        css.grid_configure(sticky="nsew", pady=(8, 0))
        css.grid_columnconfigure(0, weight=1)
        css.grid_rowconfigure(2, weight=1)  # 文本框所在行吸收拉伸

        self.css_mode = ctk.CTkSegmentedButton(css, values=["忽略", "追加", "覆盖"])
        self.css_mode.set("忽略")
        self.css_mode.grid(
            row=1, column=0, columnspan=4, padx=10, pady=(6, 4), sticky="w"
        )
        self.css_text = ctk.CTkTextbox(css)
        self.css_text.grid(
            row=2, column=0, columnspan=4, padx=10, pady=(0, 10), sticky="nsew"
        )

        parent.grid_rowconfigure(3, weight=1)

    # ==================== 替换 Tab ====================
    def _build_replace_tab(self, parent):
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(1, weight=1)

        # 上方：导入 / 导出
        top = ctk.CTkFrame(parent, fg_color="transparent")
        top.grid(row=0, column=0, pady=(10, 6))
        for text in ("导入", "导出"):
            ctk.CTkButton(top, text=text, width=60).pack(side="left", padx=4)

        # 中间：表格
        holder = ctk.CTkFrame(parent)
        holder.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 6))
        holder.grid_rowconfigure(0, weight=1)
        holder.grid_columnconfigure(0, weight=1)

        self.replace_sheet = Sheet(
            holder,
            headers=["启用", "正则", "替换为", "阶段"],
            data=[],
            show_row_index=False,
            show_top_left=False,
            row_height=24,
            header_height=26,
        )
        self.replace_sheet.enable_bindings(
            (
                "single_select",
                "row_select",
                "column_width_resize",
                "arrowkeys",
                "right_click_popup_menu",
                "rc_select",
                "copy",
                "cut",
                "paste",
                "delete",
                "undo",
                "edit_cell",
            )
        )
        self.replace_sheet.grid(row=0, column=0, sticky="nsew")

        # 列宽
        self.replace_sheet.column_width(column=0, width=50)
        self.replace_sheet.column_width(column=1, width=200)
        self.replace_sheet.column_width(column=2, width=150)
        self.replace_sheet.column_width(column=3, width=70)

        # 启用列做成复选框（tksheet 7 Span API）
        self.replace_sheet["A"].checkbox(
            checked=False,
            state="normal",
        )

        # 阶段列做成下拉框（tksheet 7 Span API）
        self.replace_sheet["D"].dropdown(
            values=self.STAGES,
            state="normal",
        )

        # 下方：行编辑按钮
        btns = ctk.CTkFrame(parent, fg_color="transparent")
        btns.grid(row=2, column=0, pady=(0, 10))
        for text in ("上移", "下移", "添加", "删除"):
            ctk.CTkButton(btns, text=text, width=60).pack(side="left", padx=4)

    # ==================== 右侧目录面板 ====================
    def _build_toc_panel(self, parent):
        self.panel = ctk.CTkFrame(parent, corner_radius=4)
        self.panel.grid(row=0, column=1, sticky="nsew", padx=(self.GAP // 2, 0))
        self.panel.grid_rowconfigure(2, weight=1)
        self.panel.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            self.panel,
            text="目录",
            font=ctk.CTkFont(size=13, weight="bold"),
        ).grid(row=0, column=0, sticky="w", padx=12, pady=(8, 4))

        # 上方：重新扫描 / 导入 / 导出
        top = ctk.CTkFrame(self.panel, fg_color="transparent")
        top.grid(row=1, column=0, pady=(0, 6))
        ctk.CTkButton(top, text="重新扫描", width=90).pack(side="left", padx=4)
        ctk.CTkButton(top, text="导入", width=60).pack(side="left", padx=4)
        ctk.CTkButton(top, text="导出", width=60).pack(side="left", padx=4)

        # 中间：表格
        holder = ctk.CTkFrame(self.panel, fg_color="transparent")
        holder.grid(row=2, column=0, sticky="nsew", padx=10)
        holder.grid_rowconfigure(0, weight=1)
        holder.grid_columnconfigure(0, weight=1)

        self.toc_sheet = Sheet(
            holder,
            headers=["启用", "标题", "预览"],
            data=[],
            show_row_index=False,
            show_top_left=False,
            row_height=24,
            header_height=26,
        )
        self.toc_sheet.enable_bindings(
            (
                "single_select",
                "row_select",
                "column_width_resize",
                "arrowkeys",
                "right_click_popup_menu",
                "rc_select",
                "copy",
                "cut",
                "paste",
                "delete",
                "undo",
                "edit_cell",
            )
        )
        self.toc_sheet.grid(row=0, column=0, sticky="nsew")

        self.toc_sheet.column_width(column=0, width=40)
        self.toc_sheet.column_width(column=1, width=180)
        self.toc_sheet.column_width(column=2, width=160)

        # 启用列做成复选框（tksheet 7 Span API）
        self.toc_sheet["A"].checkbox(
            checked=False,
            state="normal",
        )

        # 下方：深度左对齐，勾选框右对齐
        opts = ctk.CTkFrame(self.panel, fg_color="transparent")
        opts.grid(row=3, column=0, sticky="ew", padx=12, pady=(6, 10))

        depth_box = ctk.CTkFrame(opts, fg_color="transparent")
        depth_box.pack(side="left")
        ctk.CTkLabel(depth_box, text="目录深度").pack(side="left")
        self.toc_depth = ctk.CTkOptionMenu(
            depth_box,
            values=[str(i) for i in range(1, 7)],
            width=70,
            anchor="center",
        )
        self.toc_depth.set("6")
        self.toc_depth.pack(side="left", padx=(6, 0))

        self.toc_in_book_var = tk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            opts, text="目录页出现在书中", variable=self.toc_in_book_var
        ).pack(side="right")

    # ==================== 底部栏 ====================
    def _build_bottombar(self):
        bar = ctk.CTkFrame(self, height=44, corner_radius=0)
        bar.grid(row=2, column=0, sticky="ew", pady=(self.GAP, 0))
        bar.grid_columnconfigure(1, weight=1)

        ctk.CTkButton(
            bar,
            text="⚙  开始生成",
            width=140,
            height=28,
            font=ctk.CTkFont(weight="bold"),
            command=self._on_generate,
        ).grid(row=0, column=0, padx=14, pady=6, sticky="w")

    # ==================== 封装组件 ====================
    def _group(self, parent, title, row):
        """分组框。内部统一为 4 列：

        col 0: 左半区标签    col 1: 左半区字段（weight=1）
        col 2: 右半区标签    col 3: 右半区字段（weight=1）
        """
        frame = ctk.CTkFrame(parent, border_width=1, corner_radius=4)
        frame.grid(row=row, column=0, sticky="ew", padx=10, pady=(8, 0))
        frame.grid_columnconfigure(0, weight=0)
        frame.grid_columnconfigure(1, weight=1)
        frame.grid_columnconfigure(2, weight=0)
        frame.grid_columnconfigure(3, weight=1)
        ctk.CTkLabel(
            frame,
            text=title,
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=("gray30", "gray70"),
        ).grid(row=0, column=0, columnspan=4, sticky="w", padx=10, pady=(6, 2))
        return frame

    def _field(self, parent, r, label, placeholder="", col=0):
        """标签 + 输入框。col=0 用左半区，col=2 用右半区。"""
        ctk.CTkLabel(parent, text=label, anchor="w").grid(
            row=r, column=col, padx=self.LABEL_PADX, pady=self.ROW_PADY, sticky="w"
        )
        entry = ctk.CTkEntry(parent, placeholder_text=placeholder)
        entry.grid(
            row=r, column=col + 1, padx=self.FIELD_PADX, pady=self.ROW_PADY, sticky="ew"
        )
        return entry

    def _field_btn(
        self, parent, r, label, command, extra_btn=None, btn_text="浏览", btn_width=56
    ):
        """标签 + 输入框 + 按钮（可选第二个按钮）。

        标签占 col 0；输入框与按钮放在 col 1-3 的内部子 frame 里：
        输入框 pack(side="left", expand=True) 顶到分组框右边缘，按钮 pack(side="right") 贴右。
        拉伸时只动输入框，不会在输入框和按钮之间裂开缝。
        """
        ctk.CTkLabel(parent, text=label, anchor="w").grid(
            row=r, column=0, padx=self.LABEL_PADX, pady=self.ROW_PADY, sticky="w"
        )
        box = ctk.CTkFrame(parent, fg_color="transparent")
        box.grid(
            row=r,
            column=1,
            columnspan=3,
            padx=self.FIELD_PADX,
            pady=self.ROW_PADY,
            sticky="ew",
        )
        entry = ctk.CTkEntry(box)
        entry.pack(side="left", fill="x", expand=True)

        btn_box = ctk.CTkFrame(box, fg_color="transparent")
        btn_box.pack(side="right", padx=(8, 0))
        ctk.CTkButton(btn_box, text=btn_text, width=btn_width, command=command).pack(
            side="left"
        )
        if extra_btn:
            text, cmd = extra_btn
            ctk.CTkButton(btn_box, text=text, width=56, command=cmd).pack(
                side="left", padx=(6, 0)
            )
        return entry

    def _field_menu(self, parent, r, label, values, default=None, col=0):
        """标签 + 下拉。col=0 用左半区，col=2 用右半区。"""
        ctk.CTkLabel(parent, text=label, anchor="w").grid(
            row=r, column=col, padx=self.LABEL_PADX, pady=self.ROW_PADY, sticky="w"
        )
        menu = ctk.CTkOptionMenu(parent, values=values, anchor="center")
        menu.set(default if default is not None else values[0])
        menu.grid(
            row=r, column=col + 1, padx=self.FIELD_PADX, pady=self.ROW_PADY, sticky="ew"
        )
        return menu

    # ==================== 业务占位 ====================
    def _pick_input(self): ...
    def _pick_output(self): ...
    def _pick_cover(self): ...
    def _pick_font(self): ...
    def _on_generate(self): ...
    def _add_extra_rule(self): ...
    def _remove_extra_rule(self): ...

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
