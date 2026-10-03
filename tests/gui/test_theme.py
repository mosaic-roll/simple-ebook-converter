"""`gui.theme`：目录表格的行高与配色。这里要建 Tk 控件，所以只装 CLI 跑不了。

行高那条与 DPI 有关：`rowheight` 只认像素，字号却是 pt，换算由 Tk 按 `tk scaling`
做（进程 DPI aware 时已含显示器缩放）。所以行高要量字体实际像素高，不能 pt 加常数。
"""

from tkinter import font as tkfont
from tkinter import ttk

import pytest

from simple_ebook_converter.gui.theme import ROW_EXTRA, ROW_MIN, apply_toc_font

FAMILY = "Microsoft YaHei"
SIZES = (9, 13, 16, 20, 24)


@pytest.fixture
def table(tk_root):
    """目录表格。每个用例建自己一棵，用完销毁。"""
    tree = ttk.Treeview(tk_root, columns=("a",), show="headings", height=4)
    tree.heading("a", text="标题")
    tree.insert("", "end", values=("第一卷", "第一卷"))
    yield tree
    tree.destroy()


def test_row_height_fits_font_at_every_size(table):
    """每档字号下行高都要放得下字，不然文字被截。

    之前是 `size + ROW_EXTRA`（pt 加像素），字号越大缺得越多，24 号时字被压扁。
    """
    style = ttk.Style()
    for size in SIZES:
        apply_toc_font(table, FAMILY, size)
        linespace = tkfont.Font(family=FAMILY, size=size).metrics("linespace")
        row_height = int(style.lookup("Toc.Treeview", "rowheight"))
        assert row_height >= linespace + ROW_EXTRA, (
            f"{size}pt：行高 {row_height}px 放不下 {linespace}px 的字"
        )


def test_row_height_tracks_font_pixel_height(table):
    """行高要跟着字体的像素高度走，不跟 pt 数值走。

    这是 DPI 缩放不漏的关键：150% 下 Tk 给的 linespace 比 100% 大，行高跟着变大。
    """
    style = ttk.Style()
    heights = []
    for size in SIZES:
        apply_toc_font(table, FAMILY, size)
        heights.append(int(style.lookup("Toc.Treeview", "rowheight")))
    assert heights == sorted(heights), f"字号越大行高应越大，实际 {heights}"
    assert heights[0] < heights[-1], "行高必须随字号变化，不能是固定值"


def test_row_height_never_below_minimum(table):
    """再小的字号也留够最小行高，行不会挤成一条。"""
    style = ttk.Style()
    apply_toc_font(table, FAMILY, 6)
    assert int(style.lookup("Toc.Treeview", "rowheight")) >= ROW_MIN
