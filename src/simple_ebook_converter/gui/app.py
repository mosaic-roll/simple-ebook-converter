"""Simple Ebook Converter — CTk 主窗口（装配层）

这里是**唯一**的装配点：建窗口、装各 Tab/面板、注册回调、切主题。
构建细节都在子模块里，本文件不摆控件。

依赖：customtkinter
    pip install customtkinter

模块划分（依赖单向，本文件在最上层）：
  constants.py / utils.py / fonts.py / theme.py / context.py / widgets.py
  tabs/{basic,rules,layout,replace}.py / toc_panel.py / settings_dialog.py

与 core 的分工：资源（目录 / CSS / 字体 / 封面）一律以**内容**交给 core。GUI 不写任何
临时文件，也不自己实现封面发现——`_collect_sources()` 把表单收成 `core.sources.Sources`，
读文件与格式校验走 core 的 `font_resource()` / `cover_resource()` / `cover_for()`，
与 CLI 同一份实现、同一批错误消息。
"""

from __future__ import annotations

from pathlib import Path
from tkinter import filedialog, messagebox
from typing import Any

import customtkinter as ctk

from ..core.builder import builtin_css
from ..core.config import DEFAULTS, Config
from ..core.encoding import EncodingError, read_lines
from ..core.mediatypes import COVER_TYPES, FONT_TYPES, find_cover
from ..core.meta import resolve_metadata
from ..core.options import CONFIG_KINDS, build_config
from ..core.parser import Node, walk
from ..core.pipeline import (
    preview_titles,
    read_book,
    scan_toc,
    write_epub,
)
from ..core.replace import rules_from_list, rules_to_list
from ..core.sources import Sources, cover_for, font_resource, read_text
from . import config, settings_dialog, theme
from .constants import (
    ALIGN_LABELS,
    BAR_HEIGHT_BOTTOM,
    BAR_HEIGHT_TOP,
    BAR_PADX,
    BAR_PADY,
    BTN_W_S,
    DEFAULT_FONT_LABEL,
    DEFAULT_THEME_CHOICE,
    DEFAULT_TOC_SIZE,
    DEFAULT_UI_SIZE,
    ENCODING_LABELS,
    GAP,
    GEN_BTN_H,
    GEN_BTN_W,
    PAD,
    STATUS_COLORS,
    THEME_CHOICE_DARK,
    THEME_CHOICES,
    TOC_DEPTHS,
    WINDOW_MIN,
    WINDOW_SIZE,
    WINDOW_TITLE,
)
from .context import GuiContext
from .defaults import default_align_label
from .fonts import FontManager
from .tabs import basic, layout, replace, rules
from .tabs.layout import CSS_MODES, CSS_SOURCE_FILE, CSS_SOURCE_TEXT
from .tabs.replace import (
    collect_rules,
    export_rules_json,
    fill_rules,
    import_rules_json,
)
from .toc_panel import (
    SAMPLE_ENTRIES,
    entries_from_preview,
    export_toc_json,
    import_toc_json,
    populate_toc,
)
from .toc_panel import build as build_toc_panel
from .utils import open_with_default_app

#: 文件对话框的过滤器。图案由 core 的扩展名表推导（`mediatypes.COVER_TYPES` /
#: `FONT_TYPES`）——手抄一份迟早和 core 走偏：core 加了 .avif，这里还拦着不让选。
_ALL_FILES = ("所有文件", "*.*")


def _pattern(suffixes) -> str:
    """一组扩展名 → 文件对话框的图案串（空格分隔，如 `"*.ttf *.otf"`）。"""
    return " ".join(f"*{s}" for s in sorted(suffixes))


_INPUT_TYPES = [("文本文件", "*.txt"), _ALL_FILES]
_OUTPUT_TYPES = [("EPUB", "*.epub"), _ALL_FILES]
_COVER_TYPES = [("图片", _pattern(COVER_TYPES)), _ALL_FILES]
_FONT_TYPES = [("字体", _pattern(FONT_TYPES)), _ALL_FILES]
_CSS_TYPES = [("CSS", "*.css"), _ALL_FILES]


#: 扁平条目列表 → `preview_titles` 需要的 `list[Node]`（仅供预览；`line` / `deleted`
#: 不参与标题替换预览，留给后续生成路径）
def _entries_to_nodes(entries: list[dict]) -> list[Node]:
    return [
        Node(
            title=str(e.get("raw_title", "")),
            raw_title=str(e.get("raw_title", "")),
            level=int(e.get("level", 0)),
        )
        for e in entries
    ]


def _replace_entry(entry: Any, text: str) -> None:
    """整框替换输入框内容：先清空再插入。

    单独一个函数是因为回填存档、选完文件、扫完目录都要用同一套「清空 → 写入」两步，
    漏掉 `delete` 就会把新值接在旧值后面。
    """
    entry.delete(0, "end")
    entry.insert(0, text)


def _initial_out(input_path: str) -> tuple[str | None, str | None]:
    """输出对话框的 `(initialdir, initialfile)`，都取自输入路径。

    文件名只取 stem，`.epub` 交给 `defaultextension` 补。输入框为空时都返回 `None`。
    """
    src = Path(input_path.strip())
    if not src.stem:
        return None, None
    return str(src.parent), src.stem


def _as_stored(name: str, text: str) -> Any:
    """界面文本 → 落盘值：`int` 字段存成数字，其余存字符串。

    按 `CONFIG_KINDS`（core 字段类型真源）判断，避免 JSON 里 `"indent": "2"` 这种
    和 `Config` 类型不一致的写法。空文本对 `int` 字段返回 `None`（调用方跳过不存）。
    """
    if CONFIG_KINDS.get(name) is int:
        text = text.strip()
        return int(text) if text else None
    return text


def _extra_level_spec(row: dict) -> str:
    """一行额外层级 → `hN[.class]:正则` 规格（`core.levels.build_levels()` 的入参）。

    正则留空表示这一行没填，返回空串让收集阶段过滤掉——空正则会匹配一切，
    留着等于把所有行都当标题。
    """
    regex = row["regex"].get().strip()
    if not regex:
        return ""
    cls = row["class"].get().strip()
    return f"{row['level'].get().strip()}{'.' + cls if cls else ''}:{regex}"


def _scannable_entries(entries: list[dict]) -> list[dict] | None:
    """目录条目能不能直接喂给 core：每一条都得有 `line`。

    示例数据与「还没扫描过」的表没有 `line`（那是给界面看的），传进去 core 会报
    行号非法，所以判空返回 `None` 让 core 走正则解析。必须 `all()` 判全——
    只判非空会漏掉「一半有、一半没有」那种半扫描状态。
    """
    return entries if entries and all(e.get("line", 0) > 0 for e in entries) else None


#: Tab 名 → (显示文字, 构建函数)
_TABS = (
    ("basic", "基础", basic.build),
    ("rules", "规则", rules.build),
    ("layout", "排版", layout.build),
    ("replace", "替换", replace.build),
)


class App(ctk.CTk):
    """主窗口。`tab_widgets` / `toc_widgets` 收着各模块交回的控件引用，
    业务逻辑接入后 `_collect_config()` 从这里读值构造 `core.config.Config`。"""

    def __init__(self, config_dir: Path | None = None) -> None:
        super().__init__()
        self.title(WINDOW_TITLE)
        self.geometry(WINDOW_SIZE)
        self.minsize(*WINDOW_MIN)

        dark = DEFAULT_THEME_CHOICE == THEME_CHOICE_DARK
        ctk.set_appearance_mode("dark" if dark else "light")
        ctk.set_default_color_theme("blue")

        # ---- 用户配置：启动时读一次，关闭时写一次 ----
        self._config_dir = (
            Path(config_dir) if config_dir is not None else config.default_dir()
        )
        self._saved_settings = config.load(self._config_dir)

        # ---- 运行时状态 ----
        self.fonts = FontManager(DEFAULT_UI_SIZE, DEFAULT_FONT_LABEL, DEFAULT_TOC_SIZE)
        self._apply_gui_settings(self._saved_settings)
        self.ctx = GuiContext(
            fonts=self.fonts, callbacks={}, saved=self._saved_settings
        )
        self.ctx.callbacks.update(
            pick_input=self._pick_input,
            pick_output=self._pick_output,
            pick_cover=self._pick_cover,
            pick_font=self._pick_font,
            pick_css=self._pick_css,
            clear_css=self._clear_css,
            load_builtin_css=self._load_builtin_css,
            open_cover=self._open_cover,
            rescan_toc=self._on_scan,
            import_toc=self._import_toc,
            export_toc=self._export_toc,
            import_rules=self._import_rules,
            export_rules=self._export_rules,
            on_generate=self._on_generate,
            set_status=self._set_status,
        )

        # ---- 控件引用（各 Tab / 面板交回的 dict） ----
        self.tab_widgets: dict[str, dict] = {}
        self.toc_widgets: dict = {}

        # ---- 布局 ----
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self._build_topbar()
        self._build_main()
        self._build_bottombar()
        # 存档回填排在最后：它会重建卡片、清空额外层级行并切 CSS 禁用态，
        # 都得等控件都在了才能做
        self._apply_saved()
        self._refresh_toc_preview()

        table = self.toc_widgets["table"]
        theme.apply_toc_theme(table)
        theme.apply_toc_font(table, self.fonts.family, self.fonts.toc_size)

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ---------------------------------------------------------------- 顶栏

    def _build_topbar(self) -> None:
        bar = ctk.CTkFrame(self, height=BAR_HEIGHT_TOP, corner_radius=0)
        bar.grid(row=0, column=0, sticky="ew")
        bar.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(bar, text=WINDOW_TITLE, font=self.fonts.title).grid(
            row=0, column=0, sticky="w", padx=BAR_PADX, pady=BAR_PADY
        )

        right = ctk.CTkFrame(bar, fg_color="transparent")
        right.grid(row=0, column=1, sticky="e", padx=BAR_PADX, pady=BAR_PADY)

        theme_seg = ctk.CTkSegmentedButton(
            right, values=THEME_CHOICES, command=self._on_theme_change
        )
        # 开关状态直接从 ctk 当前外观模式推导，不读存档——避免存档结构与
        # 实际状态不同步（存档键改名、格式变化都会让开关显示错误）。
        theme_seg.set("深色" if ctk.get_appearance_mode() == "Dark" else "浅色")
        theme_seg.pack(side="left", padx=(0, GAP))

        ctk.CTkButton(
            right, text="设置", width=BTN_W_S, command=self._open_settings
        ).pack(side="left")

    def _on_theme_change(self, value: str) -> None:
        ctk.set_appearance_mode("dark" if value == THEME_CHOICE_DARK else "light")
        table = self.toc_widgets["table"]
        theme.apply_toc_theme(table)
        theme.apply_toc_font(table, self.fonts.family, self.fonts.toc_size)

    def _open_settings(self) -> None:
        settings_dialog.open(
            self,
            self.ctx,
            self.toc_widgets["table"],
            on_apply=self._save_gui_settings,
        )

    def _apply_gui_settings(self, saved: dict[str, Any]) -> None:
        """从存档恢复 GUI 设置（字体、字号、主题），应用到 FontManager 和 ctk。"""
        ui = saved.get("ui") or {}
        if ui.get("theme"):
            ctk.set_appearance_mode("dark" if ui["theme"] == "dark" else "light")
        if ui.get("font"):
            self.fonts.set_family_label(ui["font"])
        if ui.get("ui_font_size"):
            self.fonts.set_ui_size(int(ui["ui_font_size"]))
        if ui.get("toc_font_size"):
            self.fonts.set_toc_size(int(ui["toc_font_size"]))

    def _save_gui_settings(self) -> None:
        """把当前 FontManager 与主题写回存档并落盘。字段收进 `ui` 下。"""
        self._saved_settings["ui"] = {
            "theme": ctk.get_appearance_mode().lower(),
            "font": self.fonts.family_label,
            "ui_font_size": self.fonts.ui_size,
            "toc_font_size": self.fonts.toc_size,
        }
        config.save(self._config_dir, self._collect_saved())

    # ---------------------------------------------------------------- 主体

    def _build_main(self) -> None:
        self.main = ctk.CTkFrame(self, fg_color="transparent")
        self.main.grid(row=1, column=0, sticky="nsew", padx=PAD, pady=(PAD, 0))
        self.main.grid_rowconfigure(0, weight=1)
        self.main.grid_columnconfigure(0, weight=1, uniform="col")
        self.main.grid_columnconfigure(1, weight=1, uniform="col")

        self.tabs = ctk.CTkTabview(self.main, border_width=0)
        self.tabs.grid(row=0, column=0, sticky="nsew", padx=(0, GAP // 2))
        for _, title, _ in _TABS:
            self.tabs.add(title)

        for key, title, build in _TABS:
            self.tab_widgets[key] = build(self.tabs.tab(title), self.ctx)

        self.toc_widgets = build_toc_panel(self.main, self.ctx)

        # 初始化目录条目：用示例数据填充，等真实扫描后再替换
        self.ctx.toc_entries = [
            {"raw_title": e["raw_title"], "level": e["level"], "deleted": False}
            for e in SAMPLE_ENTRIES
        ]

        # 替换规则变动 → 刷新目录预览（回调链由 replace tab 触发）
        self.ctx.rules_changed.append(self._refresh_toc_preview)
        # 首屏预览在 __init__ 里存档规则填好后统一刷一次，这里不刷

    # ---------------------------------------------------------------- 底栏

    def _build_bottombar(self) -> None:
        bar = ctk.CTkFrame(self, height=BAR_HEIGHT_BOTTOM, corner_radius=0)
        bar.grid(row=2, column=0, sticky="ew", pady=(GAP, 0))
        bar.grid_columnconfigure(1, weight=1)

        ctk.CTkButton(
            bar,
            text="⚙  开始生成",
            width=GEN_BTN_W,
            height=GEN_BTN_H,
            font=self.fonts.bold,
            command=self.ctx.cb("on_generate"),
        ).grid(row=0, column=0, padx=BAR_PADX, pady=BAR_PADY, sticky="w")

        # 状态文字而不是进度条：pipeline 是同步的，没有分阶段回调就不知道真实进度，
        # 硬画进度条只能靠猜。等 core 有了阶段回调，再换成「进度条 + 状态文字」。
        self.status_label = ctk.CTkLabel(
            bar, text="就绪", font=self.fonts.base, anchor="e"
        )
        self.status_label.grid(
            row=0, column=1, padx=BAR_PADX, pady=BAR_PADY, sticky="e"
        )

    def _set_status(self, text: str, kind: str = "info") -> None:
        """更新底栏状态文字。`kind`：info / ok / error，配色见 `constants.STATUS_COLORS`。"""
        self.status_label.configure(
            text=text, text_color=STATUS_COLORS.get(kind, STATUS_COLORS["info"])
        )
        # 业务逻辑同步跑时，状态得先刷出来，不然等活干完才显示「正在生成」
        self.update_idletasks()

    # ------------------------------------------------------------ 浏览与自动填充

    def _pick_input(self) -> None:
        """选输入文件：**覆盖**书名/作者/封面/输出，并自动扫一次目录。

        只在「浏览」这一条路上做自动行为——用户手动敲路径时不触发任何东西，
        要扫描自己点「重新扫描」。
        """
        path = filedialog.askopenfilename(title="选择输入文件", filetypes=_INPUT_TYPES)
        if not path:
            return
        src = Path(path)
        basic_tab = self.tab_widgets["basic"]

        _replace_entry(basic_tab["input_entry"], str(src))
        title, author = resolve_metadata(src)
        _replace_entry(basic_tab["book_title"], title or "")
        _replace_entry(basic_tab["book_author"], author or "")
        # 封面自动发现在这里只作**预览**：告诉用户找到了哪张。生成的权威判断在
        # `_collect_sources()` 的 `cover_for()`，与 CLI 同一个函数。
        cover = find_cover(src)
        _replace_entry(basic_tab["cover_entry"], str(cover) if cover else "")
        _replace_entry(basic_tab["output_entry"], str(src.with_suffix(".epub")))

        self._on_scan()  # 扫失败弹窗并保留已填的路径

    def _pick_output(self) -> None:
        """选输出文件：默认文件名与目录取自输入文件（见 `_initial_out`）。"""
        initialdir, initialfile = _initial_out(
            self.tab_widgets["basic"]["input_entry"].get()
        )
        path = filedialog.asksaveasfilename(
            title="选择输出文件",
            initialdir=initialdir,
            initialfile=initialfile,
            defaultextension=".epub",
            filetypes=_OUTPUT_TYPES,
        )
        if path:
            _replace_entry(self.tab_widgets["basic"]["output_entry"], path)

    def _pick_cover(self) -> None:
        path = filedialog.askopenfilename(title="选择封面图", filetypes=_COVER_TYPES)
        if path:
            _replace_entry(self.tab_widgets["basic"]["cover_entry"], path)

    def _pick_font(self) -> None:
        path = filedialog.askopenfilename(title="选择正文字体", filetypes=_FONT_TYPES)
        if path:
            _replace_entry(self.tab_widgets["layout"]["font_entry"], path)

    def _pick_css(self) -> None:
        path = filedialog.askopenfilename(title="选择 CSS 文件", filetypes=_CSS_TYPES)
        if not path:
            return
        layout_tab = self.tab_widgets["layout"]
        _replace_entry(layout_tab["css_path"], path)
        # 选了文件就切到「使用文件」，否则用户还得自己去点单选框
        if layout_tab["css_source"].get() != CSS_SOURCE_FILE:
            layout_tab["css_source"].set(CSS_SOURCE_FILE)
            layout_tab["on_source_change"]()

    def _clear_css(self) -> None:
        _replace_entry(self.tab_widgets["layout"]["css_path"], "")

    def _load_builtin_css(self) -> None:
        """把内置样式模板填进文本框：用**当前排版参数**现算，不是写死默认。

        用户改了缩进/行高，导出的模板就该反映当前值。字体只取**文件名**
        （`builtin_css` 拼 `fonts/<name>` 用），不读字节——导模板不该被一个
        暂时无效的字体路径拦住。
        """
        try:
            cfg, font_name = self._collect_layout_cfg()
        except ValueError as e:
            messagebox.showerror("参数错误", str(e))
            return
        text = self.tab_widgets["layout"]["css_text"]
        text.delete("1.0", "end")
        text.insert("1.0", builtin_css(cfg, font_name))

    def _import_toc(self) -> None:
        """导入目录 JSON：弹出文件选择框，加载后替换 ctx.toc_entries 并刷新预览。"""
        path = filedialog.askopenfilename(
            title="导入目录",
            filetypes=[("JSON 文件", "*.json"), ("所有文件", "*.*")],
        )
        if not path:
            return
        try:
            entries = import_toc_json(Path(path))
        except (ValueError, TypeError) as e:
            messagebox.showerror("导入失败", str(e))
            return
        self.ctx.toc_entries = entries
        self._refresh_toc_preview()

    def _export_toc(self) -> None:
        """导出目录 JSON：弹出保存框，用 core.toc.to_json 序列化后写入文件。"""
        path = filedialog.asksaveasfilename(
            title="导出目录",
            defaultextension=".json",
            filetypes=[("JSON 文件", "*.json"), ("所有文件", "*.*")],
        )
        if not path:
            return
        try:
            export_toc_json(self.ctx.toc_entries, Path(path))
        except (OSError, ValueError) as e:
            messagebox.showerror("导出失败", str(e))

    def _import_rules(self) -> None:
        """导入替换规则 JSON：弹出文件选择框，加载后填充到卡片。"""
        path = filedialog.askopenfilename(
            title="导入替换规则",
            filetypes=[("JSON 文件", "*.json"), ("所有文件", "*.*")],
        )
        if not path:
            return
        try:
            import_rules_json(
                self.tab_widgets["replace"]["rule_cards"],
                Path(path),
                self.tab_widgets["replace"].get("add_card"),
                self.tab_widgets["replace"].get("fire"),
            )
        except (ValueError, TypeError) as e:
            messagebox.showerror("导入失败", str(e))

    def _export_rules(self) -> None:
        """导出替换规则 JSON：弹出保存框，将当前规则写入文件。"""
        path = filedialog.asksaveasfilename(
            title="导出替换规则",
            defaultextension=".json",
            filetypes=[("JSON 文件", "*.json"), ("所有文件", "*.*")],
        )
        if not path:
            return
        try:
            export_rules_json(self.tab_widgets["replace"]["rule_cards"], Path(path))
        except OSError as e:
            messagebox.showerror("导出失败", str(e))

    # ------------------------------------------------------------ 表单收集

    def _collect_config(self) -> Config:
        """整个表单 → `core.config.Config`。参数错抛 `ValueError`（消息可直接展示）。

        **资源路径字段不在这里**：封面 / 字体 / CSS / 目录树走 `_collect_sources()`，
        所以 `Config.cover`、`font`、`css_file`、`css_append`、`toc_file` 恒为 `None`
        ——core 侧的资源校验因此发生在 `Sources` 那条路上。
        """
        basic_tab = self.tab_widgets["basic"]
        layout_tab = self.tab_widgets["layout"]
        rules_tab = self.tab_widgets["rules"]
        replace_tab = self.tab_widgets["replace"]

        # 编码菜单存中文标签，core 只认 codec 名；`.get(label, label)` 兼容用户
        # 手动敲进来的裸 codec 名（auto / utf-8 等）
        encoding_label = basic_tab["encoding_menu"].get()
        encoding = ENCODING_LABELS.get(encoding_label, encoding_label)
        values: dict[str, Any] = {
            # 输入
            "input": basic_tab["input_entry"].get().strip() or None,
            "encoding": encoding,
            # 元数据
            "title": basic_tab["book_title"].get().strip() or None,
            "author": basic_tab["book_author"].get().strip(),
            "date": basic_tab["book_date"].get().strip() or None,
            "language": basic_tab["lang_menu"].get(),
            "text_cover": bool(basic_tab["text_cover_var"].get()),
            # 文本处理
            "clean": bool(basic_tab["clean_var"].get()),
            # 排版
            "indent": layout_tab["indent"].get() or None,
            "line_height": layout_tab["line_height"].get() or None,
            "para_spacing": layout_tab["para_spacing"].get() or None,
            "volume_align": ALIGN_LABELS[layout_tab["align_volume"].get()],
            "chapter_align": ALIGN_LABELS[layout_tab["align_chapter"].get()],
            "para_align": ALIGN_LABELS[layout_tab["align_body"].get()],
            # 章节识别
            "volume": rules_tab["rule_entries"]["卷"].get(),
            "chapter": rules_tab["rule_entries"]["章"].get(),
            "exclude": rules_tab["rule_entries"]["排除"].get(),
            "max_title_len": rules_tab["rule_entries"]["字数上限"].get() or None,
            "preface_title": rules_tab["rule_entries"]["无标题章节"].get() or None,
            "level": [
                spec
                for spec in (_extra_level_spec(r) for r in rules_tab["extra_rows"])
                if spec
            ],
            # 产出
            "toc_in_spine": bool(basic_tab["toc_in_book_var"].get()),
            "toc_depth": self.toc_widgets["depth_menu"].get(),
            "out": basic_tab["output_entry"].get().strip() or None,
        }
        cfg = build_config(
            values,
            # 替换规则来自表格卡片，不经 `--replace-rules` 的文件入口。走关键字参数
            # 而不是造完 `Config` 再改字段——后者能跑，但让 GUI 落在一条"事后修改"的
            # 通路上，和 CLI 共用同一份 `build_config` 的意图也就没了。
            replacements=collect_rules(replace_tab["rule_cards"]),
        )
        return cfg

    def _collect_sources(self) -> Sources:
        """表单 → `core.sources.Sources`：内部目录、CSS、字体、封面。**纯内存。**

        CSS 文本框里的内容就是最终样式，不再落临时文件；目录用面板内存里那份。
        读文件与格式校验走 core 的 `read_text()` / `font_resource()` / `cover_for()`，
        与 CLI 同一份实现、同一批错误消息。
        """
        basic_tab = self.tab_widgets["basic"]
        layout_tab = self.tab_widgets["layout"]

        # 目录：没真扫描过（示例数据 / 空表）就让 core 走正则
        toc_entries = _scannable_entries(self.ctx.toc_entries)

        # CSS：来源决定走哪一条。文件来源读路径；文本来源按模式显式三分。
        # 「忽略」必须显式留着 None ——写成「非覆盖即追加」会让忽略悄悄变成追加。
        css_text: str | None = None
        css_append_text: str | None = None
        if layout_tab["css_source"].get() == CSS_SOURCE_FILE:
            css_file = layout_tab["css_path"].get().strip()
            css_text = read_text(css_file, "外部 CSS") if css_file else None
        else:
            text = layout_tab["css_text"].get("1.0", "end").strip()
            if text:
                mode = layout_tab["css_mode"].get()
                if mode == "覆盖":
                    css_text = text
                elif mode == "追加":
                    css_append_text = text

        font_path = layout_tab["font_entry"].get().strip()
        font = font_resource(font_path) if font_path else None

        # 封面：显式优先，留空则按 CLI 同一套规则自动发现（同目录恰好一张 cover.*）；
        # text_cover=False 时跳过自动发现，由 builder 走文字封面逻辑。
        cover = cover_for(
            basic_tab["cover_entry"].get().strip() or None,
            basic_tab["input_entry"].get().strip() or None,
            basic_tab["text_cover_var"].get(),
        )

        return Sources(
            toc_entries=toc_entries,
            css_text=css_text,
            css_append_text=css_append_text,
            font=font,
            cover=cover,
        )

    def _collect_layout_cfg(self) -> tuple[Config, str | None]:
        """当前排版参数 → (`Config`, 内嵌字体文件名)。给「加载内置样式」用。

        不做路径存在性校验：用户可能只想看看改了缩进之后的模板长什么样，
        不该被一个暂时无效的字体路径拦住。`font_name` 只用来拼 `fonts/<name>`。
        """
        layout_tab = self.tab_widgets["layout"]
        font = layout_tab["font_entry"].get().strip()
        return (
            Config(
                indent=int(layout_tab["indent"].get() or DEFAULTS.indent),
                line_height=layout_tab["line_height"].get() or DEFAULTS.line_height,
                para_spacing=layout_tab["para_spacing"].get() or DEFAULTS.para_spacing,
                volume_align=ALIGN_LABELS[layout_tab["align_volume"].get()],
                chapter_align=ALIGN_LABELS[layout_tab["align_chapter"].get()],
                para_align=ALIGN_LABELS[layout_tab["align_body"].get()],
            ),
            Path(font).name if font else None,
        )

    def _collect_scan_cfg(self) -> Config:
        """扫描用的参数：与 `_collect_config()` 同源，但**不做值域校验**。

        扫描只是预览，填了个非法缩进不该挡住用户看目录；`ValueError` 留给
        真正生成时（`read_book` 内部会 `resolve()` → `validate()`）。
        """
        try:
            return self._collect_config()
        except ValueError:
            return Config()

    # ------------------------------------------------------------ 生成

    def _on_generate(self) -> None:
        """收集表单 → 读输入切分 → 组装 EPUB。出错只报底栏，不弹窗打断。"""
        self._set_status("正在生成…", "info")
        try:
            cfg = self._collect_config()
            sources = self._collect_sources()
            book = read_book(cfg, sources)
            path = write_epub(book)
        except ValueError as e:
            self._set_status(f"生成失败：{e}", "error")
            return
        except Exception as e:  # noqa: BLE001  # ebooklib 崩了也要给用户看
            self._set_status(f"生成失败：{e}", "error")
            return
        self._set_status(f"已生成：{path.name}", "ok")

    def _on_scan(self) -> None:
        """扫描输入文件，更新 `ctx.toc_entries`，然后触发目录预览刷新。

        用的**是当前表单的章节规则**（`_collect_scan_cfg()`），不是写死的默认值——
        否则用户改了卷/章正则，预览显示的仍是旧规则的结果。
        """
        input_path = self.tab_widgets["basic"]["input_entry"].get().strip()
        if not input_path:
            return
        scan_cfg = self._collect_scan_cfg()
        try:
            lines, _encoding = read_lines(input_path, scan_cfg.encoding)
        except OSError as e:
            messagebox.showerror("读取失败", f"无法读取输入文件：{e}")
            return
        except EncodingError as e:
            messagebox.showerror("编码错误", str(e))
            return
        try:
            tree, _stats = scan_toc(lines, self._collect_scan_cfg())
        except ValueError as e:
            messagebox.showerror("扫描失败", str(e))
            return
        # 把扫描结果转成扁平条目列表，供 preview_titles 和 populate_toc 使用；
        # `line` / `class_name` 留给导出与后续生成用，`deleted` 由删除/恢复按钮改
        self.ctx.toc_entries = [
            {
                "raw_title": n.raw_title,
                "level": n.level,
                "class_name": n.class_name,
                "line": n.line,
                "deleted": False,
            }
            for n in walk(tree)
        ]
        self._refresh_toc_preview()

    def _refresh_toc_preview(self) -> None:
        """用当前替换规则对 `ctx.toc_entries` 做预览，刷新右侧表格。

        收集逻辑收在 `tabs.replace.collect_rules()` 里，此处只负责刷新。
        预览条目与 `toc_entries` 文档序一一对应，按序号把用户手标的 `deleted` 与扫描
        得到的 `line` 带过来——否则每次规则变动重建表格都会把删除线抹掉。
        所有节点默认展开：每次刷新重建整棵树，保留展开态需要额外状态；目录通常几十条，
        全展开比记住用户折叠了哪几节更简单。

        保持纯函数语义：无论谁调用、规则是否真的变了，都无条件执行一次。
        「规则是否变了」的判断由 replace tab 的 `_fire()` 在触发点完成，
        app 层不掺杂缓存状态。
        """
        old_entries = self.ctx.toc_entries
        rules_list = replace.collect_rules(self.tab_widgets["replace"]["rule_cards"])
        try:
            results = preview_titles(_entries_to_nodes(old_entries), rules_list)
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("预览失败", str(e))
            return
        entries = entries_from_preview(results)
        for i, entry in enumerate(entries):
            prev = old_entries[i] if i < len(old_entries) else {}
            entry["deleted"] = bool(prev.get("deleted", False))
            for key in ("line", "class_name"):
                if key in prev:
                    entry[key] = prev[key]
        self.ctx.toc_entries = entries
        table = self.toc_widgets["table"]
        table.delete(*table.get_children())
        populate_toc(table, entries)

    # ------------------------------------------------------------ 配置持久化

    def _collect_saved(self) -> dict[str, Any]:
        """收集要落盘的配置子集（其余项每次启动只用默认值）。

        字段顺序：GUI 设置 → 基础 → 规则 → 排版 → 替换 + TOC，方便用户读配置文件。
        `int` 字段经 `_as_stored` 转成数字；提示型字段（`max_title_len` / `preface_title`）
        留空会被 `.strip() or None` 过滤掉，不会写进 JSON，避免噪音。
        """
        basic_tab = self.tab_widgets["basic"]
        layout_tab = self.tab_widgets["layout"]
        rules_tab = self.tab_widgets["rules"]
        rule_entries = rules_tab["rule_entries"]

        return {
            # GUI 设置：收进 `ui`，不与业务配置混在一起
            "ui": {
                "theme": ctk.get_appearance_mode().lower(),
                "font": self.fonts.family_label,
                "ui_font_size": self.fonts.ui_size,
                "toc_font_size": self.fonts.toc_size,
            },
            # 基础 tab：文件、书籍信息、封面、其他
            "clean": bool(basic_tab["clean_var"].get()),
            "text_cover": bool(basic_tab["text_cover_var"].get()),
            "toc_in_spine": bool(basic_tab["toc_in_book_var"].get()),
            # 规则 tab：卷/章/排除正则 + 额外层级行
            "volume": rule_entries["卷"].get().strip() or None,
            "chapter": rule_entries["章"].get().strip() or None,
            "exclude": rule_entries["排除"].get().strip() or None,
            "extra_levels": [
                {
                    "level": row["level"].get().strip(),
                    "class": row["class"].get().strip(),
                    "regex": row["regex"].get().strip(),
                }
                for row in rules_tab["extra_rows"]
            ],
            # 额外层级：空行也是状态，用户刻意加的空行下次还在
            # 排版 tab：段落、对齐方式、嵌入字体、自定义 CSS
            "volume_align": ALIGN_LABELS[layout_tab["align_volume"].get()],
            "chapter_align": ALIGN_LABELS[layout_tab["align_chapter"].get()],
            "para_align": ALIGN_LABELS[layout_tab["align_body"].get()],
            "indent": _as_stored("indent", layout_tab["indent"].get()),
            "line_height": layout_tab["line_height"].get().strip() or None,
            "para_spacing": layout_tab["para_spacing"].get().strip() or None,
            # `css_path` 不存：文件模式的路径指向用户自己的外部文件，下次启动不该
            # 悄悄沿用一个可能已经换了内容的路径
            "css_source": layout_tab["css_source"].get(),
            "css_mode": layout_tab["css_mode"].get(),
            # TOC 面板（底栏右侧）
            "toc_depth": _as_stored("toc_depth", self.toc_widgets["depth_menu"].get()),
            # 替换 tab：有序规则卡片列表
            "replacements": rules_to_list(
                collect_rules(self.tab_widgets["replace"]["rule_cards"])
            ),
        }

    def _apply_saved(self) -> None:
        """把 `_saved_settings` 回填到表单。

        除 basic/build 里已走 `default_text(saved=...)` 的字段外，其余在这里补：
        勾选项、排版路径、对齐、CSS 三态、目录深度、额外层级、替换规则。
        布尔与 int 存的是真值/数字，这里 `bool()` / `str()` 一律转回控件要的形态。
        """
        saved = self._saved_settings
        if not saved:
            return
        basic_tab = self.tab_widgets["basic"]
        layout_tab = self.tab_widgets["layout"]
        rules_tab = self.tab_widgets["rules"]
        replace_tab = self.tab_widgets["replace"]

        if "clean" in saved:
            basic_tab["clean_var"].set(bool(saved["clean"]))
        if "toc_in_spine" in saved:
            basic_tab["toc_in_book_var"].set(bool(saved["toc_in_spine"]))
        if "text_cover" in saved:
            basic_tab["text_cover_var"].set(bool(saved["text_cover"]))

        # 排版文本：layout.py 里这些值是 placeholder，不是初值，所以得在这里真填进去。
        # 存档可能被手改：`indent` 是 int 字段，塞进 "abc" 只会等到生成时报错，
        # 不如当场跳过、让控件留空 (= 用 core 默认)
        for name, widget in (
            ("indent", layout_tab["indent"]),
            ("line_height", layout_tab["line_height"]),
            ("para_spacing", layout_tab["para_spacing"]),
            ("font", layout_tab["font_entry"]),
        ):
            if name not in saved:
                continue
            value = saved[name]
            if value is None:
                _replace_entry(widget, "")
            elif CONFIG_KINDS.get(name) is int:
                try:
                    _replace_entry(widget, str(int(str(value).strip())))
                except (TypeError, ValueError):
                    _replace_entry(widget, "")
            else:
                _replace_entry(widget, str(value))

        # 对齐：存档非法时 default_align_label 已退回 core 默认，不会让菜单显示空白
        for name, widget in (
            ("volume_align", layout_tab["align_volume"]),
            ("chapter_align", layout_tab["align_chapter"]),
            ("para_align", layout_tab["align_body"]),
        ):
            widget.set(default_align_label(name, saved))

        # CSS 三态：来源 / 模式 / 文本，然后按来源切禁用态。配置文件用户能手改，
        # 非法值退回控件自己的默认，别让单选框显示一个谁都不认识的值
        source = saved.get("css_source")
        if source in (CSS_SOURCE_TEXT, CSS_SOURCE_FILE):
            layout_tab["css_source"].set(source)
        mode = saved.get("css_mode")
        if mode in CSS_MODES:
            layout_tab["css_mode"].set(mode)
        layout_tab["on_source_change"]()
        # 文本模式的样式从 custom.css 读回；文件模式的路径是外部文件，不存档
        css_file = config.css_path(self._config_dir)
        if css_file.is_file():
            layout_tab["css_text"].delete("1.0", "end")
            layout_tab["css_text"].insert("1.0", css_file.read_text(encoding="utf-8"))

        for label, opt_name, _mode in rules.BUILTIN_ROWS:
            if opt_name in saved:
                _replace_entry(
                    rules_tab["rule_entries"][label], str(saved[opt_name] or "")
                )

        # 额外层级：先清空 build 里预置的两行，再按存档逐条重建（存档有几行就有几行，
        # 含用户刻意留的空行）
        levels = saved.get("extra_levels")
        if levels:
            rules_tab["clear_extra_rows"]()
            for item in levels:
                row = rules_tab["add_extra_row"]()
                row["level"].set(str(item.get("level") or "h6"))
                _replace_entry(row["class"], str(item.get("class") or ""))
                _replace_entry(row["regex"], str(item.get("regex") or ""))

        # 替换规则批量重建，不逐卡触发（每加一张卡就重算一次替换预览太吵）
        if saved.get("replacements"):
            try:
                fill_rules(
                    replace_tab["rule_cards"],
                    rules_from_list(saved["replacements"]),
                    replace_tab["add_card"],
                    fire=lambda: None,
                )
            except ValueError as e:
                self._set_status(f"配置里的替换规则无效：{e}", "error")

        if "toc_depth" in saved and str(saved["toc_depth"]) in TOC_DEPTHS:
            self.toc_widgets["depth_menu"].set(str(saved["toc_depth"]))

    def _save_custom_css(self) -> None:
        """把 CSS 文本框内容写进 `custom.css`，供下次启动回填。

        **不管当前来源**：文本框在「使用文件」下是禁用态但内容还在（可能是用户切
        来源前改的），一律以文本框为准存回去，免得关窗时白丢一次编辑。文本框空了就
        删文件——真源是空的，就别留一份陈旧样式在磁盘上。
        """
        text = self.tab_widgets["layout"]["css_text"].get("1.0", "end").strip()
        config.save_css(self._config_dir, text)

    def _on_close(self) -> None:
        """关闭窗口前把当前配置写盘；写失败只提示，不挡关闭。"""
        try:
            self._save_custom_css()
        except OSError as e:
            messagebox.showwarning("样式保存失败", str(e))
        try:
            config.save(self._config_dir, self._collect_saved())
        except OSError as e:
            messagebox.showwarning("配置保存失败", str(e))
        finally:
            self.destroy()

    def _open_cover(self) -> None:
        """用系统默认程序打开封面图；跨 Tab 读值，所以回调注册在 app 层。"""
        path = self.tab_widgets["basic"]["cover_entry"].get().strip()
        if not path:
            return
        try:
            open_with_default_app(path)
        except FileNotFoundError:
            messagebox.showerror("打开失败", f"文件不存在：\n{path}")


if __name__ == "__main__":
    App().mainloop()
