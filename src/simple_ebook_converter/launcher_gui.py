"""GUI 启动入口：供 PyInstaller 打包使用。

直接用 `uv run simple-ebook-converter` 时入口是 `gui.__main__:main`，
这个文件只用于 PyInstaller 打包，避免相对导入失败。
"""

from simple_ebook_converter.gui.__main__ import main

if __name__ == "__main__":
    raise SystemExit(main())
