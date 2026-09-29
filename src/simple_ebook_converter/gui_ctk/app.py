"""Simple Ebook Converter — GUI 骨架（CTk 布局版，无业务逻辑）

依赖：customtkinter
    pip install customtkinter

代码按区块组织，将来可拆成：
  - gui/constants.py        常量
  - gui/fonts.py            字体解析与预设
  - gui/utils.py            跨平台工具
  - gui/settings_dialog.py  设置窗
  - gui/widgets.py          封装控件
  - gui/tabs/*.py           各 Tab
"""

from __future__ import annotations

import os
import subprocess
import sys
import tkinter as tk
from tkinter import messagebox, ttk

import customtkinter as ctk

# ==========================================================================
# 区块 1：跨平台工具
# ==========================================================================


def open_with_default_app(path: str) -> None:
    if not path or not os.path.exists(path):
        raise FileNotFoundError(path)
    if sys.platform == "win32":
        os.startfile(path)  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.run(["open", path], check=False)
    else:
        subprocess.run(["xdg-open", path], check=False)


# ==========================================================================
# 区块 2：常量与字体预设
# ==========================================================================

# ---- 通用间距 ----
PAD = 6
GAP = 6
ROW_PADY = 5
LABEL_PADX = (10, 6)
FIELD_PADX = (0, 10)

# ---- 分组框 ----
GROUP_PADX = 10
GROUP_PADY = (8, 0)
GROUP_TITLE_PADY = (6, 2)

# ---- 复选框 ----
CHECK_PADX = 10
CHECK_PADY_LAST = (0, 10)
CHECK_PADY_MID = (0, 6)

# ---- 顶部/底部栏 ----
BAR_PADX = 14
BAR_PADY = 6

# ---- 设置窗 ----
SETTINGS_PAD = 20
SETTINGS_ROW_PADY = 10
SETTINGS_LABEL_PADX = (0, 12)
SETTINGS_FIELD_WIDTH = 160

# ---- 选项 ----
ALIGNS = ["left", "center", "right"]
HEADINGS = ["h1", "h2", "h3", "h4", "h5", "h6"]
STAGES = ["原文", "HTML"]
ENCODINGS = ["auto", "utf-8", "gb18030", "big5", "shift_jis", "euc_jp"]
LANGUAGES = ["zh", "en", "jp"]
TOC_DEPTHS = [str(i) for i in range(1, 7)]

# ---- 字号 ----
FONT_SIZES = [str(i) for i in range(9, 21)]
DEFAULT_UI_SIZE = 13
DEFAULT_TOC_SIZE = 14
DEFAULT_FONT_LABEL = "系统默认"

# ---- 字体预设：显示名 → 实际字体族名 ----
FONT_PRESETS_BY_OS = {
    "win32": {
        "系统默认": "Microsoft YaHei",
        "微软雅黑": "Microsoft YaHei",
        "宋体": "SimSun",
        "黑体": "SimHei",
        "楷体": "KaiTi",
        "仿宋": "FangSong",
    },
    "darwin": {
        "系统默认": "TkDefaultFont",
        "苹方": "PingFang SC",
        "冬青黑体": "Hiragino Sans GB",
        "华文黑体": "STHeiti",
        "宋体-简": "Songti SC",
        "楷体-简": "Kaiti SC",
    },
    "linux": {
        "系统默认": "TkDefaultFont",
        "Noto Sans CJK": "Noto Sans CJK SC",
        "文泉驿微米黑": "WenQuanYi Micro Hei",
        "文泉驿正黑": "WenQuanYi Zen Hei",
        "思源黑体": "Source Han Sans SC",
        "思源宋体": "Source Han Serif SC",
    },
}


def font_presets() -> dict[str, str]:
    """按当前系统返回预设字体表。"""
    if sys.platform == "win32":
        return FONT_PRESETS_BY_OS["win32"]
    if sys.platform == "darwin":
        return FONT_PRESETS_BY_OS["darwin"]
    return FONT_PRESETS_BY_OS["linux"]


def resolve_family(label: str) -> str:
    """显示名 → 实际字体族名；不在预设里就当用户自定义。"""
    return font_presets().get(label, label)


# ==========================================================================
# 区块 3：主应用
# ==========================================================================


class App(ctk.CTk):

    def __init__(self):
        super().__init__()
        self.title("Simple Ebook Converter")
        self.geometry("900x720")
        self.minsize(720, 600)

        ctk.set_appearance_mode("light")
        ctk.set_default_color_theme("blue")

        # ---- 运行时状态 ----
        self.ui_size = DEFAULT_UI_SIZE
        self.toc_size = DEFAULT_TOC_SIZE
        self.font_family_label = DEFAULT_FONT_LABEL
        self.font_family = resolve_family(DEFAULT_FONT_LABEL)

        # ---- 字体 ----
        self._init_fonts()

        # ---- 布局 ----
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self._build_topbar()
        self._build_main()
        self._build_bottombar()

        self._apply_toc_theme()

    # ======================================================================
    # 区块 4：字体与主题
    # ======================================================================

    def _init_fonts(self):
        """先建空 CTkFont，再由 _refresh_fonts 填入 family/size。"""
        self.font_base = ctk.CTkFont()
        self.font_bold = ctk.CTkFont(weight="bold")
        self.font_title = ctk.CTkFont(weight="bold")
        self.font_tab = ctk.CTkFont()
        self._refresh_fonts()

    def _refresh_fonts(self):
        """把当前 family/size 应用到所有共享字体实例。"""
        s = self.ui_size
        fam = self.font_family
        self.font_base.configure(size=s, family=fam)
        self.font_bold.configure(size=s, family=fam, weight="bold")
        self.font_title.configure(size=s + 1, family=fam, weight="bold")
        self.font_tab.configure(size=max(s - 1, 9), family=fam)

    def _apply_ui_font_size(self, size: int):
        self.ui_size = size
        self._refresh_fonts()

    def _apply_font_family(self, label: str):
        self.font_family_label = label
        self.font_family = resolve_family(label)
        self._refresh_fonts()

    def _apply_toc_font(self):
        style = ttk.Style()
        fam = self.font_family
        style.configure(
            "Toc.Treeview",
            font=(fam, self.toc_size),
            rowheight=max(self.toc_size + 16, 24),
        )
        style.configure("Toc.Treeview.Heading", font=(fam, self.toc_size))
        self.toc_table.tag_configure("deleted", font=(fam, self.toc_size, "overstrike"))

    def _apply_toc_theme(self):
        dark = ctk.get_appearance_mode() == "Dark"
        style = ttk.Style()

        if dark:
            bg, fg, field = "#2b2b2b", "#e0e0e0", "#2b2b2b"
            head_bg, head_fg = "#3a3a3a", "#e0e0e0"
            sel_bg, sel_fg = "#1f538d", "#ffffff"
            del_fg = "#8a8a8a"
        else:
            bg, fg, field = "#ffffff", "#000000", "#ffffff"
            head_bg, head_fg = "#e5e5e5", "#000000"
            sel_bg, sel_fg = "#3b8ed0", "#ffffff"
            del_fg = "gray60"

        style.configure(
            "Toc.Treeview",
            background=bg,
            foreground=fg,
            fieldbackground=field,
        )
        style.map(
            "Toc.Treeview",
            background=[("selected", sel_bg)],
            foreground=[("selected", sel_fg)],
        )
        style.configure(
            "Toc.Treeview.Heading",
            background=head_bg,
            foreground=head_fg,
        )
        self.toc_table.tag_configure("deleted", foreground=del_fg)

    # ======================================================================
    # 区块 5：顶部栏
    # ======================================================================

    def _build_topbar(self):
        bar = ctk.CTkFrame(self, height=40, corner_radius=0)
        bar.grid(row=0, column=0, sticky="ew")
        bar.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            bar,
            text="Simple Ebook Converter",
            font=self.font_title,
        ).grid(row=0, column=0, sticky="w", padx=BAR_PADX, pady=BAR_PADY)

        right = ctk.CTkFrame(bar, fg_color="transparent")
        right.grid(row=0, column=1, sticky="e", padx=BAR_PADX, pady=BAR_PADY)

        theme_seg = ctk.CTkSegmentedButton(
            right,
            values=["浅色", "深色"],
            command=self._on_theme_change,
        )
        theme_seg.set("浅色")
        theme_seg.pack(side="left", padx=(0, 6))

        ctk.CTkButton(
            right,
            text="设置",
            width=56,
            command=self._open_settings,
        ).pack(side="left")

    def _on_theme_change(self, value: str):
        ctk.set_appearance_mode("dark" if value == "深色" else "light")
        self._apply_toc_theme()

    # ======================================================================
    # 区块 6：主体布局
    # ======================================================================

    def _build_main(self):
        self.main = ctk.CTkFrame(self, fg_color="transparent")
        self.main.grid(row=1, column=0, sticky="nsew", padx=PAD, pady=(PAD, 0))
        self.main.grid_rowconfigure(0, weight=1)
        self.main.grid_columnconfigure(0, weight=1, uniform="col")
        self.main.grid_columnconfigure(1, weight=1, uniform="col")

        self.tabs = ctk.CTkTabview(self.main, border_width=0)
        self.tabs.grid(row=0, column=0, sticky="nsew", padx=(0, GAP // 2))
        for name in ("基础", "规则", "排版", "替换"):
            self.tabs.add(name)

        self._build_basic_tab(self.tabs.tab("基础"))
        self._build_rules_tab(self.tabs.tab("规则"))
        self._build_layout_tab(self.tabs.tab("排版"))
        self._build_replace_tab(self.tabs.tab("替换"))

        self._build_toc_panel(self.main)

    # ======================================================================
    # 区块 7：基础 Tab
    # ======================================================================

    def _build_basic_tab(self, parent):
        parent.grid_columnconfigure(0, weight=1)

        f = self._group(parent, "文件", 0)
        self.input_entry = self._field_btn(f, 1, "源文件", self._pick_input)
        self.output_entry = self._field_btn(f, 2, "目标", self._pick_output)
        self.encoding_menu = self._field_menu(f, 3, "编码", ENCODINGS)

        m = self._group(parent, "书籍信息", 1)
        self.book_title = self._field(m, 1, "书名", "书名", col=0)
        self.book_author = self._field(m, 1, "作者", "作者", col=2)
        self.book_date = self._field(m, 2, "日期", "2024-05-13", col=0)
        self.lang_menu = self._field_menu(m, 2, "语言", LANGUAGES, col=2)

        c = self._group(parent, "封面", 2)
        self.cover_entry = self._field_btn(
            c,
            1,
            "路径",
            self._pick_cover,
            extra_btn=("查看", self._open_cover),
        )
        self.text_cover_var = tk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            c,
            text="无封面时生成文字封面",
            variable=self.text_cover_var,
            font=self.font_base,
        ).grid(
            row=2,
            column=0,
            columnspan=4,
            padx=CHECK_PADX,
            pady=CHECK_PADY_LAST,
            sticky="w",
        )

        o = self._group(parent, "其他", 3)
        self.clean_var = tk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            o,
            text="清理段首空格及空行",
            variable=self.clean_var,
            font=self.font_base,
        ).grid(
            row=1,
            column=0,
            columnspan=4,
            padx=CHECK_PADX,
            pady=CHECK_PADY_MID,
            sticky="w",
        )

        self.toc_in_book_var = tk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            o,
            text="生成书内目录页",
            variable=self.toc_in_book_var,
            font=self.font_base,
        ).grid(
            row=2,
            column=0,
            columnspan=4,
            padx=CHECK_PADX,
            pady=CHECK_PADY_LAST,
            sticky="w",
        )

    # ======================================================================
    # 区块 8：规则 Tab
    # ======================================================================

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
            btns,
            text="＋ 添加",
            width=90,
            font=self.font_base,
            command=self._add_extra_rule,
        ).pack(side="left", padx=4)
        ctk.CTkButton(
            btns,
            text="－ 删除",
            width=90,
            font=self.font_base,
            command=self._remove_extra_rule,
        ).pack(side="left", padx=4)

    def _extra_level_row(self, parent, r):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.grid(row=r, column=0, columnspan=4, sticky="ew", padx=GROUP_PADX, pady=4)
        row.grid_columnconfigure(2, weight=1)

        level = ctk.CTkOptionMenu(
            row,
            values=HEADINGS,
            width=70,
            anchor="center",
            font=self.font_base,
            dropdown_font=self.font_base,
        )
        level.set("h2")
        level.grid(row=0, column=0, padx=(0, 6))

        cls = ctk.CTkEntry(row, width=80, placeholder_text="class", font=self.font_base)
        cls.grid(row=0, column=1, padx=(0, 6))

        regex = ctk.CTkEntry(row, placeholder_text="正则", font=self.font_base)
        regex.grid(row=0, column=2, sticky="ew")
        return row

    def _restore_rule_default(self, label: str):
        entry = self.rule_entries.get(label)
        if entry is None:
            return
        entry.delete(0, "end")

    # ======================================================================
    # 区块 9：排版 Tab
    # ======================================================================

    def _build_layout_tab(self, parent):
        parent.grid_columnconfigure(0, weight=1)

        p = self._group(parent, "段落", 0)
        self.indent = self._field(p, 1, "缩进", "2", col=0)
        self.line_height = self._field(p, 1, "行高", "1.5", col=2)
        self.para_spacing = self._field(p, 2, "段间距", "1em", col=0)
        self.margin = self._field(p, 2, "页边距", "20", col=2)

        al = self._group(parent, "对齐方式", 1)
        self.align_volume = self._field_menu(
            al, 1, "卷", ALIGNS, default="center", col=0
        )
        self.align_chapter = self._field_menu(
            al, 1, "章", ALIGNS, default="center", col=2
        )
        self.align_section = self._field_menu(
            al, 2, "节", ALIGNS, default="left", col=0
        )
        self.align_body = self._field_menu(al, 2, "正文", ALIGNS, default="left", col=2)

        fo = self._group(parent, "嵌入字体", 2)
        self.font_entry = self._field_btn(fo, 1, "路径", self._pick_font)

        css = self._group(parent, "自定义 CSS", 3)
        css.grid_configure(sticky="nsew", pady=(8, 0))
        css.grid_columnconfigure(0, weight=1)
        css.grid_rowconfigure(2, weight=1)

        self.css_mode = ctk.CTkSegmentedButton(css, values=["忽略", "追加", "覆盖"])
        self.css_mode.set("忽略")
        self.css_mode.grid(
            row=1,
            column=0,
            columnspan=4,
            padx=CHECK_PADX,
            pady=(6, 4),
            sticky="w",
        )

        self.css_text = ctk.CTkTextbox(css, font=self.font_base)
        self.css_text.grid(
            row=2,
            column=0,
            columnspan=4,
            padx=CHECK_PADX,
            pady=CHECK_PADY_LAST,
            sticky="nsew",
        )

        parent.grid_rowconfigure(3, weight=1)

    # ======================================================================
    # 区块 10：替换 Tab
    # ======================================================================

    def _build_replace_tab(self, parent):
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(1, weight=1)

        top = ctk.CTkFrame(parent, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew", padx=GROUP_PADX, pady=(10, 4))
        top.grid_columnconfigure(0, weight=1)

        ctk.CTkButton(
            top,
            text="添加规则",
            width=90,
            font=self.font_base,
            command=self._add_replace_rule,
        ).grid(row=0, column=0, sticky="w")

        right_top = ctk.CTkFrame(top, fg_color="transparent")
        right_top.grid(row=0, column=1, sticky="e")
        ctk.CTkButton(right_top, text="导入", width=60, font=self.font_base).pack(
            side="left", padx=(0, 4)
        )
        ctk.CTkButton(right_top, text="导出", width=60, font=self.font_base).pack(
            side="left"
        )

        self.rules_holder = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        self.rules_holder.grid(
            row=1, column=0, sticky="nsew", padx=GROUP_PADX, pady=(0, 10)
        )
        self.rules_holder.grid_columnconfigure(0, weight=1)

        self.rule_cards: list[ctk.CTkFrame] = []
        self._add_replace_rule()
        self._add_replace_rule()

    def _add_replace_rule(self):
        card = self._make_rule_card()
        self.rule_cards.append(card)
        self._relayout_rule_cards()

    def _make_rule_card(self):
        card = ctk.CTkFrame(self.rules_holder, border_width=1, corner_radius=4)
        card.grid_columnconfigure(1, weight=1)

        head = ctk.CTkFrame(card, fg_color="transparent")
        head.grid(
            row=0, column=0, columnspan=2, sticky="ew", padx=GROUP_PADX, pady=(8, 2)
        )
        head.grid_columnconfigure(0, weight=1)

        enabled_var = tk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            head,
            text="启用",
            variable=enabled_var,
            font=self.font_base,
        ).grid(row=0, column=0, sticky="w")

        right = ctk.CTkFrame(head, fg_color="transparent")
        right.grid(row=0, column=1, sticky="e")

        stage_menu = ctk.CTkOptionMenu(
            right,
            values=STAGES,
            width=90,
            anchor="center",
            font=self.font_base,
            dropdown_font=self.font_base,
        )
        stage_menu.set("原文")
        stage_menu.pack(side="left", padx=(0, 6))

        ctk.CTkButton(
            right,
            text="↑",
            width=28,
            font=self.font_base,
            command=lambda c=card: self._move_rule(c, -1),
        ).pack(side="left", padx=(0, 2))
        ctk.CTkButton(
            right,
            text="↓",
            width=28,
            font=self.font_base,
            command=lambda c=card: self._move_rule(c, +1),
        ).pack(side="left", padx=(0, 2))
        ctk.CTkButton(
            right,
            text="✕",
            width=28,
            font=self.font_base,
            command=lambda c=card: self._remove_rule(c),
        ).pack(side="left")

        ctk.CTkLabel(card, text="正则", anchor="w", font=self.font_base).grid(
            row=1, column=0, padx=LABEL_PADX, pady=ROW_PADY, sticky="w"
        )
        pattern_entry = ctk.CTkEntry(
            card,
            placeholder_text=r"如 ^#+\s* 或 (第.{1,10}章)\s*",
            font=self.font_base,
        )
        pattern_entry.grid(row=1, column=1, padx=FIELD_PADX, pady=ROW_PADY, sticky="ew")

        ctk.CTkLabel(card, text="替换为", anchor="w", font=self.font_base).grid(
            row=2, column=0, padx=LABEL_PADX, pady=ROW_PADY, sticky="w"
        )
        replace_entry = ctk.CTkEntry(
            card,
            placeholder_text=r"留空即删除匹配内容；可用 \1 引用分组",
            font=self.font_base,
        )
        replace_entry.grid(row=2, column=1, padx=FIELD_PADX, pady=ROW_PADY, sticky="ew")

        card.enabled_var = enabled_var  # type: ignore[attr-defined]
        card.pattern_entry = pattern_entry  # type: ignore[attr-defined]
        card.replace_entry = replace_entry  # type: ignore[attr-defined]
        card.stage_menu = stage_menu  # type: ignore[attr-defined]
        return card

    def _relayout_rule_cards(self):
        for i, card in enumerate(self.rule_cards):
            card.grid(row=i, column=0, sticky="ew", pady=(0, 6))
        self.rules_holder.grid_columnconfigure(0, weight=1)

    def _move_rule(self, card, delta):
        if card not in self.rule_cards:
            return
        i = self.rule_cards.index(card)
        j = i + delta
        if j < 0 or j >= len(self.rule_cards):
            return
        self.rule_cards[i], self.rule_cards[j] = self.rule_cards[j], self.rule_cards[i]
        self._relayout_rule_cards()

    def _remove_rule(self, card):
        if card not in self.rule_cards:
            return
        self.rule_cards.remove(card)
        card.destroy()
        self._relayout_rule_cards()

    # ======================================================================
    # 区块 11：目录面板
    # ======================================================================

    def _build_toc_panel(self, parent):
        self.panel = ctk.CTkFrame(parent, corner_radius=4)
        self.panel.grid(row=0, column=1, sticky="nsew", padx=(GAP // 2, 0))
        self.panel.grid_rowconfigure(2, weight=1)
        self.panel.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            self.panel,
            text="目录",
            font=self.font_bold,
        ).grid(row=0, column=0, sticky="w", padx=12, pady=(8, 4))

        top = ctk.CTkFrame(self.panel, fg_color="transparent")
        top.grid(row=1, column=0, sticky="ew", padx=GROUP_PADX, pady=(0, 4))
        top.grid_columnconfigure(0, weight=1)

        ctk.CTkButton(top, text="重新扫描", width=90, font=self.font_base).grid(
            row=0, column=0, sticky="w"
        )
        right_top = ctk.CTkFrame(top, fg_color="transparent")
        right_top.grid(row=0, column=1, sticky="e")
        ctk.CTkButton(right_top, text="导入", width=60, font=self.font_base).pack(
            side="left", padx=(0, 4)
        )
        ctk.CTkButton(right_top, text="导出", width=60, font=self.font_base).pack(
            side="left"
        )

        holder = ctk.CTkFrame(self.panel, fg_color="transparent")
        holder.grid(row=2, column=0, sticky="nsew", padx=GROUP_PADX, pady=(0, 4))
        holder.grid_rowconfigure(0, weight=1)
        holder.grid_columnconfigure(0, weight=1)

        self.toc_table = ttk.Treeview(
            holder,
            columns=("title", "result"),
            show="tree headings",
            height=16,
            style="Toc.Treeview",
        )
        self.toc_table.heading("#0", text="")
        self.toc_table.column("#0", width=60, minwidth=60, stretch=False)
        self.toc_table.heading("title", text="标题")
        self.toc_table.heading("result", text="替换结果")
        self.toc_table.column("title", width=150, anchor="w", stretch=True)
        self.toc_table.column("result", width=150, anchor="w", stretch=True)

        self.toc_table.tag_configure(
            "deleted",
            foreground="gray60",
            font=(self.font_family, self.toc_size, "overstrike"),
        )

        vsb = ttk.Scrollbar(holder, orient="vertical", command=self.toc_table.yview)
        hsb = ttk.Scrollbar(holder, orient="horizontal", command=self.toc_table.xview)
        self.toc_table.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self.toc_table.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")

        self._load_toc_test_data()
        self._apply_toc_font()

        bottom = ctk.CTkFrame(self.panel, fg_color="transparent")
        bottom.grid(row=3, column=0, sticky="ew", padx=GROUP_PADX, pady=(0, 10))
        bottom.grid_columnconfigure(0, weight=1)

        left = ctk.CTkFrame(bottom, fg_color="transparent")
        left.grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(left, text="目录深度", font=self.font_base).pack(side="left")
        self.toc_depth = ctk.CTkOptionMenu(
            left,
            values=TOC_DEPTHS,
            width=70,
            anchor="center",
            font=self.font_base,
            dropdown_font=self.font_base,
        )
        self.toc_depth.set("6")
        self.toc_depth.pack(side="left", padx=(6, 0))

        right = ctk.CTkFrame(bottom, fg_color="transparent")
        right.grid(row=0, column=1, sticky="e")
        ctk.CTkButton(
            right,
            text="删除",
            width=60,
            font=self.font_base,
            command=self._mark_toc_deleted,
        ).pack(side="left", padx=(0, 4))
        ctk.CTkButton(
            right,
            text="恢复",
            width=60,
            font=self.font_base,
            command=self._restore_toc_deleted,
        ).pack(side="left")

    def _load_toc_test_data(self):
        vol1 = self.toc_table.insert("", "end", values=("第一卷 起源", "第一卷 起源"))
        self.toc_table.insert(vol1, "end", values=("第一章 开端", "第一章 开端"))
        ch2 = self.toc_table.insert(vol1, "end", values=("第二章 离别", "第二章 离别"))
        self.toc_table.insert(ch2, "end", values=("第一节 清晨", "第一节 清晨"))
        vol2 = self.toc_table.insert("", "end", values=("第二卷 风暴", "第二卷 风暴"))
        self.toc_table.insert(vol2, "end", values=("第三章 重逢", "第三章 重逢"))
        self.toc_table.item(vol1, open=True)
        self.toc_table.item(ch2, open=True)
        self.toc_table.item(vol2, open=True)

    def _mark_toc_deleted(self):
        for item_id in self.toc_table.selection():
            self.toc_table.item(item_id, tags=("deleted",))

    def _restore_toc_deleted(self):
        for item_id in self.toc_table.selection():
            self.toc_table.item(item_id, tags=())

    # ======================================================================
    # 区块 12：设置窗
    # ======================================================================

    def _open_settings(self):
        win = ctk.CTkToplevel(self)
        win.attributes("-alpha", 0.0)  # ① 先透明，别让用户看到初始态
        win.title("设置")
        win.resizable(False, False)
        win.transient(self)
        win.grab_set()

        body = ctk.CTkFrame(win, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=SETTINGS_PAD, pady=SETTINGS_PAD)
        body.grid_columnconfigure(0, weight=1)

        def add_row(r: int, label: str, widget: ctk.CTkBaseClass):
            """一行：标签左、控件右。标签和控件都用共享字体，跟随热更新。"""
            row = ctk.CTkFrame(body, fg_color="transparent")
            row.grid(row=r, column=0, sticky="ew", pady=(0, SETTINGS_ROW_PADY))
            row.grid_columnconfigure(0, weight=1)
            ctk.CTkLabel(
                row,
                text=label,
                anchor="w",
                font=self.font_base,
            ).grid(row=0, column=0, sticky="w", padx=SETTINGS_LABEL_PADX)
            widget.grid(row=0, column=1, sticky="e")

        font_combo = ctk.CTkComboBox(
            body,
            values=list(font_presets().keys()),
            width=SETTINGS_FIELD_WIDTH,
            font=self.font_base,
            dropdown_font=self.font_base,
        )
        font_combo.set(self.font_family_label)
        add_row(0, "字体", font_combo)

        ui_menu = ctk.CTkOptionMenu(
            body,
            values=FONT_SIZES,
            width=SETTINGS_FIELD_WIDTH,
            anchor="center",
            font=self.font_base,
            dropdown_font=self.font_base,
        )
        ui_menu.set(str(self.ui_size))
        add_row(1, "界面字号", ui_menu)

        toc_menu = ctk.CTkOptionMenu(
            body,
            values=FONT_SIZES,
            width=SETTINGS_FIELD_WIDTH,
            anchor="center",
            font=self.font_base,
            dropdown_font=self.font_base,
        )
        toc_menu.set(str(self.toc_size))
        add_row(2, "目录字号", toc_menu)

        def apply_and_close():
            self._apply_font_family(font_combo.get())
            self._apply_ui_font_size(int(ui_menu.get()))
            self.toc_size = int(toc_menu.get())
            self._apply_toc_font()
            win.destroy()

        btns = ctk.CTkFrame(body, fg_color="transparent")
        btns.grid(row=3, column=0, columnspan=2, pady=(SETTINGS_ROW_PADY, 0))
        ctk.CTkButton(
            btns,
            text="应用",
            width=80,
            font=self.font_base,
            command=apply_and_close,
        ).pack(side="left", padx=4)
        ctk.CTkButton(
            btns,
            text="取消",
            width=80,
            font=self.font_base,
            command=win.destroy,
        ).pack(side="left", padx=4)

        def center_and_show():
            self.update_idletasks()
            win.update_idletasks()
            px, py = self.winfo_rootx(), self.winfo_rooty()
            pw, ph = self.winfo_width(), self.winfo_height()
            ww, wh = win.winfo_width(), win.winfo_height()
            win.geometry(f"+{px + (pw - ww) // 2}+{py + (ph - wh) // 2}")
            win.attributes("-alpha", 1.0)  # ② 位置定好后再恢复可见

        self.after(20, center_and_show)

    # ======================================================================
    # 区块 13：底部栏
    # ======================================================================

    def _build_bottombar(self):
        bar = ctk.CTkFrame(self, height=44, corner_radius=0)
        bar.grid(row=2, column=0, sticky="ew", pady=(GAP, 0))
        bar.grid_columnconfigure(1, weight=1)

        ctk.CTkButton(
            bar,
            text="⚙  开始生成",
            width=140,
            height=28,
            font=self.font_bold,
            command=self._on_generate,
        ).grid(row=0, column=0, padx=BAR_PADX, pady=BAR_PADY, sticky="w")

    # ======================================================================
    # 区块 14：封装控件
    # ======================================================================

    def _group(self, parent, title, row):
        """分组框。内部 4 列：0/1 左半区，2/3 右半区。"""
        frame = ctk.CTkFrame(parent, border_width=1, corner_radius=4)
        frame.grid(row=row, column=0, sticky="ew", padx=GROUP_PADX, pady=GROUP_PADY)
        frame.grid_columnconfigure(0, weight=0)
        frame.grid_columnconfigure(1, weight=1)
        frame.grid_columnconfigure(2, weight=0)
        frame.grid_columnconfigure(3, weight=1)
        ctk.CTkLabel(
            frame,
            text=title,
            font=self.font_bold,
            text_color=("gray30", "gray70"),
        ).grid(
            row=0,
            column=0,
            columnspan=4,
            sticky="w",
            padx=GROUP_PADX,
            pady=GROUP_TITLE_PADY,
        )
        return frame

    def _field(self, parent, r, label, placeholder="", col=0):
        ctk.CTkLabel(parent, text=label, anchor="w", font=self.font_base).grid(
            row=r, column=col, padx=LABEL_PADX, pady=ROW_PADY, sticky="w"
        )
        entry = ctk.CTkEntry(parent, placeholder_text=placeholder, font=self.font_base)
        entry.grid(row=r, column=col + 1, padx=FIELD_PADX, pady=ROW_PADY, sticky="ew")
        return entry

    def _field_btn(
        self, parent, r, label, command, extra_btn=None, btn_text="浏览", btn_width=56
    ):
        ctk.CTkLabel(parent, text=label, anchor="w", font=self.font_base).grid(
            row=r, column=0, padx=LABEL_PADX, pady=ROW_PADY, sticky="w"
        )
        box = ctk.CTkFrame(parent, fg_color="transparent")
        box.grid(
            row=r,
            column=1,
            columnspan=3,
            padx=FIELD_PADX,
            pady=ROW_PADY,
            sticky="ew",
        )
        entry = ctk.CTkEntry(box, font=self.font_base)
        entry.pack(side="left", fill="x", expand=True)

        btn_box = ctk.CTkFrame(box, fg_color="transparent")
        btn_box.pack(side="right", padx=(8, 0))
        ctk.CTkButton(
            btn_box,
            text=btn_text,
            width=btn_width,
            font=self.font_base,
            command=command,
        ).pack(side="left")
        if extra_btn:
            text, cmd = extra_btn
            ctk.CTkButton(
                btn_box,
                text=text,
                width=56,
                font=self.font_base,
                command=cmd,
            ).pack(side="left", padx=(6, 0))
        return entry

    def _field_menu(self, parent, r, label, values, default=None, col=0):
        ctk.CTkLabel(parent, text=label, anchor="w", font=self.font_base).grid(
            row=r, column=col, padx=LABEL_PADX, pady=ROW_PADY, sticky="w"
        )
        menu = ctk.CTkOptionMenu(
            parent,
            values=values,
            anchor="center",
            font=self.font_base,
            dropdown_font=self.font_base,
        )
        menu.set(default if default is not None else values[0])
        menu.grid(row=r, column=col + 1, padx=FIELD_PADX, pady=ROW_PADY, sticky="ew")
        return menu

    # ======================================================================
    # 区块 15：业务占位
    # ======================================================================

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
