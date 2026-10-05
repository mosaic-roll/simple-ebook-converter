"""`launcher` 分派逻辑测试。

这个模块只用于 PyInstaller 打包，之前多次出问题都出在分派和 ctypes 调用上，
所以这里对「参数怎么被转发」和「控制台隐藏失败不影响 GUI」做直接断言。
"""

from __future__ import annotations

import contextlib
import sys
from pathlib import Path

import pytest

from simple_ebook_converter import launcher


@pytest.fixture
def dispatched(monkeypatch):
    """记录 launcher 把参数转发给了哪个前端。"""
    calls: list[tuple[str, list[str]]] = []

    def fake_cli(argv=None):
        calls.append(("cli", list(argv or [])))

    class FakeGui:
        @staticmethod
        def main(args=None, prog_name=None, standalone_mode=None):
            calls.append(("gui", list(args or [])))

    monkeypatch.setattr(launcher, "cli_main", fake_cli)
    monkeypatch.setattr(launcher, "gui_main", FakeGui)
    monkeypatch.setattr(launcher, "_set_console_visible", lambda visible: None)
    return calls


def run_main(
    monkeypatch, argv: list[str], exe: str = "simple-ebook-converter.exe"
) -> None:
    monkeypatch.setattr(sys, "argv", [exe, *argv])
    monkeypatch.setattr(launcher.sys, "executable", exe)
    # GUI 路径走 click 的 standalone_mode，正常结束时以 SystemExit 结束
    with contextlib.suppress(SystemExit):
        launcher.main()


def test_no_args_goes_to_gui(monkeypatch, dispatched):
    run_main(monkeypatch, [])
    assert dispatched == [("gui", [])]


def test_cli_flag_goes_to_cli(monkeypatch, dispatched):
    run_main(monkeypatch, ["--cli"])
    assert dispatched == [("cli", [])]


def test_cli_flag_is_stripped_before_forwarding(monkeypatch, dispatched):
    """`--cli` 是 launcher 自己的开关，不能泄漏给命令行前端。"""
    run_main(monkeypatch, ["--cli", "book.txt", "-e", "gb18030"])
    assert dispatched == [("cli", ["book.txt", "-e", "gb18030"])]


def test_cli_exe_name_enables_cli_without_flag(monkeypatch, dispatched):
    """专用命令行包双击就该进命令行模式，不必手敲 --cli。"""
    run_main(monkeypatch, ["book.txt"], exe="simple-ebook-converter-cli.exe")
    assert dispatched == [("cli", ["book.txt"])]


def test_gui_exe_name_with_explicit_cli_flag(monkeypatch, dispatched):
    run_main(monkeypatch, ["--cli", "book.txt"], exe="simple-ebook-converter.exe")
    assert dispatched == [("cli", ["book.txt"])]


def test_cli_help_is_forwarded_to_cli_frontend(monkeypatch, dispatched):
    run_main(monkeypatch, ["--cli", "--help"])
    assert dispatched == [("cli", ["--help"])]


def test_help_without_cli_stays_in_launcher(monkeypatch, capsys):
    """不带 --cli 的 --help 归 launcher 自己处理，不能转给前端。"""
    monkeypatch.setattr(
        launcher, "cli_main", lambda argv=None: pytest.fail("不应进 CLI")
    )
    monkeypatch.setattr(sys, "argv", ["simple-ebook-converter.exe", "--help"])
    monkeypatch.setattr(launcher.sys, "executable", "simple-ebook-converter.exe")
    with pytest.raises(SystemExit):
        launcher.main()
    assert "--cli" in capsys.readouterr().out


def test_is_cli_build_by_name(monkeypatch):
    for name, expected in [
        ("simple-ebook-converter-cli.exe", True),
        ("simple_ebook_converter_cli.exe", True),
        ("simple-ebook-converter.exe", False),
        ("simple-ebook-converter-gui.exe", False),
    ]:
        monkeypatch.setattr(launcher.sys, "executable", name)
        assert launcher._is_cli_build() is expected, name


def test_console_hiding_failure_does_not_break_startup(monkeypatch):
    """ctypes 拿不到句柄时必须静默继续，不能把 GUI 一起带崩。"""
    import ctypes

    class Boom:
        def __getattr__(self, name):
            raise AttributeError(name)

    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(ctypes, "windll", Boom())
    launcher._set_console_visible(False)  # 不应抛异常
    launcher._set_console_visible(True)


def test_gui_startup_failure_restores_console(monkeypatch):
    """GUI 起不来时要把控制台放出来，否则报错被隐藏、无从排查。"""
    shown: list[bool] = []
    monkeypatch.setattr(launcher, "_set_console_visible", shown.append)

    class FailingGui:
        @staticmethod
        def main(args=None, prog_name=None, standalone_mode=None):
            raise RuntimeError("boom")

    monkeypatch.setattr(launcher, "gui_main", FailingGui)
    monkeypatch.setattr(sys, "argv", ["simple-ebook-converter.exe"])
    monkeypatch.setattr(launcher.sys, "executable", "simple-ebook-converter.exe")

    with pytest.raises(RuntimeError, match="boom"):
        launcher.main()
    assert shown == [False, True]


def test_exe_stem_uses_executable_name(monkeypatch):
    monkeypatch.setattr(
        launcher.sys, "executable", r"C:\dist\simple-ebook-converter.exe"
    )
    assert launcher._exe_stem() == Path("simple-ebook-converter.exe").stem
