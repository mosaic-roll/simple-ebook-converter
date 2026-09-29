"""图形界面前端：只做交互与展示；通用逻辑一律走 `simple_ebook_converter.core`。

本包不 import `customtkinter`，用不到界面的工具（脚本、文档生成）导入它不会
拉起图形依赖；`python -m simple_ebook_converter.gui` 才会真正建窗口。
"""

from .._meta import __version__

__all__ = ["__version__"]
