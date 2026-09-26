"""命令行前端：参数解析与输出；通用逻辑一律走 `simple_ebook_converter.core`。"""

from .._meta import __version__
from .cli import main

__all__ = ["__version__", "main"]
