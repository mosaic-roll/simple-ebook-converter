import json
import zipfile

from click.testing import CliRunner

from sec.cli import convert, main, toc


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


def test_convert_no_overwrite(tmp_path):
    src = _write_sample(tmp_path)
    out = tmp_path / "novel.epub"
    out.write_bytes(b"existing")
    result = CliRunner().invoke(convert, [str(src)])
    assert result.exit_code != 0
    assert "已存在" in result.output


def test_convert_overwrite(tmp_path):
    src = _write_sample(tmp_path)
    out = tmp_path / "novel.epub"
    out.write_bytes(b"existing")
    result = CliRunner().invoke(convert, [str(src), "--overwrite"])
    assert result.exit_code == 0, result.output


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


def test_toc_text(tmp_path):
    src = _write_sample(tmp_path)
    result = CliRunner().invoke(toc, [str(src)])
    assert result.exit_code == 0
    assert "第一卷 起源" in result.output
    assert "第一章 开端" in result.output


def test_toc_json(tmp_path):
    src = _write_sample(tmp_path)
    result = CliRunner().invoke(toc, [str(src), "--toc-format", "json", "--toc-file", "-"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data[0]["title"] == "第一卷 起源"
    assert data[0]["children"][0]["title"] == "第一章 开端"


def test_main_dispatches_toc(tmp_path, capsys):
    src = _write_sample(tmp_path)
    main(["toc", str(src)])
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