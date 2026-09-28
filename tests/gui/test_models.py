"""`gui.models` 的纯逻辑测试：不 import tkinter，不需要 display。

这些是「动态行 / 脏跟踪」的规则层，放在 Tk 之外正是为了能这样直接测。
"""

from __future__ import annotations

from simple_ebook_converter.gui.models.autofill import AutofillPolicy
from simple_ebook_converter.gui.models.table_model import TableModel

_AUTOFILL_KEYS = ("out", "encoding", "title", "author", "cover")


def test_add_assigns_distinct_stable_ids() -> None:
    model = TableModel()
    a = model.add({"x": 1})
    b = model.add({"x": 2})
    assert a["id"] != b["id"]
    assert model.ids() == [a["id"], b["id"]]
    assert len(model) == 2


def test_remove_by_id_is_not_position_based() -> None:
    """删掉前面的行后，按 id 删仍是删那一行，不会串到后面的行。"""
    model = TableModel()
    a = model.add({"x": 1})
    b = model.add({"x": 2})
    c = model.add({"x": 3})

    assert model.remove(a["id"]) is True
    assert model.remove(b["id"]) is True  # 若按位置会误删 c
    assert [row["x"] for row in model] == [3]
    assert c["id"] in model.ids()


def test_remove_unknown_id_is_noop() -> None:
    model = TableModel()
    model.add()
    assert model.remove(999) is False
    assert len(model) == 1


def test_move_reorders_and_clamps_at_bounds() -> None:
    model = TableModel()
    a = model.add()
    b = model.add()
    c = model.add()

    assert model.move(c["id"], -1) is True
    assert model.ids() == [a["id"], c["id"], b["id"]]
    assert model.move(a["id"], -1) is False, "第一行不能上移"
    assert model.move(b["id"], 5) is False, "已在末尾不能下移"


def test_clear_does_not_reuse_ids() -> None:
    """清空后新行拿全新 id，避免刚销毁的控件的旧回调命中新行。"""
    model = TableModel()
    a = model.add()
    model.clear()
    assert len(model) == 0
    b = model.add()
    assert b["id"] > a["id"]


# ---------- AutofillPolicy ----------


def test_autofill_fills_empty_fields() -> None:
    policy = AutofillPolicy(_AUTOFILL_KEYS, "auto")
    updates = policy.plan(
        {"encoding": "auto", "title": "", "author": "", "out": ""},
        {"encoding": "gb18030", "title": "书", "author": "作", "out": "a.epub"},
    )
    assert updates == {"encoding": "gb18030", "title": "书", "author": "作", "out": "a.epub"}


def test_autofill_does_not_overwrite_touched_field() -> None:
    policy = AutofillPolicy(_AUTOFILL_KEYS, "auto")
    policy.mark_touched("title")
    updates = policy.plan(
        {"title": "用户书名", "out": ""}, {"title": "猜的", "out": "b.epub"}
    )
    assert updates == {"out": "b.epub"}


def test_autofill_refills_value_equal_to_last_auto() -> None:
    """仍是上次自动填的值 → 允许再覆盖（才算「用户没动过」）。"""
    policy = AutofillPolicy(_AUTOFILL_KEYS, "auto")
    assert policy.plan({"out": ""}, {"out": "a.epub"}) == {"out": "a.epub"}
    assert policy.plan({"out": "a.epub"}, {"out": "b.epub"}) == {"out": "b.epub"}


def test_autofill_none_means_nothing_to_fill() -> None:
    policy = AutofillPolicy(_AUTOFILL_KEYS, "auto")
    assert policy.plan({"cover": ""}, {"cover": None}) == {}


def test_autofill_auto_encoding_fillable_unless_explicitly_touched() -> None:
    """`auto` 是「未定」，默认可被真实编码覆盖；用户显式选回 auto 则不覆盖。"""
    fresh = AutofillPolicy(_AUTOFILL_KEYS, "auto")
    assert fresh.plan({"encoding": "auto"}, {"encoding": "gb18030"}) == {
        "encoding": "gb18030"
    }

    explicit = AutofillPolicy(_AUTOFILL_KEYS, "auto")
    explicit.mark_touched("encoding")
    assert explicit.plan({"encoding": "auto"}, {"encoding": "utf-8"}) == {}


def test_autofill_seed_protects_explicitly_saved_auto_encoding() -> None:
    """设置里存了 `auto` 说明用户显式选过它，加载后不该被自动填充改掉。"""
    policy = AutofillPolicy(_AUTOFILL_KEYS, "auto")
    policy.seed_from_values({"encoding": "auto"})
    assert policy.touched == {"encoding"}
    assert policy.plan({"encoding": "auto"}, {"encoding": "gb18030"}) == {}
