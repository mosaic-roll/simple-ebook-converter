"""主窗口：把四个页签、目录面板、状态栏和几个动作按钮装起来。

## 线程

Tk **不是线程安全的**：任何控件只能在主线程上碰。读文件、扫目录、生成 EPUB 都在
后台线程跑，算完 `StatusBar.on_main()` 回主线程更新界面。

**busy 期间不排队**：用户连点「生成」时第二次点击直接被忽略，不排队、不取消、
不提示。理由是这些操作对同一份输入文件做的是同一件事，排队只会让用户以为程序
卡住了；而排队逻辑（取消、合并请求）比「忽略」复杂得多，收益却只是少点一次。
生成结束按钮自动恢复。

## 防抖

改识别设置后要重扫目录，重扫要读整个文件。逐字重扫会让界面卡住，所以
`after()` 计时 300ms，期间再有改动就重新计时。busy 期间不排防抖 —— 生成用的
就是当前配置，扫完自然会显示最新的目录。

`after()` 返回的 id 存在 `_debounce_id` 里，**必须**在真正执行前清掉：否则一个早就
被取消的回调之后仍会触发，导致「停止输入很久了目录还在跳」。
"""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from ..core import pipeline
from ..core.builder import builtin_css
from ..core.config import DEFAULTS
from ..core.levels import build_levels
from ..core.replace import rules_to_json
from ..core.toc import to_json
from .build_config_from_ui import (
    CSS_NONE,
    TocSettings,
    UiValues,
    build_config_from_ui,
    preview_replacements,
    write_temp_css,
)
from .fonts import actual_family
from .metrics import s
from .settings import Settings, load_settings, save_settings
from .tabs.basic import BasicTab
from .tabs.identify import IdentifyTab
from .tabs.replace import ReplaceTab
from .tabs.typography import TypographyTab
from .theme import border_color_supported
from .widgets.scroll_frame import ScrollFrame
from .widgets.status_bar import StatusBar
from .widgets.toc_panel import TocPanel

#: 改识别设置后重扫目录的防抖间隔（毫秒）
RESCAN_DEBOUNCE_MS = 300

#: 窗口初始尺寸（设计稿像素）
INITIAL_SIZE = (1100, 760)
MIN_SIZE = (900, 600)


class App(ttk.Frame):
    """主窗口内容。`root` 由 `__main__.main()` 建好并传进来。"""

    def __init__(self, root: tk.Tk) -> None:
        super().__init__(root, padding=0)
        self.root = root
        self._debounce_id: str | None = None
        self._toc_entries: list[dict] = []
        self._scan_running = False

        self.pack(fill="both", expand=True)
        self._build()
        self._load()

        self._install_shortcuts()
        self.protocol("WM_DELETE_WINDOW", self.quit)

    # ---------- 布局 ----------

    def _build(self) -> None:
        root = self.root
        root.title("TXT 转 EPUB")
        root.geometry(f"{s(INITIAL_SIZE[0])}x{s(INITIAL_SIZE[1])}")
        root.minsize(s(MIN_SIZE[0]), s(MIN_SIZE[1]))

        # 动作条在最上：生成是主要动作，放顶部比放底部好找
        self._build_actions()

        panes = ttk.PanedWindow(self, orient="horizontal")
        panes.pack(fill="both", expand=True, padx=s(8), pady=s(4))

        left = ttk.Frame(panes)
        panes.add(left, weight=3)
        self._build_left(left)

        right = ttk.Frame(panes)
        panes.add(right, weight=4)
        self._build_right(right)

        self.status = StatusBar(self)
        self.status.pack(fill="x", padx=s(8), pady=(0, s(6)))

    def _build_actions(self) -> None:
        bar = ttk.Frame(self)
        bar.pack(fill="x", padx=s(8), pady=(s(8), s(4)))
        self.btn_generate = ttk.Button(
            bar, text="生成 EPUB", style="Accent.TButton", command=self.generate
        )
        self.btn_generate.pack(side="left")
        ttk.Button(bar, text="载入内置 CSS", command=self.dump_css).pack(
            side="left", padx=(s(8), 0)
        )
        ttk.Button(bar, text="导出目录 JSON", command=self.export_toc).pack(
            side="left", padx=(s(4), 0)
        )
        self.v_font_note = tk.StringVar()
        ttk.Label(bar, textvariable=self.v_font_note, style="Muted.TLabel").pack(side="right")

    def _build_left(self, parent: ttk.Frame) -> None:
        notebook = ttk.Notebook(parent)
        notebook.pack(fill="both", expand=True)
        self.tabs = {}
        for key, label, factory in (
            ("basic", "基础", BasicTab),
            ("identify", "识别", IdentifyTab),
            ("replace", "替换", ReplaceTab),
            ("typography", "排版", TypographyTab),
        ):
            tab = factory(notebook, on_change=self._schedule_rescan)
            notebook.add(tab, text=label)
            self.tabs[key] = tab
        # 基础页换输入文件要重扫，其余页只改排版/替换，不必重扫
        self.tabs["basic"].on_input_chosen = lambda _p: self.rescan()

    def _build_right(self, parent: ttk.Frame) -> None:
        ttk.Label(parent, text="目录", font=("Segoe UI", 11, "bold")).pack(anchor="w")
        box = ttk.Frame(parent)
        box.pack(fill="both", expand=True, pady=(s(4), 0))
        self.toc = TocPanel(
            box,
            on_rescan=self.rescan,
            on_import=self.import_toc,
            on_export=self.export_toc,
            on_setting_change=self._schedule_rescan,
        )
        self.toc.pack(fill="both", expand=True)

    # ---------- 快捷键 ----------

    def _install_shortcuts(self) -> None:
        self.root.bind("<Control-o>", lambda _e: self._browse_input())
        self.root.bind("<Control-s>", lambda _e: self.generate())
        self.root.bind("<Control-g>", lambda _e: self.rescan())
        self.root.bind("<F5>", lambda _e: self.rescan())

    def _browse_input(self) -> None:
        path = filedialog.askopenfilename(
            title="选择输入文件", filetypes=[("文本", "*.txt"), ("所有文件", "*.*")]
        )
        if path:
            self.tabs["basic"].set_input(path)
            self.rescan()

    # ---------- 值 ----------

    def collect(self) -> UiValues:
        """四个页签 + 目录面板 → `UiValues`。不解释、不校验。"""
        return UiValues(
            basic=self.tabs["basic"].get(),
            identify=self.tabs["identify"].get(),
            typography=self.tabs["typography"].get(),
            toc=self.toc.get_toc_settings(),
            rules=self.tabs["replace"].get_rows(),
        )

    def apply_settings(self, data: Settings) -> None:
        self.tabs["basic"].set(data.basic)
        self.tabs["identify"].set(data.identify)
        self.tabs["typography"].set(data.typography)
        self.toc.set_toc_settings(data.toc)
        self.tabs["replace"].set_rows(data.rules)
        self._temp_css = data.temp_css

    def _load(self) -> None:
        data = load_settings()
        self._temp_css: Path | None = None
        self.apply_settings(data)
        self._probe_borders()
        self.v_font_note.set(f"界面字体：{actual_family('ui')}")
        self.status.set_detail("就绪")
        if data.basic.input:
            self.rescan()

    def _probe_borders(self) -> None:
        """红/黄框只 clam 支持。主题认不认 `bordercolor` 探一次，不认就只留文字提示。"""
        if border_color_supported(self.root):
            for key in ("basic", "typography"):
                self.tabs[key].detect_border_support(self.root)
        self.status.set_detail("")

    # ---------- 目录扫描 ----------

    def _schedule_rescan(self) -> None:
        """改设置后延迟重扫。**busy 期间不排**——生成用的就是当前配置。"""
        if self.status.busy:
            return
        if self._debounce_id is not None:
            self.root.after_cancel(self._debounce_id)
        self._debounce_id = self.root.after(RESCAN_DEBOUNCE_MS, self.rescan)

    def rescan(self) -> None:
        """重扫目录。真正干活在后台线程。"""
        # 先清掉待执行的防抖回调，否则手动触发后还会再扫一遍
        if self._debounce_id is not None:
            self.root.after_cancel(self._debounce_id)
            self._debounce_id = None
        if self.status.busy:
            return
        path = self.tabs["basic"].input_row.get()
        if not path:
            self._show_entries([])
            return
        cfg = self._try_config()
        if cfg is None:
            return
        self._scan_running = True
        self.status.begin("正在识别目录…")

        def work() -> None:
            try:
                resolved = pipeline.resolve(cfg)
                lines, used = pipeline.read_input(resolved)
                tree, stats = pipeline.scan_toc(lines, resolved)
                entries = to_json(tree, resolved.toc_depth)
                self.status.on_main(
                    lambda: self._scan_done(entries, stats, used, resolved.book_title)
                )
            except (ValueError, OSError) as exc:
                self.status.on_main(lambda e=exc: self._scan_failed(e))

        self._run(work)

    def _scan_done(self, entries, stats, used: str, title: str) -> None:
        self._scan_running = False
        self._show_entries(entries)
        # stats 的字段名直接来自 core.parser.ParseStats，这里只用三个已确认存在的
        self.status.ok(
            f"识别到 {len(entries)} 个标题",
            f"编码 {used} · 书名 {title}",
        )

    def _scan_failed(self, exc: Exception) -> None:
        self._scan_running = False
        self._show_entries([])
        self.status.fail(f"识别失败：{exc}")

    def _show_entries(self, entries: list[dict]) -> None:
        self._toc_entries = list(entries)
        self.toc.set_entries(entries)
        self._refresh_preview()

    def _refresh_preview(self) -> None:
        """用 raw 阶段的替换规则刷新目录预览。"""
        try:
            rules = self.tabs["replace"].editor.get_rules()
        except ValueError:
            return  # 规则还没填完，先不刷

        # 非空 dict 才显示结果列；没有规则时 set_result_column(None) 会把列收掉
        self.toc.set_result_column(preview_replacements(self._toc_entries, rules) or None)

    # ---------- 生成 ----------

    def generate(self) -> None:
        """生成 EPUB。**busy 时直接返回**，不排队。"""
        if self.status.busy:
            return
        cfg = self._try_config()
        if cfg is None:
            return
        self._temp_css = None
        self.status.begin("正在生成…")

        def work() -> None:
            try:
                book = pipeline.read_book(cfg)
                target = pipeline.write_epub(book)
                self.status.on_main(lambda t=target: self._generate_ok(t))
            except (ValueError, OSError) as exc:
                self.status.on_main(lambda e=exc: self._generate_failed(e))
            finally:
                # 临时 CSS 用完就删。它是每次生成新建的，不留会堆在 temp 里
                self.status.on_main(self._cleanup_temp_css)

        self._run(work)

    def _generate_ok(self, target: Path) -> None:
        self.status.ok(f"已生成：{target}", str(target))
        # 生成后别把输入路径忘了，下次打开还想接着改
        self._save_settings()

    def _generate_failed(self, exc: Exception) -> None:
        self.status.fail(f"生成失败：{exc}")

    def _cleanup_temp_css(self) -> None:
        path, self._temp_css = self._temp_css, None
        if path is None:
            return
        try:
            Path(path).unlink(missing_ok=True)
        except OSError:
            pass  # 删不掉临时文件不是用户该操心的事

    # ---------- 导出 ----------

    def dump_css(self) -> None:
        """把内置 CSS 模板写到文件，作改样式的起点。"""
        path = filedialog.asksaveasfilename(
            title="导出内置 CSS", defaultextension=".css", filetypes=[("CSS", "*.css")]
        )
        if not path:
            return
        try:
            Path(path).write_text(builtin_css(DEFAULTS), encoding="utf-8")
        except OSError as exc:
            self.status.fail(f"导出失败：{exc}")
            return
        self.status.ok(f"已导出内置 CSS：{path}")

    def export_toc(self) -> str:
        """把当前目录（**含划掉标记**）写成 `--toc-file` 能吃的 JSON。返回路径，取消给空串。"""
        path = filedialog.asksaveasfilename(
            title="导出目录 JSON", defaultextension=".json", filetypes=[("JSON", "*.json")]
        )
        if not path:
            return ""
        try:
            import json

            entries = self.toc.toc_entries_with_flags()
            Path(path).write_text(
                json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except OSError as exc:
            self.status.fail(f"导出失败：{exc}")
            return ""
        self.status.ok(f"已导出目录：{path}（{len(entries)} 条，其中划掉 {self.toc.deleted_count()} 条）")
        return path

    def import_toc(self) -> int:
        """导入目录 JSON。**只恢复目录表格，不改变输入文件**——行号是相对输入的。"""
        path = filedialog.askopenfilename(
            title="导入目录 JSON", filetypes=[("JSON", "*.json"), ("所有文件", "*.*")]
        )
        if not path:
            return 0
        try:
            import json

            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            messagebox.showerror("导入失败", str(exc), parent=self.root)
            return 0
        if not isinstance(data, list):
            messagebox.showerror("导入失败", "目录树必须是 JSON 列表", parent=self.root)
            return 0
        self._show_entries(data)
        self.status.ok(f"已导入目录：{path}（{len(data)} 条）")
        return len(data)

    # ---------- 配置 ----------

    def _try_config(self):
        """当前界面值 → `Config`。出错弹窗并返回 `None`（不抛出到 Tk 回调外）。"""
        try:
            return build_config_from_ui(self.collect())
        except ValueError as exc:
            self.status.fail(f"参数有误：{exc}")
            messagebox.showerror("参数有误", str(exc), parent=self.root)
            return None

    def _save_settings(self) -> None:
        values = self.collect()
        # CSS 内联文本对应一个临时文件，存进设置的是**这次会话内**的路径。
        # 重启后那个文件已经不在了，所以 to_values() 还原时只有路径、没有文本，
        # 用户会看到空框而不是自己写的 CSS。这是有意的取舍：把几百行 CSS 抄进
        # 设置文件不如提示用户用「导出内置 CSS」+ 编辑文件。
        if values.typography.css_mode != CSS_NONE and not values.typography.css_path:
            if values.typography.css_text.strip():
                values.typography.css_path = str(write_temp_css(values.typography.css_text))
        save_settings(Settings.from_values(values))

    # ---------- 生命周期 ----------

    def _run(self, work) -> None:
        """在工作线程里跑 `work`，异常不许穿出来。"""
        import threading

        def guarded() -> None:
            try:
                work()
            except Exception as exc:  # noqa: BLE001 —— 后台线程不能把异常弹到 Tk
                self.status.on_main(lambda e=exc: self.status.fail(f"出错了：{e}"))

        threading.Thread(target=guarded, daemon=True).start()

    def quit(self) -> None:
        if self.status.busy:
            if not messagebox.askyesno("还在生成", "正在生成中，确定退出？", parent=self.root):
                return
        self._cleanup_temp_css()
        self._save_settings()
        self.root.destroy()
