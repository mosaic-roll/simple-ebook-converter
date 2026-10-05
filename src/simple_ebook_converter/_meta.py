"""distribution 名与版本号的唯一真源。

版本号全项目只有 `pyproject.toml` 的 `[project] version` 一处，这里在运行时读出来，
谁都不许再写死第二份。`DIST_NAME` 则是唯一必须写死在代码里的字符串：它要精确匹配
`pyproject.toml` 的 `[project] name`（含连字符），代码才能查到自己的元数据。
tests 里的 test_api 会独立断言这一致性，所以改包名时漏掉这里会被测出来。

本模块刻意不导入任何项目内模块，这样顶层包可以零依赖地暴露 `__version__`。
PyInstaller 打包时用 `--copy-metadata=<DIST_NAME>` 把元数据拷进可执行文件，
否则冻结后的程序 `importlib.metadata.version()` 会抛 `PackageNotFoundError`。
"""

from importlib.metadata import version

#: distribution 名，必须与 pyproject.toml 的 `[project] name` 完全一致
DIST_NAME = "simple-ebook-converter"

#: 导入包名。Python 标识符不能含连字符，所以按名称规范化规则把 DIST_NAME 的
#: 连字符换成下划线；两者指向同一个 distribution（`-`/`_`/`.` 规范化后等价）。
IMPORT_NAME = DIST_NAME.replace("-", "_")

#: 命令行入口名，必须与 pyproject.toml 的 `[project.scripts]` 一致
CLI_PROG = f"{DIST_NAME}-cli"

#: 版本号以 pyproject.toml 为唯一真源
__version__ = version(DIST_NAME)
