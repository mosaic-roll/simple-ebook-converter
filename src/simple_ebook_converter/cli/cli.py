"""命令行前端：把命令行参数绑成 `Config`，交给 core，只负责显示结果。

选项表不在这里写死：`-h` 的分组、每个选项的说明与默认值都取自
`core.options.OPTIONS`，所以 core 改一次，命令行界面与 GUI 表单同时跟着变。
"""

from __future__ import annotations

import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import click

from .._meta import CLI_PROG, __version__
from ..core import jobs
from ..core.jobs import CSS, EPUB, TOC, Book, Result
from ..core.options import (
    BOOL,
    CHOICE,
    INT,
    MULTI,
    OPTIONS,
    Option,
    build_config,
    option_default,
    option_groups,
)

#: 来自 `_meta`，即 pyproject.toml 那一个版本号；这里不要再写死一份
VERSION = __version__

#: `--out` 写这个值表示输出到标准输出
STDOUT = "-"

#: 三种产出方式各自的成功提示
_DONE = {EPUB: "已生成", TOC: "目录已写入", CSS: "CSS 已写入"}


@contextmanager
def _usage_errors() -> Iterator[None]:
    """把 core 抛的 `ValueError` 转成 `click.UsageError`。

    core 的错误消息本来就是写给人看的（"封面文件不存在：…"），转一下就不会吐 traceback。
    """
    try:
        yield
    except ValueError as exc:
        raise click.UsageError(str(exc)) from exc


# ---------- 选项表 → click 参数 ----------


def _click_type(opt: Option):
    """选项类型 → click 参数类型。`--level` 这类多值项在这里只管单个值的类型。"""
    if opt.kind == INT:
        return click.INT
    if opt.kind == CHOICE:
        return click.Choice(opt.choices)
    if opt.kind == "path":
        return click.Path(exists=opt.exists, dir_okay=False, path_type=Path)
    return click.STRING


def _click_default(opt: Option):
    """click 的默认值：留空表示「未指定」，只能是 `None` 或 `()`。

    空串不能直接给 `--out`：click 会拿它去构造 `Path("")`，得到当前目录。
    层级正则也不给默认值，`--help` 里印一条几百字的正则没人看得下去。
    """
    if opt.kind == BOOL:
        return None
    if opt.kind == MULTI:
        return ()
    if opt.level is not None:
        return None
    value = option_default(opt)
    return None if value == "" else value


def _click_option(opt: Option) -> click.Option:
    default = _click_default(opt)
    attrs: dict[str, object] = {
        "help": opt.help,
        "default": default,
        "show_default": default not in (None, "", ()),
    }
    if opt.kind == BOOL:
        attrs["is_flag"] = True
    else:
        attrs["type"] = _click_type(opt)
    if opt.kind == MULTI:
        attrs["multiple"] = True
    return click.Option(list(opt.flags), **attrs)


class _GroupedHelp(click.Command):
    """`--help` 按选项表里的分组小节打印，而不是 click 默认的一长串。"""

    def format_options(self, ctx: click.Context, formatter: click.HelpFormatter) -> None:
        params = {param.name: param for param in self.params}
        listed: set[str] = set()
        for title, options in option_groups():
            rows = [params[opt.name].get_help_record(ctx) for opt in options if opt.name in params]
            listed |= {opt.name for opt in options}
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


# ---------- 产出 ----------


def _target(values: dict) -> tuple[str, str | None]:
    """三个开关挑一种产出方式，并算出它的输出路径。

    `--out` 是 click 给的 `Path`，所以拿字符串比。`-` 只对目录有意义：目录正文走
    标准输出，EPUB 是二进制文件没地方可去。
    """
    out = values.get("out")
    out = "" if out is None else str(out)
    if values.get("toc_only"):
        return TOC, None if out in ("", STDOUT) else out
    if values.get("dump_css"):
        return CSS, values["dump_css"]
    if out == STDOUT:
        raise click.UsageError("EPUB 是二进制文件，不能输出到标准输出，请用 --out 指定文件路径")
    return EPUB, out


def _report(result: Result) -> None:
    if result.path is None:
        click.echo(result.text)
        return
    click.echo(f"{_DONE[result.kind]}：{result.path}")
    if result.kind == EPUB:
        click.echo(_summary(result.book))


def _summary(book: Book) -> str:
    """给终端看的一行处理结果。"""
    counts = book.stats.level_counts
    levels = "、".join(f"h{level}×{counts[level]}" for level in sorted(counts))
    return (
        f"编码：{book.encoding}；标题：{levels or '无'}；"
        f"前言：{'有' if book.stats.has_preface else '无'}"
    )


def _convert(input_txt: Path | None, values: dict) -> None:
    if not values.get("input") and input_txt is None:
        raise click.UsageError("缺少输入文件，请指定位置参数或用 -i/--input")
    values["input"] = values.get("input") or input_txt
    kind, out = _target(values)
    with _usage_errors():
        cfg = build_config(values)
        result = jobs.run(cfg, kind, out, str(values["toc_format"]))
    _report(result)


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
def convert(input_txt: Path | None, **values) -> None:
    """把 txt 转成 EPUB。

    INPUT_TXT 也可以用 -i/--input 给；--toc-only 只输出目录，--dump-css 只输出 CSS。
    """
    _convert(input_txt, values)


for _opt in OPTIONS:
    convert.params.append(_click_option(_opt))


def main(argv: list[str] | None = None) -> None:
    args = list(sys.argv[1:] if argv is None else argv)
    try:
        convert.main(args=args, prog_name=CLI_PROG, standalone_mode=False)
    except click.ClickException as exc:
        exc.show()
        raise SystemExit(exc.exit_code) from exc


if __name__ == "__main__":
    main()
