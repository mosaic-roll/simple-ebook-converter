"""sec：TXT → EPUB3 工具集。

一个 distribution 装三个顶层子包：

- `sec.core`  核心库（无前端依赖，唯一入口 `process()`）
- `sec.cli`   命令行前端，入口点 `sec-cli`
- `sec.gui`   图形界面前端，入口点 `sec-gui`

`sec` 本身不导出业务函数，只作为命名空间；请从具体子包导入。
"""

from importlib.metadata import version

#: 版本号以 pyproject.toml 为唯一真源
__version__ = version("sec")

__all__ = ["__version__"]
