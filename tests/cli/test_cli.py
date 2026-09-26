import json
import re
import zipfile
from pathlib import Path

import click
import pytest
from click.testing import CliRunner

from simple_ebook_converter.cli.cli import convert, main
from simple_ebook_converter.core.config import Config
from simple_ebook_converter.core.encoding import EncodingError
from simple_ebook_converter.core.options import OPTIONS, option_default, option_groups
from simple_ebook_converter.core.parser import NoEnabledRulesError


def _write_sample(tmp_path, name="novel.txt", text=None):
    p = tmp_path / name
    p.write_text(text or "第一卷 起源\n第一章 开端\n第一段正文\n第二段正文\n", encoding="utf-8")
    return p


def test_convert_default(tmp_path):
    src = _write_sample(tmp_path)
    result = CliRunner().invoke(convert, [str(src)])
    assert result.exit_code == 0, result.output
    out = tmp_path / "novel.epub"
    assert out.exists()
    with zipfile.ZipFile(out) as z:
        assert "META-INF/container.xml" in z.namelist()


def test_convert_overwrites_by_default(tmp_path):
    src = _write_sample(tmp_path)
    out = tmp_path / "novel.epub"
    out.write_bytes(b"existing")
    result = CliRunner().invoke(convert, [str(src)])
    assert result.exit_code == 0, result.output
    assert out.read_bytes()[:2] == b"PK"


def test_convert_no_overwrite_refuses(tmp_path):
    src = _write_sample(tmp_path)
    out = tmp_path / "novel.epub"
    out.write_bytes(b"existing")
    result = CliRunner().invoke(convert, [str(src), "--no-overwrite"])
    assert result.exit_code != 0
    assert "已存在" in result.output


def test_convert_metadata_and_replace(tmp_path):
    src = _write_sample(tmp_path, text="#第1章 开头\n# 这里有个#号\n正文段落\n")
    result = CliRunner().invoke(
        convert,
        [
            "--title",
            "我的书",
            "--author",
            "张三",
            "--chapter",
            r"^#.*",
            "--replace-json",
            json.dumps([{"pattern": r"^#\s*", "replace": ""}]),
            str(src),
        ],
    )
    assert result.exit_code == 0, result.output


def test_convert_replace_json_and_file_conflict(tmp_path):
    src = _write_sample(tmp_path)
    rf = tmp_path / "rules.json"
    rf.write_text("[]", encoding="utf-8")
    result = CliRunner().invoke(
        convert, [str(src), "--replace-json", "[]", "--replace-file", str(rf)]
    )
    assert result.exit_code != 0
    assert "只能给一处" in result.output


def test_replace_applies_to_title_and_toc(tmp_path):
    src = _write_sample(tmp_path, text="#第1章 开头\n第一段正文\n")
    result = CliRunner().invoke(
        convert,
        [
            "--chapter",
            r"^#.*",
            "--replace-json",
            json.dumps(
                [
                    {"pattern": r"^#\s*第", "replace": "章节 "},
                    {"pattern": r"#", "replace": ""},
                ]
            ),
            str(src),
        ],
    )
    assert result.exit_code == 0, result.output
    out = tmp_path / "novel.epub"
    with zipfile.ZipFile(out) as z:
        nav = next(n for n in z.namelist() if n.endswith("nav.xhtml"))
        text = z.read(nav).decode("utf-8")
        assert "章节 1章 开头" in text
        page = next(n for n in z.namelist() if n.endswith("text/p0001.xhtml"))
        content = z.read(page).decode("utf-8")
        assert "章节 1章 开头" in content


def _nav_and_page(tmp_path: Path) -> tuple[str, str]:
    """读出生成结果里的目录页与正文页文本。"""
    out = tmp_path / "novel.epub"
    with zipfile.ZipFile(out) as z:
        nav = z.read(next(n for n in z.namelist() if n.endswith("nav.xhtml"))).decode("utf-8")
        page = z.read(next(n for n in z.namelist() if n.endswith("text/p0001.xhtml"))).decode(
            "utf-8"
        )
    return nav, page


def test_replace_scope_title_leaves_body_alone(tmp_path):
    """不写 scope 就是「标题」，正文一个字都不动。"""
    src = _write_sample(tmp_path, text="#第1章 开头\n正文里有第1章\n")
    result = CliRunner().invoke(
        convert,
        [
            "--chapter",
            r"^#.*",
            "--replace-json",
            json.dumps([{"pattern": "第1章", "replace": "首章"}]),
            str(src),
        ],
    )
    assert result.exit_code == 0, result.output
    nav, page = _nav_and_page(tmp_path)
    assert "首章 开头" in nav
    assert "正文里有第1章" in page


def test_replace_scope_body_leaves_title_alone(tmp_path):
    src = _write_sample(tmp_path, text="#第1章 开头\n正文里有第1章\n")
    result = CliRunner().invoke(
        convert,
        [
            "--chapter",
            r"^#.*",
            "--replace-json",
            json.dumps([{"pattern": "第1章", "replace": "首章", "scope": "body"}]),
            str(src),
        ],
    )
    assert result.exit_code == 0, result.output
    nav, page = _nav_and_page(tmp_path)
    assert "第1章 开头" in nav
    assert "正文里有首章" in page


def test_replace_scope_all_hits_both(tmp_path):
    src = _write_sample(tmp_path, text="#第1章 开头\n正文里有第1章\n")
    result = CliRunner().invoke(
        convert,
        [
            "--chapter",
            r"^#.*",
            "--replace-json",
            json.dumps([{"pattern": "第1章", "replace": "首章", "scope": "all"}]),
            str(src),
        ],
    )
    assert result.exit_code == 0, result.output
    nav, page = _nav_and_page(tmp_path)
    assert "首章 开头" in nav
    assert "正文里有首章" in page


def test_replace_rejects_unknown_scope(tmp_path):
    src = _write_sample(tmp_path)
    result = CliRunner().invoke(
        convert,
        [str(src), "--replace-json", json.dumps([{"pattern": "a", "scope": "chapter"}])],
    )
    assert result.exit_code != 0
    assert "作用范围只能是" in result.output


def test_cover_is_discovered_next_to_input(tmp_path):
    """不给 --cover 时，同目录唯一的 cover.* 自动生效。"""
    src = _write_sample(tmp_path)
    (tmp_path / "cover.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    result = CliRunner().invoke(convert, [str(src)])
    assert result.exit_code == 0, result.output
    with zipfile.ZipFile(tmp_path / "novel.epub") as z:
        opf = z.read(next(n for n in z.namelist() if n.endswith("content.opf"))).decode("utf-8")
    assert "cover.png" in opf


def test_ambiguous_covers_are_ignored(tmp_path):
    """两个候选就不猜了，宁可没有封面。"""
    src = _write_sample(tmp_path)
    (tmp_path / "cover.png").write_bytes(b"\x89PNG")
    (tmp_path / "cover.jpg").write_bytes(b"\xff\xd8")
    result = CliRunner().invoke(convert, [str(src)])
    assert result.exit_code == 0, result.output
    with zipfile.ZipFile(tmp_path / "novel.epub") as z:
        opf = z.read(next(n for n in z.namelist() if n.endswith("content.opf"))).decode("utf-8")
    assert "cover.png" not in opf
    assert "cover.jpg" not in opf


def test_explicit_cover_wins_over_discovery(tmp_path):
    src = _write_sample(tmp_path)
    (tmp_path / "cover.png").write_bytes(b"\x89PNG")
    mine = tmp_path / "mine.jpg"
    mine.write_bytes(b"\xff\xd8")
    result = CliRunner().invoke(convert, [str(src), "--cover", str(mine)])
    assert result.exit_code == 0, result.output
    with zipfile.ZipFile(tmp_path / "novel.epub") as z:
        opf = z.read(next(n for n in z.namelist() if n.endswith("content.opf"))).decode("utf-8")
    assert "mine.jpg" in opf
    assert "cover.png" not in opf


def _cover_page(tmp_path, name="novel.epub"):
    with zipfile.ZipFile(tmp_path / name) as z:
        if "EPUB/cover.xhtml" not in z.namelist():
            return ""
        return z.read("EPUB/cover.xhtml").decode("utf-8")


def test_text_cover_page_generated_by_default(tmp_path):
    """没有封面图时默认生成文字封面页，内容是书名和作者。"""
    src = _write_sample(tmp_path)
    result = CliRunner().invoke(convert, [str(src), "--title", "书名", "--author", "作者"])
    assert result.exit_code == 0, result.output
    page = _cover_page(tmp_path)
    assert 'epub:type="cover"' in page
    assert "<h1>书名</h1>" in page
    assert "<p>作者</p>" in page


def test_no_text_cover_skips_page(tmp_path):
    src = _write_sample(tmp_path)
    result = CliRunner().invoke(convert, [str(src), "--title", "书名", "--no-text-cover"])
    assert result.exit_code == 0, result.output
    assert _cover_page(tmp_path) == ""
    with zipfile.ZipFile(tmp_path / "novel.epub") as z:
        assert "EPUB/cover.xhtml" not in z.namelist()


def test_text_cover_not_used_when_cover_found(tmp_path):
    """同目录有 cover.* 时用图，不再生成文字页。"""
    src = _write_sample(tmp_path)
    (tmp_path / "cover.png").write_bytes(b"\x89PNG")
    result = CliRunner().invoke(convert, [str(src), "--title", "书名"])
    assert result.exit_code == 0, result.output
    page = _cover_page(tmp_path)
    assert "<img" in page
    assert "<h1>" not in page


def test_text_cover_uses_guessed_metadata(tmp_path):
    """没给 --title/--author 时用从文件名猜出来的值填封面页。"""
    src = _write_sample(tmp_path, name="《希灵帝国》作者：远瞳.txt")
    result = CliRunner().invoke(convert, [str(src)])
    assert result.exit_code == 0, result.output
    page = _cover_page(tmp_path, name="《希灵帝国》作者：远瞳.epub")
    assert "希灵帝国" in page
    assert "远瞳" in page


def test_no_text_cover_in_help():
    result = CliRunner().invoke(convert, ["--help"])
    assert result.exit_code == 0
    assert "--no-text-cover" in result.output


def test_convert_date(tmp_path):
    src = _write_sample(tmp_path)
    result = CliRunner().invoke(convert, [str(src), "--date", "2024-05-13"])
    assert result.exit_code == 0, result.output
    out = tmp_path / "novel.epub"
    with zipfile.ZipFile(out) as z:
        opf = next(n for n in z.namelist() if n.endswith("content.opf"))
        text = z.read(opf).decode("utf-8")
    assert "<dc:date>2024-05-13</dc:date>" in text


def test_convert_date_invalid(tmp_path):
    """日期由 core 的 Config.validate() 校验，CLI 与 GUI 用同一条消息。"""
    src = _write_sample(tmp_path)
    result = CliRunner().invoke(convert, [str(src), "--date", "not-a-date"])
    assert result.exit_code == 2, result.output
    assert "日期格式错误：not-a-date" in result.output
    assert not isinstance(result.exception, ValueError)


def test_convert_unsupported_font(tmp_path):
    src = _write_sample(tmp_path)
    bad = tmp_path / "font.ttc"
    bad.write_bytes(b"\x00\x00\x00\x00tc")
    result = CliRunner().invoke(convert, [str(src), "--font", str(bad)])
    assert result.exit_code != 0
    assert "font.ttc" in result.output


def test_unsupported_cover_reports_clean_error(tmp_path):
    src = _write_sample(tmp_path)
    bad = tmp_path / "cover.txt"
    bad.write_text("not an image", encoding="utf-8")
    result = CliRunner().invoke(convert, [str(src), "--cover", str(bad)])
    assert result.exit_code != 0
    assert "不支持的封面图格式" in result.output


def test_asset_check_is_mode_independent(tmp_path):
    """字体/封面格式由 Config.validate() 统一管，`--toc-only` 也要拒。"""
    src = _write_sample(tmp_path)
    bad = tmp_path / "font.ttc"
    bad.write_bytes(b"\x00\x00\x00\x00tc")
    for extra in ([], ["--dump-css", str(_write_sample(tmp_path, name="x.css"))]):
        result = CliRunner().invoke(convert, [str(src), "--toc-only", *extra, "--font", str(bad)])
        assert result.exit_code != 0
        assert "font.ttc" in result.output


def test_toc_text(tmp_path):
    src = _write_sample(tmp_path)
    result = CliRunner().invoke(convert, [str(src), "--toc-only"])
    assert result.exit_code == 0
    assert "第一卷 起源" in result.output
    assert "第一章 开端" in result.output


def test_toc_json(tmp_path):
    src = _write_sample(tmp_path)
    result = CliRunner().invoke(convert, [str(src), "--toc-only", "--toc-format", "json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data[0]["title"] == "第一卷 起源"
    assert data[0]["children"][0]["title"] == "第一章 开端"


def test_toc_replace_applies_to_text(tmp_path):
    src = _write_sample(tmp_path)
    result = CliRunner().invoke(
        convert,
        [
            str(src),
            "--toc-only",
            "--replace-json",
            json.dumps([{"pattern": r"第一章", "replace": "第1章"}]),
        ],
    )
    assert result.exit_code == 0
    assert "第1章 开端" in result.output
    assert "第一章 开端" not in result.output


def test_toc_json_has_raw_title(tmp_path):
    src = _write_sample(tmp_path)
    result = CliRunner().invoke(
        convert,
        [str(src), "--toc-only", "--replace-json", json.dumps([{"pattern": r"卷", "replace": "部"}]), "--toc-format", "json"],
    )
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data[0]["title"] == "第一部 起源"
    assert data[0]["raw_title"] == "第一卷 起源"


def test_toc_input_option(tmp_path):
    src = _write_sample(tmp_path)
    result = CliRunner().invoke(convert, ["-i", str(src), "--toc-only"])
    assert result.exit_code == 0
    assert "第一卷 起源" in result.output


def test_toc_output_file(tmp_path):
    src = _write_sample(tmp_path)
    out = tmp_path / "toc.txt"
    result = CliRunner().invoke(convert, [str(src), "--toc-only", "-o", str(out)])
    assert result.exit_code == 0
    assert "第一章 开端" in out.read_text(encoding="utf-8")


def test_toc_output_overwrites_by_default(tmp_path):
    src = _write_sample(tmp_path)
    out = tmp_path / "toc.txt"
    out.write_text("旧内容", encoding="utf-8")
    result = CliRunner().invoke(convert, [str(src), "--toc-only", "-o", str(out)])
    assert result.exit_code == 0, result.output
    assert "旧内容" not in out.read_text(encoding="utf-8")


def test_toc_output_no_overwrite_refuses(tmp_path):
    src = _write_sample(tmp_path)
    out = tmp_path / "toc.txt"
    out.write_text("旧内容", encoding="utf-8")
    result = CliRunner().invoke(
        convert, [str(src), "--toc-only", "-o", str(out), "--no-overwrite"]
    )
    assert result.exit_code != 0
    assert "已存在" in result.output
    assert out.read_text(encoding="utf-8") == "旧内容"


def test_toc_output_no_overwrite_allows_new_file(tmp_path):
    src = _write_sample(tmp_path)
    out = tmp_path / "toc.txt"
    result = CliRunner().invoke(
        convert, [str(src), "--toc-only", "-o", str(out), "--no-overwrite"]
    )
    assert result.exit_code == 0, result.output
    assert "第一章 开端" in out.read_text(encoding="utf-8")


def test_toc_missing_input():
    result = CliRunner().invoke(convert, ["--toc-only"])
    assert result.exit_code != 0


def test_main_toc_only(tmp_path, capsys):
    src = _write_sample(tmp_path)
    main([str(src), "--toc-only"])
    out = capsys.readouterr().out
    assert "第一章 开端" in out


def test_toc_json_depth_pruning(tmp_path):
    p = tmp_path / "novel.txt"
    p.write_text("第一卷\n第一章\n§1\n正文\n", encoding="utf-8")
    deep = CliRunner().invoke(
        convert,
        [str(p), "--toc-only", "--toc-format", "json", "--level", "4:^§", "--toc-depth", "6"],
    )
    assert deep.exit_code == 0, deep.output
    assert "§1" in deep.output
    shallow = CliRunner().invoke(
        convert,
        [str(p), "--toc-only", "--toc-format", "json", "--level", "4:^§", "--toc-depth", "3"],
    )
    assert shallow.exit_code == 0, shallow.output
    assert "第一章" in shallow.output
    assert "§1" not in shallow.output


def test_main_error_clean(tmp_path, capsys):
    import pytest

    missing = tmp_path / "nope.txt"
    with pytest.raises(SystemExit):
        main([str(missing)])
    assert "Error:" in capsys.readouterr().err


def test_convert_out_stdout_epub_rejected(tmp_path):
    src = _write_sample(tmp_path)
    result = CliRunner().invoke(convert, [str(src), "-o", "-"])
    assert result.exit_code != 0
    assert "标准输出" in result.output


def test_convert_metadata_from_filename(tmp_path):
    src = _write_sample(tmp_path, name="《希灵帝国》（校对版全本）作者：远瞳.txt")
    result = CliRunner().invoke(convert, [str(src)])
    assert result.exit_code == 0, result.output
    out = tmp_path / "《希灵帝国》（校对版全本）作者：远瞳.epub"
    assert out.exists()
    with zipfile.ZipFile(out) as z:
        opf = next(n for n in z.namelist() if n.endswith("content.opf"))
        data = z.read(opf).decode("utf-8")
    assert "希灵帝国" in data
    assert "远瞳" in data


def test_convert_explicit_metadata_overrides_filename(tmp_path):
    src = _write_sample(tmp_path, name="《A》作者：B.txt")
    result = CliRunner().invoke(convert, [str(src), "--title", "手动标题", "--author", "手动作者"])
    assert result.exit_code == 0, result.output
    out = tmp_path / "《A》作者：B.epub"
    with zipfile.ZipFile(out) as z:
        opf = next(n for n in z.namelist() if n.endswith("content.opf"))
        data = z.read(opf).decode("utf-8")
    assert "手动标题" in data
    assert "手动作者" in data
    assert ">A<" not in data


def test_main_convert(tmp_path):
    src = _write_sample(tmp_path)
    main([str(src)])
    assert (tmp_path / "novel.epub").exists()


def test_convert_dump_css(tmp_path):
    src = _write_sample(tmp_path)
    css_out = tmp_path / "style.css"
    result = CliRunner().invoke(convert, [str(src), "--dump-css", str(css_out)])
    assert result.exit_code == 0
    assert "line-height" in css_out.read_text(encoding="utf-8")


def test_convert_missing_input():
    result = CliRunner().invoke(convert, [])
    assert result.exit_code != 0


@pytest.mark.parametrize(
    "args",
    [
        ["--chapter", "("],
        ["--volume", "["],
        ["--section", "(?"],
        ["--level", "2:("],
    ],
)
def test_invalid_level_regex_reports_clean_error(tmp_path, args):
    src = _write_sample(tmp_path)
    result = CliRunner().invoke(convert, [str(src), *args])
    assert result.exit_code == 2, result.output
    assert "正则非法" in result.output
    assert not isinstance(result.exception, re.error)


def test_wrong_manual_encoding_reports_clean_error(tmp_path):
    src = tmp_path / "gb.txt"
    src.write_bytes("第一章 甲\n正文".encode("gb18030"))
    result = CliRunner().invoke(convert, [str(src), "-e", "utf-8"])
    assert result.exit_code == 2, result.output
    assert "无法用编码 utf-8 解码" in result.output
    assert not isinstance(result.exception, EncodingError)


def test_unknown_encoding_name_reports_clean_error(tmp_path):
    src = _write_sample(tmp_path)
    result = CliRunner().invoke(convert, [str(src), "-e", "no-such-encoding"])
    assert result.exit_code == 2, result.output
    assert "无法用编码 no-such-encoding 解码" in result.output


@pytest.mark.parametrize("source", ["--replace-json", "--replace-file"])
def test_invalid_replace_regex_reports_clean_error(tmp_path, source):
    src = _write_sample(tmp_path)
    bad = '[{"pattern": "("}]'
    args = [str(src), source, bad]
    if source == "--replace-file":
        rules = tmp_path / "rules.json"
        rules.write_text(bad, encoding="utf-8")
        args[-1] = str(rules)
    result = CliRunner().invoke(convert, args)
    assert result.exit_code == 2, result.output
    assert "替换规则正则非法" in result.output
    assert not isinstance(result.exception, re.error)


def test_all_levels_disabled_reports_clean_error(tmp_path):
    src = _write_sample(tmp_path)
    result = CliRunner().invoke(
        convert, [str(src), "--volume", "", "--chapter", "", "--section", ""]
    )
    assert result.exit_code == 2, result.output
    assert "没有启用的标题规则" in result.output
    assert not isinstance(result.exception, NoEnabledRulesError)


#: 这些选项在 `--help` 里要印出默认值，其余（路径、开关、正则）不印
_SCALAR_OPTIONS = (
    "encoding",
    "max_title_len",
    "preface_title",
    "language",
    "indent",
    "line_height",
    "para_spacing",
    "chapter_align",
    "volume_align",
    "toc_depth",
    "toc_format",
)


def test_option_defaults_come_from_config():
    """选项默认值必须等于 Config 的默认值，不能在 CLI 里另写一份字面量。"""
    params = {p.name: p for p in convert.params}
    for name in _SCALAR_OPTIONS:
        default = option_default(next(o for o in OPTIONS if o.name == name))
        assert params[name].default == default, f"--{name} 的默认值与选项表不一致"
        assert default == getattr(Config(), name, default)
        assert params[name].show_default, f"--{name} 未在 --help 里显示默认值"


def test_help_shows_config_defaults():
    """--help 里印出来的默认值就是 Config 的默认值（click 折行不影响 [default: X] 这个整体）。"""
    result = CliRunner().invoke(convert, ["--help"])
    assert result.exit_code == 0, result.output
    for name in _SCALAR_OPTIONS:
        default = option_default(next(o for o in OPTIONS if o.name == name))
        token = f"[default: {default}]"
        assert token in result.output, f"--{name} 未显示默认值 {token}"


def test_cli_flags_come_from_the_option_table():
    """命令行表面完全由选项表生成：加一个选项只改 core，两边同时生效。"""
    declared = {opt for param in convert.params for opt in param.opts}
    for opt in OPTIONS:
        for flag in opt.flags:
            assert flag in declared, f"选项表里的 {flag} 没有出现在命令上"


def test_help_lists_every_option():
    result = CliRunner().invoke(convert, ["--help"])
    assert result.exit_code == 0, result.output
    for opt in OPTIONS:
        assert f"--{opt.name.replace('_', '-')}" in result.output, opt.name


def test_help_is_grouped_like_the_option_table():
    """`--help` 按选项表的分组小节打印，不是 click 默认的一长串。"""
    result = CliRunner().invoke(convert, ["--help"])
    assert result.exit_code == 0, result.output
    for title, _options in option_groups():
        assert f"\n{title}:" in result.output, title


def test_help_documents_each_option():
    """每个选项的说明都进了 --help。

    比对 click 自己的 help record 而不是渲染后的文本：`--help` 会按终端宽度折行，
    直接在输出里找原句会被折断的中文坑到。
    """
    ctx = click.Context(convert)
    records = {param.name: param.get_help_record(ctx) for param in convert.params}
    for opt in OPTIONS:
        _flags, help_text = records[opt.name]
        assert opt.help in help_text, opt.name



@pytest.mark.parametrize(
    ("flag", "value", "message"),
    [
        ("--toc-depth", "0", "目录深度"),
        ("--toc-depth", "7", "目录深度"),
        ("--max-title-len", "0", "标题最大字数"),
        ("--indent", "-1", "段落缩进"),
    ],
)
def test_out_of_range_values_report_clean_error(tmp_path, flag, value, message):
    """取值范围由 core 把关，CLI 只负责转成 UsageError，不吐 traceback。"""
    src = _write_sample(tmp_path)
    result = CliRunner().invoke(convert, [str(src), flag, value])
    assert result.exit_code == 2, result.output
    assert message in result.output
    assert not isinstance(result.exception, ValueError)
