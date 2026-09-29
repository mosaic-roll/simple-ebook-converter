"""各 Tab 的构建。

每个模块只暴露一个 `build(parent, ctx) -> dict`：

- 不在模块里留状态（控件引用、变量都放进返回的 dict 交给 app 层）
- tabs 之间互不导入，跨 Tab 的动作一律走 `ctx.cb()`
"""

from __future__ import annotations

from . import basic, layout, replace, rules

__all__ = ["basic", "layout", "replace", "rules"]
