from __future__ import annotations

import json
import sys
from importlib.metadata import version
from pathlib import Path

import click

from sec.core.builder import build_css, build_epub
from sec.core.config import ALIGN_CHOICES, Config, LevelRule, Node, config_defaults
from sec.core.encoding import EncodingError, read_lines
from sec.core.levels import build_levels
from sec.core.parser import ParseStats
from sec.core.pipeline import process
from sec.core.replace import Rule, rules_from_json
from sec.core.toc import to_json, to_text

#: 版本号以 pyproject.toml 为唯一真源，这里读出来给 --version 用，不要再写死一份
VERSION = version("sec")

_PATH = click.Path(exists=True, dir_okay=False, path_type=Path)
_OUT_PATH = click.Path(dir_okay=False, path_type=Path)

#: 选项默认值一律取自 sec.core 的 Config，不再在 CLI 里另写一份字面量。
#: 改 Config 的默认值会同时改掉这里的行为与 --help 里显示的默认值。
_DEFAULTS = config_defaults()


def _build_levels(
    volume: str | None,
    chapter: str | None,
    section: str | None,
    extra: tuple[str, ...],
) -> list[LevelRule]:
    try:
        return build_levels(volume, chapter, section, extra)
    except ValueError as e:
        raise click.UsageError(str(e)) from e


def _load_replacements(replace_json: str | None, replace_file: Path | None) -> list[Rule]:
    if replace_json is not None and replace_file is not None:
        raise click.UsageError("--replace-json 与 --replace-file 二选一")
    if replace_json is not None:
        text = replace_json
    elif replace_file is not None:
        text = Path(replace_file).read_text(encoding="utf-8")
    else:
        return []
    try:
        return rules_from_json(text)
    except ValueError as e:
        raise click.UsageError(str(e))


def _read_input(input_path: Path, encoding: str) -> tuple[list[str], str]:
    try:
        return read_lines(input_path, encoding)
    except EncodingError as e:
        raise click.UsageError(str(e)) from e
    except OSError as e:
        raise click.UsageError(f"无法读取输入文件：{e}") from e


def _resolve_output(input_path: Path, out: Path | None) -> Path:
    if out is None:
        return input_path.with_suffix(".epub")
    if str(out) == "-":
        raise click.UsageError("二进制 EPUB 不能输出到 stdout，请省略 -o 或指定文件路径")
    if out.suffix.lower() != ".epub":
        return out.with_name(out.name + ".epub")
    return out


def _check_overwrite(path: Path, no_overwrite: bool) -> None:
    """`--no-overwrite` 时的存在性检查；二进制产物由 builder 自己写盘，故单独提供。"""
    if no_overwrite and path.exists():
        raise click.UsageError(f"输出文件已存在：{path}（去掉 --no-overwrite 覆盖）")


def _write_output(path: Path, text: str, no_overwrite: bool, what: str) -> None:
    """写文本产物，统一处理 `--no-overwrite` 与写入失败。"""
    _check_overwrite(path, no_overwrite)
    try:
        path.write_text(text, encoding="utf-8")
    except OSError as e:
        raise click.UsageError(f"无法写入{what}：{e}") from e


def _emit_toc(
    tree: list[Node], toc_depth: int, out: Path | None, fmt: str, no_overwrite: bool
) -> None:
    """`--toc-only`：目录走 stdout 或文件，都不生成 EPUB。"""
    if fmt == "json":
        text = json.dumps(to_json(tree, toc_depth), ensure_ascii=False, indent=2)
    else:
        text = to_text(tree, toc_depth)
    if out is None or str(out) == "-":
        click.echo(text)
    else:
        _write_output(out, text + "\n", no_overwrite, "目录文件")


def _emit_css(cfg: Config, dump_css: Path, no_overwrite: bool) -> None:
    """`--dump-css`：只写 CSS 就退出。"""
    _write_output(dump_css, build_css(cfg), no_overwrite, "CSS")
    click.echo(f"CSS 已写入 {dump_css}")


def _emit_epub(
    cfg: Config,
    tree: list[Node],
    stats: ParseStats,
    input_path: Path,
    out: Path | None,
    used: str,
    no_overwrite: bool,
) -> None:
    """默认路径：组装 EPUB。"""
    output = _resolve_output(input_path, out)
    _check_overwrite(output, no_overwrite)
    try:
        build_epub(cfg, tree, build_css(cfg), output)
    except (ValueError, OSError) as e:
        # 读字体/封面字节、写 EPUB 失败都在这里兜住，转成干净的用法错误而不是 traceback
        raise click.UsageError(str(e)) from e
    click.echo(f"已生成：{output}")
    click.echo(
        f"编码：{used}；卷/章/节：{stats.level_counts}；"
        f"前言：{'有' if stats.has_preface else '无'}"
    )


@click.command(context_settings={"help_option_names": ["-h", "--help"]})
@click.argument("input_txt", type=_PATH, required=False)
@click.option("-i", "--input", "input_opt", type=_PATH, help="输入 txt（也可用位置参数）")
@click.option("-e", "--encoding", default=_DEFAULTS["encoding"], show_default=True, help="输入编码，auto 为自动检测")
@click.option("--volume", help="卷标题正则，h2 + class=volume；省略则用内置规则")
@click.option("--chapter", help="章标题正则，h3 + class=chapter；省略则用内置规则")
@click.option("--section", help="节标题正则，h4 + class=section；省略则用内置规则")
@click.option("--no-volume", is_flag=True, help="无卷名模式：卷不作为标题")
@click.option("--level", "extra_levels", multiple=True, help="额外层级规则，格式 级别:正则[:类名]")
@click.option("--max-title-len", default=_DEFAULTS["max_title_len"], type=int, show_default=True, help="标题最大字数，超过视为正文")
@click.option("--preface-title", default=_DEFAULTS["preface_title"], show_default=True, help="首个标题之前的无标题段落默认名")
@click.option("--replace-json", "replace_json", default=None, help="一段 JSON 替换规则（有序列表）")
@click.option("--replace-file", type=_PATH, help="从 JSON 文件读取替换规则")
@click.option("-o", "--out", type=_OUT_PATH, help="输出文件（不含扩展名，默认取输入名；--toc-only 时不带则输出到 stdout）")
@click.option("--no-overwrite", is_flag=True, help="不覆盖已存在文件")
@click.option("--title", help="书名（未指定则从文件名猜《书名》作者：作者）")
@click.option("--author", help="作者（留空则从文件名猜，仍留空不写入元数据）")
@click.option("--date", default=None, help="出版日期，如 2024-05-13；留空则 dc:date 省略（规范可选）")
@click.option("--language", default=_DEFAULTS["language"], show_default=True)
@click.option("--cover", type=_PATH, help="封面图片路径")
@click.option("--no-clean", is_flag=True, help="不清理文本（保留空行/段首段尾空格）")
@click.option("--indent", default=_DEFAULTS["indent"], show_default=True, help="段落缩进字数，0 为不缩进")
@click.option("--line-height", default=_DEFAULTS["line_height"], show_default=True)
@click.option("--para-spacing", default=_DEFAULTS["para_spacing"], show_default=True)
@click.option("--chapter-align", type=click.Choice(ALIGN_CHOICES), default=_DEFAULTS["chapter_align"], show_default=True)
@click.option("--volume-align", type=click.Choice(ALIGN_CHOICES), default=_DEFAULTS["volume_align"], show_default=True)
@click.option("--font", type=_PATH, help="嵌入正文字体")
@click.option("--css-file", type=_PATH, help="加载外部 CSS（追加到内置样式之后）")
@click.option("--dump-css", type=_OUT_PATH, help="输出当前生效 CSS 后退出")
@click.option("--no-toc", is_flag=True, help="目录不出现在书页中（仍保留导航文档供阅读器使用）")
@click.option("--toc-depth", default=_DEFAULTS["toc_depth"], type=int, show_default=True, help="目录包含到第几级")
@click.option("--toc-only", is_flag=True, help="只输出目录（配合 --toc-format），不生成 EPUB")
@click.option("--toc-format", type=click.Choice(["text", "json"]), default="text", show_default=True)
@click.version_option(VERSION, prog_name="sec-cli")
def convert(
    input_txt: str | None,
    input_opt: Path | None,
    encoding: str,
    out: Path | None,
    no_overwrite: bool,
    title: str | None,
    author: str,
    date: str | None,
    language: str,
    cover: Path | None,
    volume: str | None,
    chapter: str | None,
    section: str | None,
    no_volume: bool,
    extra_levels: tuple[str, ...],
    max_title_len: int,
    preface_title: str,
    replace_json: str | None,
    replace_file: Path | None,
    no_clean: bool,
    indent: int,
    line_height: str,
    para_spacing: str,
    chapter_align: str,
    volume_align: str,
    font: Path | None,
    css_file: Path | None,
    dump_css: Path | None,
    no_toc: bool,
    toc_depth: int,
    toc_only: bool,
    toc_format: str,
) -> None:
    input_path = Path(input_opt) if input_opt else Path(input_txt) if input_txt else None
    if input_path is None:
        raise click.UsageError("缺少输入文件，请指定位置参数或用 -i/--input")

    cfg = Config(
        input=input_path,
        encoding=encoding,
        overwrite=not no_overwrite,
        title=title,
        author=author or "",
        date=(date or "").strip() or None,
        language=language,
        cover=cover,
        levels=_build_levels(volume, chapter, section, extra_levels),
        max_title_len=max_title_len,
        preface_title=preface_title,
        no_volume=no_volume,
        replacements=_load_replacements(replace_json, replace_file),
        no_clean=no_clean,
        no_toc=no_toc,
        toc_depth=toc_depth,
        indent=indent,
        line_height=line_height,
        para_spacing=para_spacing,
        chapter_align=chapter_align,
        volume_align=volume_align,
        font=font,
        css_file=css_file,
    )

    lines, used = _read_input(input_path, encoding)
    try:
        # process() 负责校验（含字体/封面格式）、从文件名猜书名/作者并写回 cfg
        tree, stats = process(lines, cfg)
    except ValueError as e:
        # 含 NoEnabledRulesError 与 Config.validate() 的取值范围错误
        raise click.UsageError(str(e)) from e
    if not tree:
        raise click.UsageError(f"文件为空，没有可生成的内容：{input_path.name}")

    if toc_only:
        _emit_toc(tree, toc_depth, out, toc_format, no_overwrite)
    elif dump_css is not None:
        _emit_css(cfg, dump_css, no_overwrite)
    else:
        _emit_epub(cfg, tree, stats, input_path, out, used, no_overwrite)


def main(argv: list[str] | None = None) -> None:
    args = list(sys.argv[1:] if argv is None else argv)
    try:
        convert.main(args=args, prog_name="sec-cli", standalone_mode=False)
    except click.ClickException as exc:
        exc.show()
        raise SystemExit(exc.exit_code) from exc


if __name__ == "__main__":
    main()
