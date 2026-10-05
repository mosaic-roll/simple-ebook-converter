"""CLI 启动入口：供 PyInstaller 打包使用。

直接用 `uv run simple-ebook-converter-cli` 时入口是 `cli.cli:main`，
这个文件只用于 PyInstaller 打包，避免相对导入失败。
"""

from simple_ebook_converter.cli.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
