"""sec-cli 命令行前端；核心实现见 sec-core（sec_core）。"""

from importlib.metadata import version

from .cli import main

__all__ = ["main"]
#: 版本号以 pyproject.toml 为唯一真源
__version__ = version("sec-cli")
