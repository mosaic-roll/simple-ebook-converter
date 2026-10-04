"""图形界面入口：直接运行即可。

pip install "simple-ebook-converter[gui]"
python -m simple_ebook_converter.gui
simple-ebook-converter

默认配置在程序同目录（脚本模式下是当前工作目录）的 `config/config.json`；
也可用 `--config-dir` 指定其他目录。
"""

from __future__ import annotations

from pathlib import Path

import click

from .._meta import DIST_NAME


@click.command()
@click.option(
    "--config-dir",
    type=click.Path(file_okay=False, path_type=Path),
    default=None,
    help="配置目录（默认：程序同目录下的 config/）",
)
@click.version_option(package_name=DIST_NAME)
def main(config_dir: Path | None = None) -> int:
    # customtkinter 是可选依赖，这两处 import 必须留在函数体内：挪到模块顶部，缺依赖时
    # 会先抛一个不友好的 ImportError，下面这段提示就没机会执行（`.app` 顶层也 import 它）。
    try:
        import customtkinter  # noqa: F401
    except ImportError:
        click.echo(
            "图形界面需要额外依赖 customtkinter。\n"
            '请安装：pip install "simple-ebook-converter[gui]"\n'
            "（只用命令行的话：simple-ebook-converter-cli --help）",
            err=True,
        )
        return 3

    from .app import App

    App(config_dir=config_dir).mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
