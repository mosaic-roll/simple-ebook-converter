"""统一启动入口：供 PyInstaller 打包使用。

- 不带参数（桌面双击）：隐藏控制台窗口，启动图形界面
- 带 `--cli`：保持控制台可见，进入命令行模式，`--cli` 之后的参数原样转交命令行前端

之所以能在同一个 exe 里兼顾两者，是因为打包时保留 console 子系统，
GUI 模式由本模块在运行时调用 `ShowWindow(GetConsoleWindow(), 0)` 隐藏控制台；
若打包成 `--noconsole`，`--cli` 模式将没有任何 stdout 可写。

直接用 `uv run simple-ebook-converter[-cli]` 时入口是 `cli.cli:main` / `gui.__main__:main`，
这个文件只用于 PyInstaller 打包，避免相对导入失败。
"""

import sys

import click

from simple_ebook_converter.cli.cli import main as cli_main
from simple_ebook_converter.gui.__main__ import main as gui_main


def _set_console_visible(visible: bool) -> None:
    """显示/隐藏本进程的控制台窗口。

    `GetConsoleWindow` 在 kernel32，`ShowWindow` 在 user32，写错模块会抛
    `AttributeError`；这里兜住所有异常，宁可不隐藏也不能让 GUI 起不来。
    """
    if sys.platform != "win32":
        return
    try:
        import ctypes

        hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if hwnd:
            # SW_HIDE=0, SW_SHOW=5
            ctypes.windll.user32.ShowWindow(hwnd, 5 if visible else 0)
    except Exception:  # noqa: BLE001, S110 - 隐藏失败不应影响 GUI 启动
        pass


@click.command(
    "simple-ebook-converter",
    context_settings={"ignore_unknown_options": True},
)
@click.option(
    "--cli", "cli_mode", is_flag=True, help="进入命令行模式，控制台窗口保持可见"
)
@click.version_option(package_name="simple-ebook-converter")
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
@click.pass_context
def launcher(ctx: click.Context, cli_mode: bool, args: tuple[str, ...]) -> None:
    """默认启动桌面图形界面，控制台窗口会自动隐藏。

    \b
    使用 --cli 进入命令行模式，此时控制台窗口保持可见，
    --cli 之后的参数原样转交给命令行前端。例如：
    \b
        simple-ebook-converter --cli --help
        simple-ebook-converter --cli book.txt -e gb18030
        simple-ebook-converter --cli --dump-css base.css
    """
    if cli_mode:
        cli_main(argv=list(args))
        return

    _set_console_visible(False)
    try:
        gui_main.main(
            args=list(args), prog_name="simple-ebook-converter", standalone_mode=True
        )
    except SystemExit:
        raise
    except BaseException:
        # 控制台已隐藏，GUI 启动失败时若不恢复就什么都看不到，只会闪一下就消失
        _set_console_visible(True)
        raise


def main() -> int:
    argv = sys.argv[1:]
    # `--cli --help` 时把帮助完整交给命令行前端，而不是显示 launcher 的帮助
    if "--cli" in argv and "--help" in argv:
        cli_main(argv=[arg for arg in argv if arg != "--cli"])
        return 0
    launcher.main()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
