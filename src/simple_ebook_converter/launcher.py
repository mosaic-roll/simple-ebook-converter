"""统一启动入口：供 PyInstaller 打包使用。

- 不带参数（桌面双击）：启动图形界面
- 带 `--cli`：进入命令行模式，`--cli` 之后的参数原样转交命令行前端

控制台窗口在这个包里始终正常显示，不做任何隐藏：实测 `ShowWindow(SW_HIDE)`
虽然能隐藏，但用户反馈体验不好（看起来像最小化、行为也不稳定），而
`FreeConsole` 不可逆。干脆不做运行时处理：

- `simple-ebook-converter-versatile.exe`：console 子系统，控制台一直显示
- `simple-ebook-converter-gui.exe`：`--noconsole`，天生没有控制台，双击最干净
- `simple-ebook-converter-cli.exe`：exe 名以 `-cli` 结尾，自动进命令行模式

直接用 `uv run simple-ebook-converter[-cli]` 时入口是 `cli.cli:main` / `gui.__main__:main`，
这个文件只用于 PyInstaller 打包，避免相对导入失败。
"""

import sys
from pathlib import Path

import click

from simple_ebook_converter.cli.cli import main as cli_main
from simple_ebook_converter.gui.__main__ import main as gui_main


@click.command(
    "simple-ebook-converter",
    context_settings={"ignore_unknown_options": True},
)
@click.option("--cli", "cli_mode", is_flag=True, help="进入命令行模式")
@click.version_option(package_name="simple-ebook-converter")
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def launcher(cli_mode: bool, args: tuple[str, ...]) -> None:
    """默认启动桌面图形界面。

    \b
    使用 --cli 进入命令行模式，--cli 之后的参数原样转交给命令行前端。例如：
    \b
        simple-ebook-converter-versatile --cli --help
        simple-ebook-converter-versatile --cli book.txt -e gb18030
        simple-ebook-converter-versatile --cli --dump-css base.css
    \b
    控制台窗口始终正常显示；想要双击完全没有控制台，请用
    simple-ebook-converter-gui.exe。
    """
    if cli_mode:
        cli_main(argv=list(args))
        return

    if _is_freeconsole_build():
        _free_console()
    gui_main.main(
        args=list(args), prog_name="simple-ebook-converter", standalone_mode=True
    )


def _exe_stem() -> str:
    """当前可执行文件名（不含扩展名）；源码运行时是解释器名。"""
    return Path(sys.executable).stem


def _is_cli_build() -> bool:
    """专用命令行包的 exe 名以 `-cli` 结尾，双击即可直接进命令行模式。"""
    stem = _exe_stem()
    return stem.endswith(("-cli", "_cli"))


def _is_freeconsole_build() -> bool:
    """FreeConsole 试验版：exe 名以 `-freeconsole` 结尾。"""
    stem = _exe_stem()
    return stem.endswith(("-freeconsole", "_freeconsole"))


def _free_console() -> None:
    """脱离当前控制台。

    双击启动时控制台是本进程独占创建的，`FreeConsole` 一断开它就随之消失，
    比 `ShowWindow(SW_HIDE)` 更彻底。副作用是之后 `print()` 没有去处，
    GUI 若崩溃则报错无处可看，所以只用于试验对比。
    """
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.kernel32.FreeConsole()
    except Exception:  # noqa: BLE001, S110 - 脱离失败不应影响 GUI 启动
        pass


def main() -> int:
    argv = list(sys.argv[1:])
    if _is_cli_build() and "--cli" not in argv:
        argv.insert(0, "--cli")
    sys.argv = [sys.argv[0], *argv]

    # `--cli --help` 时把帮助完整交给命令行前端，而不是显示 launcher 的帮助
    if "--cli" in argv and "--help" in argv:
        cli_main(argv=[arg for arg in argv if arg != "--cli"])
        return 0
    launcher.main()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
