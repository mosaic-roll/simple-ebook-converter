"""命令行前端：参数解析与输出；通用逻辑一律走 `sec.core`。"""

from importlib.metadata import version

from .cli import main

#: 与 `sec`、`sec.core` 同源，都是 pyproject.toml 里那一个版本号
__version__ = version("sec")

__all__ = ["__version__", "main"]
