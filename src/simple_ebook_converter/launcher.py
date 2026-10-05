"""统一启动入口：供 PyInstaller 打包使用。

- 不带参数（桌面双击）：脱离控制台后启动图形界面，双击看不到任何黑框
- 带 `--cli`：进入命令行模式，控制台保持连接，`--cli` 之后的参数原样转交命令行前端

控制台为什么用 `FreeConsole` 而不是 `ShowWindow(SW_HIDE)`：

- 双击时控制台是本进程独占创建的，`FreeConsole` 一断开它就彻底消失，
  不会像 `SW_HIDE` 那样出现"像最小化"的观感
- 实测 `ShowWindow(SW_HIDE)` 虽然能让 `IsWindowVisible=0`，但用户反馈体验不好
- 代价是脱离后 `print()` 无处可去，GUI 若崩溃则没有 traceback 可看；
  需要双击绝对无黑框又要在出错时能看到信息，请用 `--noconsole` 的桌面版
  （它没有控制台可脱离，报错同样不可见），或在终端里跑源码版

对 `--noconsole` 打包的桌面版调用 `FreeConsole` 是无害的：本来就没有控制台，
调用只会失败并被忽略。

直接用 `uv run simple-ebook-converter[-cli]` 时入口是 `cli.cli:main` / `gui.__main__:main`，
这个文件只用于 PyInstaller 打包，避免相对导入失败。
"""

import sys
from pathlib import Path

import click

from simple_ebook_converter.cli.cli import main as cli_main
from simple_ebook_converter.gui.__main__ import main as gui_main


def _free_console() -> None:
    """脱离当前控制台，让双击启动时的控制台窗口消失。

    从已有终端启动时只会断开自己，不会关掉那个终端窗口。失败一律静默忽略，
    脱离失败最多是留个黑框，不能因此让 GUI 起不来。
    """
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.kernel32.FreeConsole()
    except Exception:  # noqa: BLE001, S110 - 脱离失败不应影响 GUI 启动
        pass


@click.command(
    "simple-ebook-converter",
    context_settings={"ignore_unknown_options": True},
)
@click.option("--cli", "cli_mode", is_flag=True, help="进入命令行模式")
@click.version_option(package_name="simple-ebook-converter")
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def launcher(cli_mode: bool, args: tuple[str, ...]) -> None:
    """默认启动桌面图形界面，并脱离控制台窗口。

    \b
    使用 --cli 进入命令行模式，此时控制台保持连接、输出正常，
    --cli 之后的参数原样转交给命令行前端。例如：
    \b
        simple-ebook-converter-versatile --cli --help
        simple-ebook-converter-versatile --cli book.txt -e gb18030
        simple-ebook-converter-versatile --cli --dump-css base.css
    """
    if cli_mode:
        cli_main(argv=list(args))
        return

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
