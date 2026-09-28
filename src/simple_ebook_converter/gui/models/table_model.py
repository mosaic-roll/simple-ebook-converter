"""有序行模型：行带**稳定 id**，增删不漂移。

动态行控件（额外层级、替换规则）最容易出的错是**用序号定位行**：删掉一行后其余行
的序号都变了，早先绑好的回调就会删错行。把「有序 + 稳定 id」抽到这里，控件只负责
建帧和取值，不再自己维护 `rows` 列表和序号。

行就是 `dict`，其中 `"id"` 是保留键，由本模型分配。其余键由调用方随意使用
（额外层级往里塞 Tk 变量和 Frame 引用，规则表往里塞 pattern/replace/...）。
"""

from __future__ import annotations

from typing import Any


class TableModel:
    """有序、稳定 id 的行集合。所有增删移操作都按 id，不按索引。"""

    def __init__(self) -> None:
        self._rows: list[dict[str, Any]] = []
        self._next_id = 0

    # ---------- 增 ----------

    def new(self) -> dict[str, Any]:
        """建一个只有 `id` 的空行并追加到末尾，返回该行本身（供调用方填字段）。

        先建行、后建控件：删除按钮的回调要在建按钮时就能引用到行 id。
        """
        row: dict[str, Any] = {"id": self._next_id}
        self._next_id += 1
        self._rows.append(row)
        return row

    def add(self, data: dict[str, Any] | None = None) -> dict[str, Any]:
        """建行并填入 `data`，返回该行。"""
        row = self.new()
        if data:
            row.update(data)
        return row

    # ---------- 删 / 移 ----------

    def remove(self, row_id: int) -> bool:
        for index, row in enumerate(self._rows):
            if row["id"] == row_id:
                self._rows.pop(index)
                return True
        return False

    def move(self, row_id: int, delta: int) -> bool:
        """把某行上移/下移 `delta` 位；越界不动，返回是否移动。"""
        index = self.index_of(row_id)
        if index is None:
            return False
        target = index + delta
        if not 0 <= target < len(self._rows):
            return False
        self._rows.insert(target, self._rows.pop(index))
        return True

    def clear(self) -> None:
        """清空行。**id 计数器不重置**，后续新行仍拿全新 id。"""
        self._rows.clear()

    # ---------- 查 ----------

    def index_of(self, row_id: int) -> int | None:
        for index, row in enumerate(self._rows):
            if row["id"] == row_id:
                return index
        return None

    def get(self, row_id: int) -> dict[str, Any] | None:
        index = self.index_of(row_id)
        return self._rows[index] if index is not None else None

    @property
    def rows(self) -> list[dict[str, Any]]:
        """底层行列表（**只读语义**：增删请走本模型的方法）。"""
        return self._rows

    def ids(self) -> list[int]:
        return [row["id"] for row in self._rows]

    def __len__(self) -> int:
        return len(self._rows)

    def __iter__(self):
        return iter(self._rows)
