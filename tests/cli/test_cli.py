"""CLI 层：选项绑定、产出分派、错误包装。

生成出来的 EPUB 长什么样由 core 的测试负责，这里只断三件 core 管不到的事：
命令行表面与选项表同步、`_produce()` 按开关走哪条产出、core 抛的异常有没有
变成不带 traceback 的可读报错。
"""

import json
import re

import click
import pytest
from click.testing import CliRunner

from simple_ebook_converter.cli.cli import convert, main
from simple_ebook_converter.core.encoding import EncodingError
from simple_ebook_converter.core.options import OPTIONS, option_default, option_groups
from simple_ebook_converter.core.parser import NoEnabledRulesError


def _write_sample(tmp_path, name="novel.txt", text=None):
    p = tmp_path / name
    p.write_text(
        text or "第一卷 起源\n第一章 开端\n第一段正文\n第二段正文\n", encoding="utf-8"
    )
    return p


def _write_rules(tmp_path, rules, name="rules.json"):
    """把替换规则写成一个 JSON 文件；命令行只认文件，不收内联 JSON。"""
    p = tmp_path / name
    p.write_text(json.dumps(rules, ensure_ascii=False), encoding="utf-8")
    return p


# ---------- 生成 EPUB ----------


def test_convert_epub_output(tmp_path):
    """基本生成 / 输出命名 / -o 覆盖 / 默认覆盖 / --no-overwrite 拒绝，一次跑完。"""
    src = _write_sample(tmp_path)
    runner = CliRunner()

    # 默认输出落在输入名上
    result = runner.invoke(convert, [str(src)])
    assert result.exit_code == 0, result.output
    assert (tmp_path / "novel.epub").exists()

    # 自定义 -o 路径（在同目录跑，novel.epub 已存在，只断 book.epub 产生了）
    out = tmp_path / "book.epub"
    result = runner.invoke(convert, [str(src), "-o", str(out)])
    assert result.exit_code == 0, result.output
    assert out.exists()

    # 默认覆盖已有文件
    existing = tmp_path / "novel.epub"
    existing.write_bytes(b"existing")
    result = runner.invoke(convert, [str(src)])
    assert result.exit_code == 0, result.output
    assert existing.read_bytes()[:2] == b"PK"

    # --no-overwrite 拒绝覆盖（已有文件是上一步的 novel.epub，不是 "existing"）
    result = runner.invoke(convert, [str(src), "--no-overwrite"])
    assert result.exit_code != 0
    assert "已存在" in result.output

    # 输出路径不存在时 --no-overwrite 不拦
    new_out = tmp_path / "new.epub"
    result = runner.invoke(convert, [str(src), "-o", str(new_out), "--no-overwrite"])
    assert result.exit_code == 0, result.output
    assert new_out.exists()


def test_convert_epub_output_rejects_stdout(tmp_path):
    """`-o -` 只在 `--toc-only` 下有意义；生成 EPUB 时直接拒。"""
    src = _write_sample(tmp_path)
    result = CliRunner().invoke(convert, [str(src), "-o", "-"])
    assert result.exit_code != 0
    assert "标准输出" in result.output


def test_convert_epub_summary(tmp_path):
    """编码/各级标题数这一行是终端文案，core 不再提供，由 CLI 自己拼。"""
    src = _write_sample(tmp_path)
    result = CliRunner().invoke(convert, [str(src), "-o", str(tmp_path / "out.epub")])
    assert result.exit_code == 0
    assert "已生成：" in result.output
    assert "编码：utf-8" in result.output
    assert "h3×1" in result.output


def test_main_convert_writes_epub(tmp_path):
    src = _write_sample(tmp_path)
    main([str(src)])
    assert (tmp_path / "novel.epub").exists()


def test_missing_input():
    """缺输入文件时 CLI 与 TOC 都拒绝。"""
    assert CliRunner().invoke(convert, []).exit_code != 0
    assert CliRunner().invoke(convert, ["--toc-only"]).exit_code != 0


# ---------- 只输出目录 ----------


# ---------- 输出目录（toc-only） ----------


def test_toc_output_formats(tmp_path):
    """text / json / 替换 / raw_title / -i / 输出到文件 / stdout，共享同一份输入。"""
    src = _write_sample(tmp_path)
    runner = CliRunner()

    # text 模式
    result = runner.invoke(convert, [str(src), "--toc-only"])
    assert result.exit_code == 0
    assert "第一卷 起源" in result.output
    assert "第一章 开端" in result.output
    assert not list(tmp_path.glob("*.epub"))

    # json 模式
    result = runner.invoke(convert, [str(src), "--toc-only", "--toc-format", "json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert [e["raw_title"] for e in data] == ["第一卷 起源", "第一章 开端"]
    assert data[0]["level"] == 2 and data[1]["level"] == 3

    # --replace-rules 对目录文本生效
    rules = _write_rules(tmp_path, [{"pattern": r"第一章", "replace": "第1章"}])
    result = runner.invoke(
        convert, [str(src), "--toc-only", "--replace-rules", str(rules)]
    )
    assert result.exit_code == 0
    assert "第1章 开端" in result.output
    assert "第一章 开端" not in result.output

    # JSON 只存 raw_title，替换结果不落盘
    rules2 = _write_rules(tmp_path, [{"pattern": r"卷", "replace": "部"}])
    result = runner.invoke(
        convert,
        [str(src), "--toc-only", "--replace-rules", str(rules2), "--toc-format", "json"],
    )
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data[0]["raw_title"] == "第一卷 起源"
    assert "title" not in data[0]

    # -i 位置参数等价
    result = runner.invoke(convert, ["-i", str(src), "--toc-only"])
    assert result.exit_code == 0
    assert "第一卷 起源" in result.output

    # -o 写到文件 / 覆盖 / --no-overwrite 拒 / 新文件放行
    out = tmp_path / "toc.txt"
    out.write_text("旧内容", encoding="utf-8")
    result = runner.invoke(convert, [str(src), "--toc-only", "-o", str(out)])
    assert result.exit_code == 0
    assert "旧内容" not in out.read_text(encoding="utf-8")

    out2 = tmp_path / "toc2.txt"
    out2.write_text("旧内容", encoding="utf-8")
    result = runner.invoke(convert, [str(src), "--toc-only", "-o", str(out2), "--no-overwrite"])
    assert result.exit_code != 0
    assert out2.read_text(encoding="utf-8") == "旧内容"

    new_out = tmp_path / "new.txt"
    result = runner.invoke(convert, [str(src), "--toc-only", "-o", str(new_out), "--no-overwrite"])
    assert result.exit_code == 0
    assert "第一章 开端" in new_out.read_text(encoding="utf-8")

    # -o - 写 stdout，不落文件
    result = runner.invoke(convert, [str(src), "--toc-only", "-o", "-"])
    assert result.exit_code == 0
    assert "第一章" in result.output
    assert "目录已写入" not in result.output
    assert not list(tmp_path.glob("*.epub"))


def test_toc_json_depth_pruning(tmp_path):
    """`--toc-depth` 只裁目录深度，不动分页。"""
    p = tmp_path / "novel.txt"
    p.write_text("第一卷\n第一章\n§1\n正文\n", encoding="utf-8")
    deep = CliRunner().invoke(
        convert, [str(p), "--toc-only", "--toc-format", "json", "--level", "h4:^§"]
    )
    assert deep.exit_code == 0, deep.output
    assert "§1" in deep.output
    shallow = CliRunner().invoke(
        convert,
        [str(p), "--toc-only", "--toc-format", "json", "--level", "h4:^§", "--toc-depth", "3"],
    )
    assert shallow.exit_code == 0, shallow.output
    assert "第一章" in shallow.output
    assert "§1" not in shallow.output


def test_main_toc_only(tmp_path, capsys):
    src = _write_sample(tmp_path)
    main([str(src), "--toc-only"])
    out = capsys.readouterr().out
    assert "第一章 开端" in out


# ---------- 导出 CSS ----------


def test_convert_dump_css(tmp_path):
    """正常导出 + 跳过 validate + 缺少输出路径拒绝 + 非数值拒绝 + 不受 --css-file 干扰。"""
    src = _write_sample(tmp_path)
    css_out = tmp_path / "style.css"
    extra = tmp_path / "extra.css"
    extra.write_text("body { color: red; }", encoding="utf-8")

    # 正常导出
    result = CliRunner().invoke(convert, [str(src), "--dump-css", str(css_out)])
    assert result.exit_code == 0
    assert "CSS 已写入" in result.output
    assert "line-height" in css_out.read_text(encoding="utf-8")
    assert not list(tmp_path.glob("*.epub"))

    # 值域越界也照样出模板
    for extra_arg in (["--indent", "-5"], ["--toc-depth", "99"]):
        r = CliRunner().invoke(convert, ["--dump-css", str(css_out), *extra_arg])
        assert r.exit_code == 0, r.output
        assert "body {" in css_out.read_text(encoding="utf-8")

    # 没有输出路径就失败
    result = CliRunner().invoke(convert, ["--dump-css"])
    assert result.exit_code != 0

    # 非数值在 click 解析时就报错，不等到 validate
    result = CliRunner().invoke(convert, ["--dump-css", str(css_out), "--indent", "abc"])
    assert result.exit_code != 0
    assert "not a valid integer" in result.output

    # 导的是内置模板，--css-file 不影响
    result = CliRunner().invoke(
        convert, [str(src), "--dump-css", str(css_out), "--css-file", str(extra)]
    )
    assert result.exit_code == 0, result.output
    dumped = css_out.read_text(encoding="utf-8")
    assert "line-height" in dumped
    assert "color: red" not in dumped


def test_css_file_and_css_append_conflict(tmp_path):
    """互斥是 `Config.validate()` 管的，CLI 只负责把它变成 exit 2。"""
    src = _write_sample(tmp_path)
    a, b = tmp_path / "a.css", tmp_path / "b.css"
    a.write_text("body {}", encoding="utf-8")
    b.write_text("body {}", encoding="utf-8")
    result = CliRunner().invoke(
        convert, [str(src), "--css-file", str(a), "--css-append", str(b)]
    )
    assert result.exit_code == 2, result.output
    assert "互斥" in result.output
    assert not list(tmp_path.glob("*.epub"))


def test_no_text_cover_in_help():
    result = CliRunner().invoke(convert, ["--help"])
    assert result.exit_code == 0
    assert "--no-text-cover" in result.output


# ---------- 错误包装（core 只管抛，这里管怎么呈现） ----------


def test_input_errors(tmp_path):
    """各类非法输入统一报 exit 2 / exit != 0，不吐 traceback。一次跑完省掉多个 tmp_path。"""
    src = _write_sample(tmp_path)
    runner = CliRunner()

    # 日期格式错误
    r = runner.invoke(convert, [str(src), "--date", "not-a-date"])
    assert r.exit_code == 2, r.output
    assert "日期格式错误：not-a-date" in r.output
    assert not isinstance(r.exception, ValueError)

    # 未知编码名
    r = runner.invoke(convert, [str(src), "-e", "no-such-encoding"])
    assert r.exit_code == 2, r.output
    assert "未知编码：no-such-encoding" in r.output
    assert "codec" in r.output

    # 手动编码不匹配文件实际编码
    bad_src = tmp_path / "gb.txt"
    bad_src.write_bytes("第一章 甲\n正文".encode("gb18030"))
    r = runner.invoke(convert, [str(bad_src), "-e", "utf-8"])
    assert r.exit_code == 2, r.output
    assert "无法用编码 utf-8 解码" in r.output
    assert not isinstance(r.exception, EncodingError)

    # 不支持的字体
    bad_font = tmp_path / "font.ttc"
    bad_font.write_bytes(b"\x00\x00\x00\x00tc")
    r = runner.invoke(convert, [str(src), "--font", str(bad_font)])
    assert r.exit_code != 0
    assert "font.ttc" in r.output

    # 不支持的封面
    bad_cover = tmp_path / "cover.txt"
    bad_cover.write_text("not an image", encoding="utf-8")
    r = runner.invoke(convert, [str(src), "--cover", str(bad_cover)])
    assert r.exit_code != 0
    assert "不支持的封面图格式" in r.output

    # 字体检查与输出模式无关（--toc-only 也要拒）
    r = runner.invoke(convert, [str(src), "--toc-only", "--font", str(bad_font)])
    assert r.exit_code != 0
    assert "font.ttc" in r.output

    # 非法正则：卷 / 章 / 自定义层级
    for args in (["--chapter", "("], ["--volume", "["], ["--level", "h2:("]):
        r = runner.invoke(convert, [str(src), *args])
        assert r.exit_code == 2, r.output
        assert "正则非法" in r.output
        assert not isinstance(r.exception, re.error)

    # 替换规则阶段非法
    rules_bad = _write_rules(tmp_path, [{"pattern": "a", "stage": "chapter"}])
    r = runner.invoke(convert, [str(src), "--replace-rules", str(rules_bad)])
    assert r.exit_code != 0
    assert "阶段只能是" in r.output

    # 替换规则文件不存在
    r = runner.invoke(convert, [str(src), "--replace-rules", str(tmp_path / "nope.json")])
    assert r.exit_code != 0
    assert "nope.json" in r.output

    # 替换规则正则非法
    rules_regex = tmp_path / "rules.json"
    rules_regex.write_text('[{"pattern": "("}]', encoding="utf-8")
    r = runner.invoke(convert, [str(src), "--replace-rules", str(rules_regex)])
    assert r.exit_code == 2, r.output
    assert "替换规则正则非法" in r.output
    assert not isinstance(r.exception, re.error)

    # 所有层级规则都关闭
    r = runner.invoke(convert, [str(src), "--volume", "", "--chapter", ""])
    assert r.exit_code == 2, r.output
    assert "没有启用的标题规则" in r.output
    assert not isinstance(r.exception, NoEnabledRulesError)


def test_main_error_clean(tmp_path, capsys):
    missing = tmp_path / "nope.txt"
    with pytest.raises(SystemExit):
        main([str(missing)])
    assert "Error:" in capsys.readouterr().err


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


# ---------- 命令行表面 = 选项表 ----------


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
    "para_align",
    "toc_depth",
    "toc_format",
)


def test_option_defaults_come_from_config():
    """click 命令上声明的默认值必须来自选项表，不能在 CLI 里另写一份字面量。

    `--help` 里印出来的值由 `test_help_shows_config_defaults` 断。
    """
    params = {p.name: p for p in convert.params}
    for name in _SCALAR_OPTIONS:
        default = option_default(next(o for o in OPTIONS if o.name == name))
        assert params[name].default == default, f"--{name} 的默认值与选项表不一致"
        assert params[name].show_default, f"--{name} 未在 --help 里显示默认值"


def test_help_shows_config_defaults():
    """--help 里印出来的默认值就是 Config 的默认值。

    比对 click 的 help record 而不是渲染后的文本：`[default: X]` 靠空格分词，
    终端宽度不巧时会被从中间折开（如 `[default:` / `auto]`），断言不能依赖
    文案长度碰运气。
    """
    ctx = click.Context(convert)
    records = {param.opts[-1]: param.get_help_record(ctx) for param in convert.params}
    for name in _SCALAR_OPTIONS:
        opt = next(o for o in OPTIONS if o.name == name)
        token = f"[default: {option_default(opt)}]"
        assert token in records[opt.flags[-1]][1], f"--{name} 未显示默认值 {token}"


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
        for flag in opt.flags:
            assert flag in result.output, opt.name


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
    records = {param.opts[-1]: param.get_help_record(ctx) for param in convert.params}
    for opt in OPTIONS:
        _flags, help_text = records[opt.flags[-1]]
        assert opt.help in help_text, opt.name
