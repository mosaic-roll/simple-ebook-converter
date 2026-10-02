"""测试基建入口。helper 本体在 `helpers.py`，这里只把常用件挂成 fixture。

分两个文件是因为 `--import-mode=importlib` 下 `conftest` 不可被测试模块导入，
而 helper 自己也要有测试（`test_conftest.py`）。
"""

from __future__ import annotations

from pathlib import Path

import pytest
from helpers import Epub, assert_heading, parse_css, resolve_href


@pytest.fixture
def novel(tmp_path: Path) -> Path:
    """一份最小可解析的输入：前言 + 两章。"""
    path = tmp_path / "novel.txt"
    path.write_text("前言内容\n第一章 一\n正文一\n第二章 二\n正文二\n", encoding="utf-8")
    return path


@pytest.fixture
def make_config():
    def _make(tmp_path: Path, **kwargs):
        from simple_ebook_converter.core.config import Config

        kwargs.setdefault("input", tmp_path / "novel.txt")
        return Config(**kwargs)

    return _make


@pytest.fixture
def epub_class():
    return Epub


@pytest.fixture
def build_epub_file(tmp_path: Path):
    """跑一次 `build_epub` 并解开成 `Epub`。`tree` / `sources` / `cfg` / `lines` 可覆盖。"""

    def _build(*, tree=None, sources=None, cfg=None, lines=None, out="out.epub"):
        from simple_ebook_converter.core.builder import build_epub
        from simple_ebook_converter.core.config import Config, default_levels
        from simple_ebook_converter.core.parser import parse

        if cfg is None:
            cfg = Config(input=tmp_path / "novel.txt")
        if tree is None:
            if lines is None:
                lines = ["第一章 一", "正文一", "第二章 二", "正文二"]
            tree = parse(lines, default_levels(), fallback_title="测试书")[0]
        path = tmp_path / out
        build_epub(cfg, tree, sources, path)
        return Epub(path)

    return _build


@pytest.fixture
def parse_css_fixture():
    """给不想写 `usefixtures` 的地方用；多数测试直接 `from helpers import parse_css`。"""
    return parse_css


@pytest.fixture
def assert_heading_fixture():
    return assert_heading


@pytest.fixture
def resolve_href_fixture():
    return resolve_href