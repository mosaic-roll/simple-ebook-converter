"""统一启动入口：供 PyInstaller 打包使用。

通过 `--cli` 参数区分 CLI 模式和 GUI 模式：
- `launcher.py --cli` 启动命令行前端（对应 `simple-ebook-converter-cli`）
- 不带参数启动图形界面（对应 `simple-ebook-converter`）

`--cli` 会在交给 Click 之前从 `sys.argv` 中移除，避免 Click 把它当成
业务参数而报 `No such option '--cli'`。

直接用 `uv run simple-ebook-converter[-cli]` 时入口是 `cli.cli:main` / `gui.__main__:main`，
这个文件只用于 PyInstaller 打包，避免相对导入失败。
"""

import sys

from simple_ebook_converter.cli.cli import main as cli_main
from simple_ebook_converter.gui.__main__ import main as gui_main


def main() -> int:
    if "--cli" in sys.argv:
        sys.argv.remove("--cli")
        return cli_main()
    return gui_main()


if __name__ == "__main__":
    raise SystemExit(main())