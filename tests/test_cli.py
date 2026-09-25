import json
import zipfile

from click.testing import CliRunner

from sec.cli import convert, main


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
    src = _write_sample(tmp_path)
    result = CliRunner().invoke(convert, [str(src), "--date", "not-a-date"])
    assert result.exit_code != 0
    assert "--date" in result.output


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


def test_toc_missing_input():
    result = CliRunner().invoke(convert, ["--toc-only"])
    assert result.exit_code != 0


def test_main_toc_only(tmp_path, capsys):
    src = _write_sample(tmp_path)
    main([str(src), "--toc-only"])
    out = capsys.readouterr().out
    assert "第一章 开端" in out


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