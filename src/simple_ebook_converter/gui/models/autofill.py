"""「自动填充能不能覆盖某个字段」的规则。

从输入文件扫出书名/作者/封面/编码后，界面会把这些值自动填进「基础」页。难点是
**不能盖掉用户自己填的东西**，而判断「用户填的」不能只看值：

* 字段非空不代表用户填的 —— 可能正是上一次自动填进去的；
* 编码的默认值是 `auto`（非空串），它其实是「还没定」，但用户也可能是**显式**
  选回 `auto` 表示「就要自动探测」。

所以规则是「空 + 仍等于上次自动值 + 显式动过的标记」三者一起判。把它抽到这里，
页签只负责读写控件，规则可以脱离 Tk 单测。
"""

from __future__ import annotations

from collections.abc import Iterable


class AutofillPolicy:
    """记录「哪些字段用户动过 / 上次自动填了什么」，据此决定能不能覆盖。"""

    def __init__(self, keys: Iterable[str], auto_default: str = "auto") -> None:
        self._keys = tuple(keys)
        #: 编码控件「未定」时的显示值（`core.encoding.AUTO_ENCODING`）
        self._auto_default = auto_default
        #: 用户手改过的字段，永不被自动填覆盖
        self.touched: set[str] = set()
        #: 字段 → 上次自动填进去的值
        self.last_auto: dict[str, str] = {}

    def seed_from_values(self, values: dict) -> None:
        """从读回来的设置初始化：**非空**的输入字段算「用户已定」，其余留给自动填充。

        `values` 的键是原始值（`encoding` 可能为空串，表示「没指定」）。
        """
        self.touched = {key for key in self._keys if values.get(key)}
        self.last_auto.clear()

    def mark_touched(self, key: str) -> None:
        self.touched.add(key)

    def fillable(self, key: str, current: str) -> bool:
        """当前值可以被自动填充覆盖吗。"""
        if not current or current == self.last_auto.get(key):
            return True
        # 编码的 `auto` 是「未定」的显示值：只有用户**显式**选过它才不许覆盖。
        return (
            key == "encoding"
            and current == self._auto_default
            and key not in self.touched
        )

    def plan(self, current: dict[str, str], desired: dict[str, str | None]) -> dict[str, str]:
        """算出这次要写入的 `{key: value}`，并更新「上次自动值」账本。

        `desired` 里值为 `None` 表示这次没有可填的（如没找到封面），跳过。
        即使不写值，也会在 `current == value` 时记下账本，供后续判断「仍等于上次自动值」。
        """
        updates: dict[str, str] = {}
        for key, value in desired.items():
            if value is None:
                continue
            current_value = current.get(key, "")
            if current_value == value:
                self.last_auto[key] = value
                continue
            if not self.fillable(key, current_value):
                continue
            updates[key] = value
            self.last_auto[key] = value
        return updates
