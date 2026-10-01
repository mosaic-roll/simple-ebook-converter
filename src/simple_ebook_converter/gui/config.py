"""用户配置的读写：一个 `config/config.json`，纯数据进出，不依赖任何 UI 模块。

- 目录：默认打包时取 exe 同目录、脚本时取当前工作目录，再拼 `config/`；可用
  `--config-dir` 指定别的目录。
- 文件不存在、JSON 非法、顶层不是对象，一律当空配置（用默认值），不阻断启动。
- 只存一部分字段（见 `app._collect_saved()`），其余项每次启动仍取 core 默认值。
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

#: 配置目录名（程序目录 / 工作目录下）
DIR_NAME = "config"
#: 配置文件名
FILENAME = "config.json"
#: 自定义 CSS 文本的文件名（与 `config.json` 同目录，单独一个文件）
CSS_FILENAME = "custom.css"


def css_path(config_dir: Path) -> Path:
    """自定义 CSS 文本的落盘位置。

    **只表示落盘位置**，不参与生成：GUI 的文本框内容直接变成 `Sources.css_text` /
    `Sources.css_append_text`，生成过程不读这个文件。
    """
    return Path(config_dir) / CSS_FILENAME


def save_css(config_dir: Path, text: str) -> None:
    """把自定义 CSS 文本写到 `custom.css`；`text` 为空则删掉这个文件。

    与 `save()` 同样的「先写 `.tmp` 再 `os.replace`」：直接覆写时进程被杀会留下
    半截 CSS，下次启动回填出来就是坏样式。删除走 `unlink(missing_ok=True)`——
    本来就没有文件不是错误。
    """
    directory = Path(config_dir)
    target = directory / CSS_FILENAME
    if not text.strip():
        target.unlink(missing_ok=True)
        return
    directory.mkdir(parents=True, exist_ok=True)
    tmp = directory / f"{CSS_FILENAME}.tmp"
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, target)


def default_dir() -> Path:
    """默认配置目录：打包的 exe 同目录 / 脚本的当前工作目录，拼上 `config/`。"""
    frozen = bool(getattr(sys, "frozen", False)) or "__compiled__" in globals()
    base = Path(sys.executable).parent if frozen else Path.cwd()
    return base / DIR_NAME


def load(config_dir: Path) -> dict[str, Any]:
    """读配置文件。不存在或读不出合法对象时返回空 dict。"""
    path = Path(config_dir) / FILENAME
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        # ValueError 覆盖 JSONDecodeError 与非 UTF-8 的 UnicodeDecodeError
        return {}
    return data if isinstance(data, dict) else {}


def save(config_dir: Path, data: dict[str, Any]) -> None:
    """写配置文件。目录不存在就创建；先写同目录临时文件再 `os.replace`，避免写一半损坏。

    无并发场景，临时文件名固定；上次崩溃残留的 `.tmp` 会被这次写入直接覆盖。
    """
    directory = Path(config_dir)
    directory.mkdir(parents=True, exist_ok=True)
    tmp = directory / f"{FILENAME}.tmp"
    tmp.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    os.replace(tmp, directory / FILENAME)
