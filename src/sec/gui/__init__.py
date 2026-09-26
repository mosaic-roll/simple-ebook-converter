"""图形界面前端：只做交互与展示；通用逻辑一律走 `sec.core`。"""

from importlib.metadata import version

#: 与 `sec`、`sec.core` 同源，都是 pyproject.toml 里那一个版本号
__version__ = version("sec")

__all__ = ["__version__"]
