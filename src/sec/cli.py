from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

import click

from .builder import build_css, build_epub, font_media_type
from .config import Config, LevelRule, default_levels
from .encoding import read_lines
from .meta import guess_metadata
from .pipeline import process
from .replace import Rule
from .toc import to_json, to_text

VERSION = "0.1.0"

_PATH = click.Path(exists=True, dir_okay=False, path_type=Path)
_OUT_PATH = click.Path(dir_okay=False, path_type=Path)


def _build_levels(
    volume: str | None,
    chapter: str | None,
    section: str | None,
    extra: tuple[str, ...],
) -> list[LevelRule]:
    levels = default_levels()
    presets = {2: ("volume", volume), 3: ("chapter", chapter), 4: ("section", section)}
    for level, (class_name, pat) in presets.items():
        if pat is not None:
            for r in levels:
                if r.level == level:
                    r.pattern = pat
                    r.class_name = class_name
    for spec in extra:
        parts = spec.split(":", 2)
        if len(parts) < 2:
            raise click.UsageError(f"--level 格式应为 级别:正则[:类名]，收到：{spec}")
        try:
            level = int(parts[0])
        except ValueError:
            raise click.UsageError(f"--level 级别必须是数字，收到：{parts[0]}")
        if not 1 <= level <= 6:
            raise click.UsageError(f"--level 级别需在 1~6 之间，收到：{level}")
        class_name = parts[2] if len(parts) > 2 else f"level{level}"
        for r in levels:
            if r.level == level:
                r.pattern = parts[1]
                r.class_name = class_name
                break
        else:
            levels.append(LevelRule(level, parts[1], class_name))
    return levels


def _load_replacements(replace_json: str | None, replace_file: Path | None) -> list[Rule]:
    if replace_json is not None and replace_file is not None:
        raise click.UsageError("--replace-json 与 --replace-file 二选一")
    if replace_json is not None:
        data = json.loads(replace_json)
    elif replace_file is not None:
        data = json.loads(Path(replace_file).read_text(encoding="utf-8"))
    else:
        return []
    if not isinstance(data, list):
        raise click.UsageError("替换规则必须是 JSON 列表")
    rules: list[Rule] = []
    for item in data:
        if not isinstance(item, dict) or "pattern" not in item:
            raise click.UsageError(f"替换规则条目格式错误：{item!r}")
        rules.append(Rule(item["pattern"], item.get("replace", "")))
    return rules


def _resolve_output(input_path: Path, out: Path | None) -> Path:
    if out is None:
        out = input_path.with_suffix(".epub")
    elif str(out) == "-":
        raise click.UsageError("二进制 EPUB 不能输出到 stdout，请省略 -o 或指定文件路径")
    elif out.suffix.lower() != ".epub":
        out = out.with_name(out.name + ".epub")
    return out


def _validate_date(value: str | None) -> str | None:
    if value is None:
        return None

    try:
        datetime.fromisoformat(value.strip())
    except ValueError:
        raise click.UsageError(f"--date 格式应为 YYYY-MM-DD 或 YYYY-MM-DD HH:MM[:SS]，收到：{value}")
    return value.strip()


@click.command(context_settings={"help_option_names": ["-h", "--help"]})
@click.argument("input_txt", type=_PATH, required=False)
@click.option("-i", "--input", "input_opt", type=_PATH, help="输入 txt（也可用位置参数）")
@click.option("-e", "--encoding", default="auto", show_default=True, help="输入编码，auto 为自动检测")
@click.option("--volume", help="卷标题正则，h2 + class=volume")
@click.option("--chapter", help="章标题正则，h3 + class=chapter")
@click.option("--section", help="节标题正则，h4 + class=section")
@click.option("--no-volume", is_flag=True, help="无卷名模式：卷不作为标题")
@click.option("--level", "extra_levels", multiple=True, help="额外层级规则，格式 级别:正则[:类名]")
@click.option("--max-title-len", default=35, type=int, show_default=True, help="标题最大字数，超过视为正文")
@click.option("--preface-title", default="前言", show_default=True, help="首个标题之前的无标题段落默认名")
@click.option("--replace-json", "replace_json", default=None, help="一段 JSON 替换规则（有序列表）")
@click.option("--replace-file", type=_PATH, help="从 JSON 文件读取替换规则")
@click.option("-o", "--out", type=_OUT_PATH, help="输出文件（不含扩展名，默认取输入名；--toc-only 时不带则输出到 stdout）")
@click.option("--no-overwrite", is_flag=True, help="不覆盖已存在文件")
@click.option("--title", help="书名（默认取输入文件名）")
@click.option("--author", default="", help="作者，留空则不写入元数据")
@click.option("--date", default=None, help="出版日期，如 2024-05-13；留空则 dc:date 省略（规范可选）")
@click.option("--language", default="zh", show_default=True)
@click.option("--cover", type=_PATH, help="封面图片路径")
@click.option("--no-clean", is_flag=True, help="不清理文本（保留空行/段首段尾空格）")
@click.option("--indent", default=2, show_default=True, help="段落缩进字数，0 为不缩进")
@click.option("--line-height", default="1.5", show_default=True)
@click.option("--para-spacing", default="1em", show_default=True)
@click.option("--chapter-align", type=click.Choice(["left", "center", "right"]), default="center", show_default=True)
@click.option("--volume-align", type=click.Choice(["left", "center", "right"]), default="right", show_default=True)
@click.option("--font", type=_PATH, help="嵌入正文字体")
@click.option("--css-file", type=_PATH, help="加载外部 CSS（追加到内置样式之后）")
@click.option("--dump-css", type=_OUT_PATH, help="输出当前生效 CSS 后退出")
@click.option("--no-toc", is_flag=True, help="目录不出现在书页中（仍保留导航文档供阅读器使用）")
@click.option("--toc-depth", default=6, type=int, show_default=True, help="目录包含到第几级")
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

    guessed_title, guessed_author = guess_metadata(input_path.stem)
    title = title or guessed_title
    author = author or guessed_author or ""

    cfg = Config(
        input=input_path,
        encoding=encoding,
        overwrite=not no_overwrite,
        title=title,
        author=author,
        date=_validate_date(date),
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

    lines, used = read_lines(input_path, encoding)
    fallback = title or input_path.stem
    tree, stats = process(lines, cfg, fallback)
    if not tree:
        raise click.UsageError(f"文件为空，没有可生成的内容：{input_path.name}")

    if toc_only:
        if toc_format == "json":
            content = json.dumps(to_json(tree, toc_depth), ensure_ascii=False, indent=2)
        else:
            content = to_text(tree, toc_depth)
        if out is None or str(out) == "-":
            click.echo(content)
        else:
            out.write_text(content + "\n", encoding="utf-8")
        return

    if cfg.font:
        try:
            font_media_type(cfg.font)
        except ValueError as e:
            raise click.UsageError(str(e))

    css = build_css(cfg)
    if dump_css is not None:
        dump_css.write_text(css, encoding="utf-8")
        click.echo(f"CSS 已写入 {dump_css}")
        return

    output = _resolve_output(input_path, out)
    if output.exists() and no_overwrite:
        raise click.UsageError(f"输出文件已存在：{output}（去掉 --no-overwrite 覆盖）")

    build_epub(cfg, tree, css, output)
    click.echo(f"已生成：{output}")
    click.echo(f"编码：{used}；卷/章/节：{stats.level_counts}；前言：{'有' if stats.has_preface else '无'}")


def main(argv: list[str] | None = None) -> None:
    args = list(sys.argv[1:] if argv is None else argv)
    try:
        convert.main(args=args, prog_name="sec-cli", standalone_mode=False)
    except click.ClickException as exc:
        exc.show()
        raise SystemExit(exc.exit_code) from exc


if __name__ == "__main__":
    main()