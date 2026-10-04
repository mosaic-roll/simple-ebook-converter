"""simple-ebook-converter：TXT → EPUB3 工具集。

一个 distribution 装三个顶层子包：

- `simple_ebook_converter.core`  核心库（无前端依赖，两个前端的入口都在这层）
- `simple_ebook_converter.cli`   命令行前端，入口点 `simple-ebook-converter-cli`
- `simple_ebook_converter.gui`   图形界面前端（customtkinter），入口点 `simple-ebook-converter`

顶层包本身不导出业务函数，只作为命名空间；请从具体子包导入。
"""

from ._meta import __version__

__all__ = ["__version__"]
