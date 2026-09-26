import json
import re
import zipfile

import pytest
from click.testing import CliRunner

from sec_cli.cli import convert, main
from sec_core.config import Config, config_defaults
from sec_core.encoding import EncodingError
from sec_core.parser import NoEnabledRulesError


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
    assert "二选一" in result.output


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
    assert "stdout" in result.output


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


#: CLI 选项名 -> Config 字段名（其余选项无对应字段或为 flag/路径）
_SCALAR_OPTIONS = {
    "encoding": "encoding",
    "max_title_len": "max_title_len",
    "preface_title": "preface_title",
    "language": "language",
    "indent": "indent",
    "line_height": "line_height",
    "para_spacing": "para_spacing",
    "chapter_align": "chapter_align",
    "volume_align": "volume_align",
    "toc_depth": "toc_depth",
}


def test_option_defaults_come_from_config():
    """选项默认值必须等于 Config 的默认值，不能在 CLI 里另写一份字面量。"""
    defaults = config_defaults()
    params = {p.name: p for p in convert.params}
    for opt, field in _SCALAR_OPTIONS.items():
        flag = "--" + opt.replace("_", "-")
        assert params[opt].default == defaults[field], f"{flag} 的默认值与 Config.{field} 不一致"
        assert defaults[field] == getattr(Config(), field)
        assert params[opt].show_default, f"{flag} 未在 --help 里显示默认值"


def test_help_shows_config_defaults():
    """--help 里印出来的默认值就是 Config 的默认值（click 折行不影响 [default: X] 这个整体）。"""
    result = CliRunner().invoke(convert, ["--help"])
    assert result.exit_code == 0, result.output
    defaults = config_defaults()
    for opt, field in _SCALAR_OPTIONS.items():
        token = f"[default: {defaults[field]}]"
        assert token in result.output, f"--{opt.replace('_', '-')} 未显示 Config.{field} 的默认值 {token}"


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
