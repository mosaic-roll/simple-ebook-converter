"""CTk GUI 入口：直接运行即可，无需依赖 CLI/core。

    pip install "simple-ebook-converter[gui-ctk]"
    python -m simple_ebook_converter.gui_ctk
    simple-ebook-converter-ctk
"""

from __future__ import annotations

import sys


def main() -> int:
    try:
        import customtkinter  # noqa: F401
    except ImportError:
        print(
            "CTk 图形界面需要额外依赖 customtkinter。\n"
            '请安装：pip install "simple-ebook-converter[gui-ctk]"\n'
            "（只用命令行的话：simple-ebook-converter-cli --help）",
            file=sys.stderr,
        )
        return 3

    from .app import App
    App().mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
