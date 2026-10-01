"""跨模块共享的上下文。

各 Tab / 面板都是无状态的 `build(parent, ctx) -> dict`：控件引用交回 app 层，
字体与回调从 `ctx` 拿。这样 tabs 之间互相不认识，换实现只改 app 一处。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from .fonts import FontManager


def _noop(*args: Any, **kwargs: Any) -> None:
    """没注册回调时的占位：点了没反应，但不报错。"""


@dataclass
class GuiContext:
    """传给各 UI 模块的容器。

    - `fonts`：共享字体实例与字号/字体族状态
    - `callbacks`：名字 → 无参可调用，由 app 层注册；Tab 用 `ctx.cb()` 取
    - `toc_entries`：当前目录条目列表（扁平 dict 列表），由扫描或示例数据填充
    - `rules_changed`：替换规则列表变动时的回调链（由 app 注册）

    这里**不放** `Config` 或 core 模块引用：参数收集、校验、资源加载都归 app 层的
    `_collect_config()` / `_collect_sources()`，Tab 只管控件，没人需要摸 core。
    """

    fonts: FontManager
    callbacks: dict[str, Callable[..., Any]] = field(default_factory=dict)
    #: 当前目录条目列表：扁平 `dict` 列表，每项含 `raw_title` / `level` 等键；
    #: 由扫描结果或示例数据填充，规则变动时直接在此数据上预览
    toc_entries: list[dict[str, Any]] = field(default_factory=list)
    #: 启动时从配置文件读到的用户配置（core 字段名 → 值）；表单初值的覆盖来源
    saved: dict[str, Any] = field(default_factory=dict)
    #: 替换规则变动时触发的回调列表（app 注册，replace tab 触发）
    rules_changed: list[Callable[..., Any]] = field(default_factory=list)

    def cb(self, name: str) -> Callable[..., Any]:
        """取回调；没注册就返回空实现。Tab 里统一走这里，不写 `lambda: None`。"""
        return self.callbacks.get(name, _noop)
