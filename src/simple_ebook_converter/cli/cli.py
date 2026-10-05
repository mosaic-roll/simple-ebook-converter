"""命令行前端：把命令行参数收成 `Config`，交给 core，只负责显示结果。

选项表不在这里写死：`-h` 的分组、每个选项的说明与默认值都取自
`core.options.OPTIONS`，所以 core 改一次，命令行界面与 GUI 表单同时跟着变。

三个产出开关就是设计文档里的三种产物：默认生成 EPUB，`--toc-only` 只输出目录
（`-o` 留空或给 `-` 时走 stdout），`--dump-css` 只导出 CSS。
"""

from __future__ import annotations

import sys
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

import click

from .._meta import CLI_PROG, __version__
from .._stdio import make_output_encoding_safe
from ..core.config import Config
from ..core.levels import parse_level_spec
from ..core.options import OPTIONS, Option, build_config, option_default, option_groups
from ..core.pipeline import (
    Book,
    read_book,
    toc_text,
    write_css,
    write_epub,
    write_toc,
)
from ..core.sources import load_sources
from ..core.validation import validate_config

#: 来自 `_meta`，即 pyproject.toml 那一个版本号；这里不要再写死一份
VERSION = __version__

#: `--out` 写这个值表示输出到标准输出
STDOUT = "-"


@contextmanager
def _usage_errors() -> Generator[None, None, None]:
    """把 core 抛的 `ValueError` 转成 `click.UsageError`。

    core 的错误消息本来就是写给人看的（"封面文件不存在：…"），转一下就不会吐 traceback。
    """
    try:
        yield
    except ValueError as exc:
        raise click.UsageError(str(exc)) from exc


# ---------- 选项表 → click 参数 ----------


def _param_name(opt: Option) -> str:
    """click 参数名：由长旗标推出（`--no-volume` → `no_volume`），与 click 自己的规则一致。"""
    return opt.flags[-1].lstrip("-").replace("-", "_")


def _click_type(opt: Option):
    """选项类型 → click 参数类型。`--level` 这类多值项只管单个值的类型。

    `allow_empty` 的选项（如 `--cover`）用 STRING：`click.Path(exists=True)` 会把空串当成
    「文件不存在」直接报错，可空串在那里恰恰有确切含义——显式说不要封面。存在性检查
    没丢，`options._path()` 照样查非空路径。
    """
    if opt.choices:
        return click.Choice(opt.choices)
    if opt.kind is Path and not opt.allow_empty:
        return click.Path(exists=not opt.output, dir_okay=False, path_type=Path)
    return click.INT if opt.kind is int else click.STRING


def _click_default(opt: Option):
    """click 的默认值：留空表示「未指定」，只能是 `None` 或 `()`。

    空串不能直接给 `--out`：click 会拿它去构造 `Path("")`，得到当前目录。层级正则也
    不给默认值，`--help` 里印一条几百字的正则没人看得下去。
    """
    if opt.kind is bool:
        # 旗标未给 = 功能维持默认；「给旗标」的语义转换（含 negative 取反）在 _convert
        return False
    if opt.multiple:
        return ()
    if opt.preset_level:
        return None
    value = option_default(opt)
    return None if value == "" else value


def _click_option(opt: Option) -> click.Option:
    """一条 `Option` → 一个 click 参数。默认值与 `Config` 字段的默认值同源。"""
    default = _click_default(opt)
    attrs: dict[str, object] = {"help": opt.help, "default": default}
    if opt.kind is bool:
        attrs |= {"is_flag": True, "flag_value": not default}
    else:
        attrs |= {
            "type": _click_type(opt),
            "show_default": default not in (None, "", ()),
        }
    if opt.multiple:
        attrs |= {"multiple": True}
    return click.Option(list(opt.flags), **attrs)


class _GroupedHelp(click.Command):
    """`--help` 按选项表里的分组小节打印，而不是 click 默认的一长串。"""

    def format_options(
        self, ctx: click.Context, formatter: click.HelpFormatter
    ) -> None:
        params = {param.name: param for param in self.params}
        listed: set[str] = set()
        for title, options in option_groups():
            rows = [params[_param_name(opt)].get_help_record(ctx) for opt in options]
            listed |= {_param_name(opt) for opt in options}
            if rows:
                with formatter.section(title):
                    formatter.write_dl(rows)
        # 位置参数在 usage 里，不进选项表；--version 之类归到「其他」
        rest = [
            record
            for param in self.params
            if param.name not in listed and isinstance(param, click.Option)
            if (record := param.get_help_record(ctx)) is not None
        ]
        if rest:
            with formatter.section("其他"):
                formatter.write_dl(rest)


# ---------- 三种产物 ----------


def _summary(book: Book) -> str:
    """给终端看的一行处理结果。"""
    counts = book.stats.level_counts
    levels = "、".join(f"h{level}×{counts[level]}" for level in sorted(counts))
    return (
        f"编码：{book.encoding}；标题：{levels or '无'}；"
        f"前言：{'有' if book.stats.has_preface else '无'}"
    )


def _produce(cfg: Config) -> None:
    """按 `cfg` 上的产出开关跑一次转换，并把结果打印到终端。"""
    if cfg.dump_css:
        click.echo(f"CSS 已写入：{write_css(cfg)}")
        return
    # 先 validate 一次再读资源：参数错（如 --css-file 与 --css-append 同时给）当场
    # 报出来，不必等资源读完、输入都解析完了才说。
    #
    # `read_book()` 内部的 `resolve()` 还会再 validate 一次，重复调用无妨：它是
    # 纯检查、无副作用，且不改动 `cfg`——`Book.cfg` 仍是 `resolve()` 的产物（补全过
    # 书名/作者的那一份），不是这里这份。
    validate_config(cfg)
    book = read_book(cfg, load_sources(cfg))
    if cfg.toc_only:
        if cfg.out is None or str(cfg.out) == STDOUT:
            click.echo(toc_text(book))
        else:
            click.echo(f"目录已写入：{write_toc(book)}")
        return
    if str(cfg.out or "") == STDOUT:
        raise click.UsageError(
            "EPUB 是二进制文件，不能输出到标准输出，请用 --out 指定文件路径"
        )
    click.echo(f"已生成：{write_epub(book)}")
    click.echo(_summary(book))


def _convert(input_txt: Path | None, params: dict) -> None:
    """把 click 收上来的参数按选项表翻译成 `Config`，再交给 core。"""
    if not (params["input"] or input_txt) and not params["dump_css"]:
        raise click.UsageError("缺少输入文件，请指定位置参数或用 -i/--input")
    values: dict = {}
    for opt in OPTIONS:
        value = params[_param_name(opt)]
        values[opt.name] = not value if opt.negative else value
    values["input"] = params["input"] or input_txt
    with _usage_errors():
        # `--level hN[.class]:正则` 是命令行的参数格式，在这一层就拆成 `LevelRule`。
        # core 内部只认结构化的级别/class/正则三项——`hN[.class]:正则` 不该渗进去。
        values["level"] = [
            parse_level_spec(spec) for spec in values["level"] or ()
        ]
        _produce(build_config(values))


@click.command(
    cls=_GroupedHelp,
    context_settings={"help_option_names": ["-h", "--help"]},
)
@click.argument(
    "input_txt",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    required=False,
)
@click.version_option(VERSION, prog_name=CLI_PROG)
def convert(input_txt: Path | None, **params) -> None:
    """把 txt 转成 EPUB。

    INPUT_TXT 也可以用 -i/--input 给；--toc-only 只输出目录，--dump-css 只输出 CSS。
    """
    _convert(input_txt, params)


for _opt in OPTIONS:
    convert.params.append(_click_option(_opt))


def main(argv: list[str] | None = None) -> None:
    # 必须早于任何输出：Click 格式化 usage 与报错时也要写中文，
    # 非 UTF-8 控制台上会抛 UnicodeEncodeError，把错误提示本身都吞掉
    make_output_encoding_safe()
    args = list(sys.argv[1:] if argv is None else argv)
    try:
        convert.main(args=args, prog_name=CLI_PROG, standalone_mode=False)
    except click.ClickException as exc:
        exc.show()
        raise SystemExit(exc.exit_code) from exc


if __name__ == "__main__":
    main()
