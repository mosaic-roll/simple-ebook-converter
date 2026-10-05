"""命令行版的打包入口。

PyInstaller 会把入口脚本当成 `__main__` 执行，所以不能直接把
`simple_ebook_converter/cli/cli.py` 交给它：那里的 `from .._meta import ...`
是相对导入，脱离包上下文会报
`attempted relative import with no known parent package`。

这个文件只做一件事——用绝对导入把控制权交给真正的前端，不含任何分派逻辑。
"""

from simple_ebook_converter.cli.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
