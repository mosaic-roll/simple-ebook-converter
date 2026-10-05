"""图形界面版的打包入口。

和 `entry_cli.py` 同理：这里只做绝对导入转发，让 PyInstaller 有个能当
`__main__` 跑的脚本，从而绕开 `gui/__main__.py` 里的相对导入。

控制台行为不在代码里处理，而是由 spec 里 `EXE(console=False)` 决定，
双击不会有控制台窗口。
"""

from simple_ebook_converter.gui.__main__ import main

if __name__ == "__main__":
    raise SystemExit(main())
