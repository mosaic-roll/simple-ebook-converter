"""统一启动入口：供 PyInstaller 打包使用。

通过检查环境变量 `SE_EBOOK_LAUNCH_CLI` 区分 CLI 模式和 GUI 模式：
- 设置了 `SE_EBOOK_LAUNCH_CLI=1` 时启动命令行前端（对应 `simple-ebook-converter-cli`）
- 默认启动图形界面（对应 `simple-ebook-converter`）

直接用 `uv run simple-ebook-converter[-cli]` 时入口是 `cli.cli:main` / `gui.__main__:main`，
这个文件只用于 PyInstaller 打包，避免相对导入失败。
"""

import os
import sys

from simple_ebook_converter.cli.cli import main as cli_main
from simple_ebook_converter.gui.__main__ import main as gui_main


def main() -> int:
    if os.environ.get("SE_EBOOK_LAUNCH_CLI") == "1":
        # 把环境变量从 argv 里清掉，避免 Click 收到奇怪的参数
        return cli_main()
    return gui_main()


if __name__ == "__main__":
    raise SystemExit(main())
