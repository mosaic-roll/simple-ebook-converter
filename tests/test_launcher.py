"""`launcher` 分派逻辑测试。

这个模块只用于 PyInstaller 打包，之前多次出问题都出在参数分派上，
所以这里对「参数怎么被转发」「exe 名决定默认模式」做直接断言。
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
    return calls


def run_main(
    monkeypatch,
    argv: list[str],
    exe: str = "simple-ebook-converter-versatile.exe",
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
    run_main(monkeypatch, ["--cli", "book.txt"], exe="simple-ebook-converter-gui.exe")
    assert dispatched == [("cli", ["book.txt"])]


def test_versatile_exe_name_defaults_to_gui(monkeypatch, dispatched):
    run_main(monkeypatch, [], exe="simple-ebook-converter-versatile.exe")
    assert dispatched == [("gui", [])]


def test_cli_help_is_forwarded_to_cli_frontend(monkeypatch, dispatched):
    run_main(monkeypatch, ["--cli", "--help"])
    assert dispatched == [("cli", ["--help"])]


def test_help_without_cli_stays_in_launcher(monkeypatch, capsys):
    """不带 --cli 的 --help 归 launcher 自己处理，不能转给前端。"""
    monkeypatch.setattr(
        launcher, "cli_main", lambda argv=None: pytest.fail("不应进 CLI")
    )
    monkeypatch.setattr(sys, "argv", ["simple-ebook-converter-versatile.exe", "--help"])
    monkeypatch.setattr(
        launcher.sys, "executable", "simple-ebook-converter-versatile.exe"
    )
    with pytest.raises(SystemExit):
        launcher.main()
    out = capsys.readouterr().out
    assert "--cli" in out
    assert "gui.exe" in out


def test_is_cli_build_by_name(monkeypatch):
    for name, expected in [
        ("simple-ebook-converter-cli.exe", True),
        ("simple_ebook_converter_cli.exe", True),
        ("simple-ebook-converter-versatile.exe", False),
        ("simple-ebook-converter-gui.exe", False),
    ]:
        monkeypatch.setattr(launcher.sys, "executable", name)
        assert launcher._is_cli_build() is expected, name


def test_launcher_does_not_touch_console_window(monkeypatch, dispatched):
    """控制台保持原样显示，launcher 不做任何隐藏/最小化处理。"""
    import ctypes

    def boom(*args, **kwargs):
        raise AssertionError("launcher 不应操作控制台窗口")

    monkeypatch.setattr(ctypes, "windll", boom)
    run_main(monkeypatch, [])
    assert dispatched == [("gui", [])]


def test_gui_startup_failure_propagates(monkeypatch):
    """GUI 起不来时异常要照常抛出，控制台可见时用户能直接看到报错。"""

    class FailingGui:
        @staticmethod
        def main(args=None, prog_name=None, standalone_mode=None):
            raise RuntimeError("boom")

    monkeypatch.setattr(launcher, "gui_main", FailingGui)
    monkeypatch.setattr(sys, "argv", ["simple-ebook-converter-versatile.exe"])
    monkeypatch.setattr(
        launcher.sys, "executable", "simple-ebook-converter-versatile.exe"
    )

    with pytest.raises(RuntimeError, match="boom"):
        launcher.main()


def test_exe_stem_uses_executable_name(monkeypatch):
    monkeypatch.setattr(
        launcher.sys, "executable", r"C:\dist\simple-ebook-converter-versatile.exe"
    )
    assert launcher._exe_stem() == Path("simple-ebook-converter-versatile.exe").stem
