"""Simple Ebook Converter — CTk 主窗口（装配层）

这里是**唯一**的装配点：建窗口、装各 Tab/面板、注册回调、切主题。
构建细节都在子模块里，本文件不摆控件。

依赖：customtkinter
    pip install customtkinter

模块划分（依赖单向，本文件在最上层）：
  constants.py / utils.py / fonts.py / theme.py / context.py / widgets.py
  tabs/{basic,rules,layout,replace}.py / toc_panel.py / settings_dialog.py
"""

from __future__ import annotations

from pathlib import Path
from tkinter import filedialog, messagebox
from typing import Any

import customtkinter as ctk

from ..core.config import DEFAULTS
from ..core.encoding import EncodingError, read_lines
from ..core.options import CONFIG_KINDS
from ..core.parser import Node, walk
from ..core.pipeline import preview_titles, scan_toc
from ..core.replace import rules_from_list, rules_to_list
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
    GAP,
    GEN_BTN_H,
    GEN_BTN_W,
    PAD,
    STATUS_COLORS,
    THEME_CHOICE_DARK,
    THEME_CHOICES,
    WINDOW_MIN,
    WINDOW_SIZE,
    WINDOW_TITLE,
)
from .context import GuiContext
from .fonts import FontManager
from .tabs import basic, layout, replace, rules
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


def _as_stored(name: str, text: str) -> Any:
    """界面文本 → 落盘值：`int` 字段存成数字，其余存字符串。

    按 `CONFIG_KINDS`（core 字段类型真源）判断，避免 JSON 里 `"indent": "2"` 这种
    和 `Config` 类型不一致的写法。空文本对 `int` 字段返回 `None`（调用方跳过不存）。
    """
    if CONFIG_KINDS.get(name) is int:
        text = text.strip()
        return int(text) if text else None
    return text


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
        self._apply_saved_rules()
        # 存档规则为空时 _apply_saved_rules 提前返回、不触发刷新，这里统一刷首屏一次
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
        theme_seg.set(DEFAULT_THEME_CHOICE)
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
        settings_dialog.open(self, self.ctx, self.toc_widgets["table"])

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

    # ------------------------------------------------------------ 业务占位
    # TODO: 接 core 后逐一实现；在此之前都是空函数，点了没反应。
    # 表单初值与收集见 README：`core.config.DEFAULTS` → 反向填 UI，`UI → Config`。

    def _pick_input(self) -> None: ...

    def _pick_output(self) -> None: ...

    def _pick_cover(self) -> None: ...

    def _pick_font(self) -> None: ...

    def _pick_css(self) -> None: ...

    def _clear_css(self) -> None: ...

    def _load_builtin_css(self) -> None: ...

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

    def _on_generate(self) -> None: ...

    def _on_scan(self) -> None:
        """扫描输入文件，更新 `ctx.toc_entries`，然后触发目录预览刷新。

        目前 `ctx.config` 为空（TODO），先用 core 的 `DEFAULTS` 作为参数模板，等
        收集阶段接上后再换成用户表单的实际值。
        """
        input_path = self.tab_widgets["basic"]["input_entry"].get().strip()
        if not input_path:
            return
        try:
            lines, _encoding = read_lines(input_path)
        except OSError as e:
            messagebox.showerror("读取失败", f"无法读取输入文件：{e}")
            return
        except EncodingError as e:
            messagebox.showerror("编码错误", str(e))
            return
        try:
            tree, _stats = scan_toc(lines, DEFAULTS)
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
            results = preview_titles(
                _entries_to_nodes(old_entries), rules_list
            )
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

    def _apply_saved_rules(self) -> None:
        """启动时若有存档的替换规则，重建卡片；没有就保留默认那张空卡。

        这里不触发预览刷新（`fire` 传空操作 → 批量建卡、不逐卡触发），
        由 `__init__` 末尾统一刷一次，避免首屏白刷两遍。
        """
        saved = self._saved_settings.get("replacements")
        if not saved:
            return
        try:
            saved_rules = rules_from_list(saved)
        except ValueError as e:
            self._set_status(f"配置里的替换规则无效：{e}", "error")
            return
        replace_tab = self.tab_widgets["replace"]
        fill_rules(
            replace_tab["rule_cards"],
            saved_rules,
            replace_tab["add_card"],
            fire=lambda: None,
        )

    def _collect_saved(self) -> dict[str, Any]:
        """收集要落盘的配置子集（其余项每次启动只用默认值）。

        `int` 字段按类型存成数字；提示型字段（`max_title_len` / `preface_title`）
        留空表示「用默认」，直接不写进文件，免得 JSON 里一堆空串噪音。
        """
        layout_tab = self.tab_widgets["layout"]
        data: dict[str, Any] = {
            "indent": _as_stored("indent", layout_tab["indent"].get()),
            "line_height": layout_tab["line_height"].get(),
            "para_spacing": layout_tab["para_spacing"].get(),
            "volume_align": ALIGN_LABELS[layout_tab["align_volume"].get()],
            "chapter_align": ALIGN_LABELS[layout_tab["align_chapter"].get()],
            "body_align": ALIGN_LABELS[layout_tab["align_body"].get()],
            "replacements": rules_to_list(
                collect_rules(self.tab_widgets["replace"]["rule_cards"])
            ),
        }
        rule_entries = self.tab_widgets["rules"]["rule_entries"]
        for label, opt_name, mode in rules.BUILTIN_ROWS:
            value = _as_stored(opt_name, rule_entries[label].get())
            # 提示型字段空 = 用默认，跳过；预填型（卷/章/排除）空 = 用户主动清空，保留
            if value is None or (value == "" and mode == rules.HINT):
                continue
            data[opt_name] = value
        return {key: value for key, value in data.items() if value is not None}

    def _on_close(self) -> None:
        """关闭窗口前把当前配置写盘；写失败只提示，不挡关闭。"""
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
