"""端到端测试：走真实后台线程，从界面一路跑到出 EPUB 文件。

前面的测试要么只碰纯数据层，要么一次只碰一个控件，都**结构性地**看不到线程相关的
问题。本轮两个最严重的 bug 都在这一层，且都不会在别的测试里显形：

- 后台线程里 `root.after()` → `RuntimeError`，于是重扫/生成**永远收不了尾**，
  状态栏 busy 卡死，按钮全灰。
- `App.apply_settings()` 读的是早已不存在的 `data.basic` → 启动即崩。

这两条单测里都看不出来，只有让线程真的跑起来、让 Tk 事件循环真的转起来才会暴露。
所以这里不 mock `pipeline`，用真的 `scan_toc` / `write_epub`，产物用 zipfile 验。
"""

from __future__ import annotations

import time
import zipfile
from collections.abc import Callable
from pathlib import Path

import pytest

from simple_ebook_converter.core.replace import Rule
from simple_ebook_converter.gui import dpi, fonts, metrics, theme
from simple_ebook_converter.gui.app import App
from simple_ebook_converter.gui.widgets.toc_panel import CHECK, RESULT, TITLE

#: 等后台任务的最长时间。真跑一遍是毫秒级，给足余量给慢机器。
WAIT_S = 20.0

SAMPLE = "第一章 开始\n这是正文。\n第二章 结束\n还是正文。\n"


def _pump(root, done: Callable[[], bool]) -> None:
    """转事件循环直到 `done()` 为真或超时。Tk 没有 `wait_until`，只能自己轮。"""
    deadline = time.time() + WAIT_S
    while not done() and time.time() < deadline:
        root.update()
        time.sleep(0.01)
    root.update()
    assert done(), f"{WAIT_S:.0f}s 内后台任务没结束（状态栏多半是卡在 busy 了）"


@pytest.fixture
def app(tk_root, monkeypatch, tmp_path):
    """建好 App 的实例，屏蔽真实设置文件的读写。"""
    import simple_ebook_converter.gui.app as app_mod
    import simple_ebook_converter.gui.settings as settings_mod

    monkeypatch.setattr(settings_mod, "load_settings", lambda: settings_mod.Settings())
    monkeypatch.setattr(app_mod, "load_settings", lambda: settings_mod.Settings())
    monkeypatch.setattr(app_mod, "save_settings", lambda data: None)
    monkeypatch.setattr(app_mod, "messagebox", _no_dialogs())

    instance = app_mod.App(tk_root)
    yield instance
    instance.main.stop()
    instance.destroy()


def _no_dialogs():
    """弹窗会挂起测试。`ask*` 返回「取消」，`show*` 静默。"""
    import simple_ebook_converter.gui.app as app_mod

    class _Box:
        @staticmethod
        def showerror(*a, **k):
            return None

        @staticmethod
        def showwarning(*a, **k):
            return None

        @staticmethod
        def askyesno(*a, **k):
            return False

    return _Box()


def _prepare(app: App, tmp_path: Path) -> tuple[Path, Path]:
    src = tmp_path / "sample.txt"
    src.write_text(SAMPLE, encoding="utf-8")
    out = tmp_path / "book.epub"
    app.tabs["basic"].set_input(str(src))
    app.tabs["basic"].out_row.set(str(out))
    return src, out


def test_rescan_completes_through_worker_thread(app, tk_root, tmp_path) -> None:
    """重扫要在真线程里跑完，busy 必须收掉，目录面板要拿到条目。"""
    _prepare(app, tmp_path)

    app.rescan()
    _pump(tk_root, lambda: not app.status.busy)

    assert app.status.busy is False, "busy 没收掉：线程回主线程的通道断了"
    assert len(app._toc_entries) == 2
    titles = [app.toc.tree.set(i, TITLE).strip() for i in app.toc.tree.get_children("")]
    assert "第一章 开始" in titles
    assert "第二章 结束" in titles
    assert "utf-8" in app.status.detail.cget("text")


def test_generate_writes_a_valid_epub_through_worker_thread(app, tk_root, tmp_path) -> None:
    """从界面点到出文件，全程走真线程。"""
    _prepare(app, tmp_path)

    app.generate()
    _pump(tk_root, lambda: not app.status.busy)

    out = tmp_path / "book.epub"
    assert app.status.busy is False
    assert out.exists(), f"没出文件：{app.status.text.cget('text')}"

    # 产物本身要像个 EPUB：能解压、有目录、有样式。
    with zipfile.ZipFile(out) as zf:
        assert zf.testzip() is None, "zip 损坏"
        names = zf.namelist()
        assert "mimetype" in names
        assert any("toc" in n.lower() for n in names), "没有目录"
        assert any(n.endswith(".css") for n in names), "没有样式"
        container = zf.read("META-INF/container.xml").decode("utf-8")
        assert "content.opf" in container


def test_replacement_rules_reach_the_generated_book(app, tk_root, tmp_path) -> None:
    """规则真的进了产物，而不只是显示在预览列里。

    预览列对了不等于生成对了：两条路用的是不同的数据源（一个读界面，一个读
    build_config_from_ui 产出的 Config）。这里拆穿这一点。
    """
    _prepare(app, tmp_path)
    app.tabs["replace"].editor.set_rows([("第一章", "Chapter One", "原文")])

    app.rescan()
    _pump(tk_root, lambda: not app.status.busy)
    app.generate()
    _pump(tk_root, lambda: not app.status.busy)

    out = tmp_path / "book.epub"
    with zipfile.ZipFile(out) as zf:
        ncx = next(n for n in zf.namelist() if n.lower().endswith(".ncx"))
        body = zf.read(ncx).decode("utf-8")
    assert "Chapter One" in body
    assert "第一章" not in body, "规则没生效"
    # 只替换命中的那条
    assert "第二章" in body


def test_busy_blocks_duplicate_generate(app, tk_root, tmp_path) -> None:
    """连点生成不排队，第二次直接忽略。"""
    _prepare(app, tmp_path)
    app.status.begin("占位")  # 假装正在忙
    app.generate()
    tk_root.update()
    # 没进 work()，所以既没有开始新的忙状态，也没出文件
    assert app.status.text.cget("text") == "占位"
    assert not (tmp_path / "book.epub").exists()
    app.status.ok("收工")
