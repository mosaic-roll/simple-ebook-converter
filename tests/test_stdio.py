"""输出编码兜底：非 UTF-8 控制台上不能崩。

回归背景：GitHub Actions 的 windows runner 默认代码页是 cp1252，打包后的
`simple-ebook-converter-cli.exe --dump-css` 输出「CSS 已写入：…」时抛
`UnicodeEncodeError: 'charmap' codec can't encode characters`。更糟的是 Click
格式化 usage 时也要写中文，于是那段报错自己都显示不出来，用户只看到截断的
usage 加退出码 1。英文版 Windows 用户本地跑同一个 exe 会遇到一模一样的问题。
"""

import io
import sys

import pytest

from simple_ebook_converter._stdio import make_output_encoding_safe
from simple_ebook_converter.cli.cli import main


class _NoReconfigure:
    """模拟测试框架替换过的流：压根没有 reconfigure 属性，调用必须静默跳过。"""

    def write(self, text):
        return len(text)


def test_cp1252_stdout_can_print_chinese(tmp_path, monkeypatch, capsys):
    """把 stdout 换成 cp1252 后，中文提示应转义输出而不是抛 UnicodeEncodeError。"""
    raw = io.TextIOWrapper(io.BytesIO(), encoding="cp1252", errors="strict", newline="")
    monkeypatch.setattr(sys, "stdout", raw)

    make_output_encoding_safe()

    # strict 下这行原本会抛 UnicodeEncodeError
    print("CSS 已写入：中文")
    print("ascii ok")
    raw.flush()

    assert "ascii ok" in raw.buffer.getvalue().decode("cp1252")


def test_encoding_is_not_changed(tmp_path, monkeypatch):
    """只改容错策略、不改编码：cp936 系统上中文仍要正常显示，不能被换成 UTF-8。"""
    raw = io.TextIOWrapper(io.BytesIO(), encoding="cp936", errors="strict", newline="")
    monkeypatch.setattr(sys, "stdout", raw)

    make_output_encoding_safe()

    assert raw.encoding == "cp936"
    print("中文正常显示")
    raw.flush()
    assert "中文正常显示" in raw.buffer.getvalue().decode("cp936")


def test_none_stream_is_skipped(monkeypatch):
    """`--noconsole` 的图形界面版里 stdout/stderr 是 None，不能因此报错。"""
    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)

    make_output_encoding_safe()  # 不抛异常即通过


def test_stream_without_reconfigure_is_skipped(monkeypatch):
    """没有 reconfigure 的流要静默跳过，不能把主流程带崩。"""
    monkeypatch.setattr(sys, "stdout", _NoReconfigure())
    monkeypatch.setattr(sys, "stderr", _NoReconfigure())

    make_output_encoding_safe()


def test_cli_main_calls_guard(monkeypatch):
    """`main()` 必须先设好容错再输出，否则 Click 的报错格式化仍会炸。"""
    called = []
    monkeypatch.setattr(
        "simple_ebook_converter.cli.cli.make_output_encoding_safe",
        lambda: called.append(True),
    )

    with pytest.raises(SystemExit):
        main(["--nonexistent-option"])

    assert called, "main() 没有调用编码兜底"
