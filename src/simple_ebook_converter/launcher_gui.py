"""GUI 启动入口：用绝对导入避免相对导入在 PyInstaller 中失败。"""

from __future__ import annotations

from simple_ebook_converter.gui.__main__ import main

if __name__ == "__main__":
    raise SystemExit(main())
