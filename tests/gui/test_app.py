import re
import zipfile
from pathlib import Path

import pytest

from simple_ebook_converter.core.config import DEFAULT_VOLUME_RE, config_defaults
from simple_ebook_converter.core.encoding import ENCODING_CHOICES, FALLBACK_ENCODINGS, decode
from simple_ebook_converter.core.replace import SCOPE_ALL, SCOPE_BODY, SCOPE_LABELS, SCOPE_TITLE
from simple_ebook_converter.gui.app import (
    _SCOPE_LABELS_TUPLE,
    build_book,
    make_config,
    preview_data,
    split_extra,
)

SAMPLE = """前言。

第一卷 开门见山
第一章 出门
正文第一段。
第二章 遇见
正文第二段。

第二卷 渐入佳境
第三章 出发
正文第三段。
"""


def _opf(epub_path: Path) -> str:
    with zipfile.ZipFile(epub_path) as z:
        name = next(n for n in z.namelist() if n.endswith("content.opf"))
        return z.read(name).decode("utf-8")


def _fields(tmp_path: Path, **overrides) -> dict:
    txt = tmp_path / "书《测试集》次第.txt"
    txt.write_text(SAMPLE, encoding="utf-8")
    fields = {
        "input": str(txt),
        "output": "",
        "encoding": "utf-8",
        "no_overwrite": False,
        "title": "",
        "author": "",
        "date": "",
        "language": "zh",
        "cover": "",
        "text_cover": True,
        "volume": "",
        "chapter": "",
        "section": "",
        "no_volume": False,
        "extra_levels": "",
        "max_title_len": 35,
        "preface_title": "前言",
        "replacements": [],
        "no_clean": False,
        "no_toc": False,
        "toc_depth": 6,
        "indent": 2,
        "line_height": "1.5",
        "para_spacing": "1em",
        "chapter_align": "center",
        "volume_align": "right",
    }
    fields.update(overrides)
    return fields


def test_split_extra():
    assert split_extra("1:^第一卷:volume\n   \n2:^第[0-9]+章") == (
        "1:^第一卷:volume",
        "2:^第[0-9]+章",
    )
    assert split_extra("") == ()


def test_config_defaults_reads_config():
    d = config_defaults()
    assert d["preface_title"] == "前言"
    assert d["max_title_len"] == 35
    assert d["toc_depth"] == 6
    assert d["chapter_align"] == "center"
    assert d["volume_align"] == "right"
    assert d["volume"] == DEFAULT_VOLUME_RE
    assert d["section"] == ""
    assert d["no_toc"] is False


def test_config_defaults_is_the_core_one():
    """GUI 用的默认值就是 core 的那一份，不再各维护一套。"""
    from simple_ebook_converter.gui import app

    assert app.config_defaults is config_defaults


#: 界面上留空时应回落到 Config 默认值的字段
_FALLBACK_FIELDS = (
    "encoding",
    "language",
    "preface_title",
    "line_height",
    "para_spacing",
    "chapter_align",
    "volume_align",
)


def test_make_config_empty_fields_fall_back_to_config(tmp_path):
    """字段留空/缺失时回落到 Config 的默认值，不靠 app.py 里另写的字面量。"""
    fields = _fields(tmp_path)
    for name in _FALLBACK_FIELDS:
        fields[name] = ""
    for name in ("toc_depth", "indent"):
        del fields[name]
    cfg = make_config(fields)
    defaults = config_defaults()
    for name in _FALLBACK_FIELDS:
        assert getattr(cfg, name) == defaults[name], f"{name} 没有回落到 Config 默认值"
    assert cfg.toc_depth == defaults["toc_depth"]
    assert cfg.indent == defaults["indent"]


def test_make_config_defaults(tmp_path):
    cfg = make_config(_fields(tmp_path))
    assert cfg.no_volume is False
    assert cfg.overwrite is True
    assert cfg.title is None
    assert len(cfg.levels) >= 2


def test_make_config_rejects_bad_input(tmp_path):
    fields = _fields(tmp_path)
    fields["input"] = str(tmp_path / "不存在.txt")
    with pytest.raises(ValueError, match="输入文件不存在"):
        make_config(fields)


def test_bad_date_is_rejected(tmp_path):
    """日期格式由 core 的 Config.validate() 兜底（make_config 不再自己解析日期）。"""
    fields = _fields(tmp_path, date="2024/13/05")
    with pytest.raises(ValueError, match="日期格式错误"):
        build_book(fields)


def test_make_config_rejects_missing_cover(tmp_path):
    with pytest.raises(ValueError, match="封面文件不存在"):
        make_config(_fields(tmp_path, cover=str(tmp_path / "没有.png")))


def test_text_cover_default_on(tmp_path):
    assert config_defaults()["text_cover"] is True
    assert make_config(_fields(tmp_path)).text_cover is True


def test_text_cover_checkbox_turns_it_off(tmp_path):
    cfg = make_config(_fields(tmp_path, text_cover=False))
    assert cfg.text_cover is False


def test_text_cover_missing_field_defaults_on(tmp_path):
    """老调用方没传这个字段时按默认开启处理，不当成关掉。"""
    fields = _fields(tmp_path)
    del fields["text_cover"]
    assert make_config(fields).text_cover is True


def test_preview_data_tree_and_replacement(tmp_path):
    fields = _fields(
        tmp_path,
        title="测试集",
        replacements=[("第一章", "CHAPTER 1", "标题")],
    )
    tree = preview_data(fields)
    assert [n["title"] for n in tree] == ["前言", "第一卷 开门见山", "第二卷 渐入佳境"]
    volume = next(n for n in tree if n["class_name"] == "volume")
    children = volume["children"]
    assert children[0]["title"] == "CHAPTER 1 出门"
    assert children[0]["raw_title"] == "第一章 出门"
    assert children[0]["class_name"] == "chapter"


def test_build_book_guesses_metadata_from_filename(tmp_path):
    """直接填路径（不经「浏览」按钮）也要用上 core 的元数据猜测。"""
    txt = tmp_path / "《测试集》作者：张三.txt"
    txt.write_text(SAMPLE, encoding="utf-8")
    fields = _fields(tmp_path, output=str(tmp_path / "guessed"))
    fields["input"] = str(txt)
    out = build_book(fields)
    opf = _opf(out)
    assert "<dc:title>测试集</dc:title>" in opf
    assert "张三" in opf


def test_build_book_never_writes_none_metadata(tmp_path):
    """文件名不含《》与「作者：」时，不能把 None 写进 EPUB 元数据。"""
    txt = tmp_path / "novel.txt"
    txt.write_text(SAMPLE, encoding="utf-8")
    fields = _fields(tmp_path, output=str(tmp_path / "plain"))
    fields["input"] = str(txt)
    opf = _opf(build_book(fields))
    titles = re.findall(r"<dc:title[^>]*>([^<]*)<", opf)
    assert titles == ["novel"]
    # 猜不到作者就不写 dc:creator，但绝不能是字符串 "None"
    assert re.findall(r"<dc:creator[^>]*>([^<]*)<", opf) == []
    assert "None" not in opf


def test_build_book_explicit_title_overrides_filename(tmp_path):
    txt = tmp_path / "《测试集》作者：张三.txt"
    txt.write_text(SAMPLE, encoding="utf-8")
    fields = _fields(tmp_path, output=str(tmp_path / "explicit"), title="手动标题", author="手动作者")
    fields["input"] = str(txt)
    opf = _opf(build_book(fields))
    assert "<dc:title>手动标题</dc:title>" in opf
    assert "手动作者" in opf


def test_build_book_creates_epub(tmp_path):
    fields = _fields(tmp_path, output=str(tmp_path / "result"))
    out = build_book(fields)
    assert out == tmp_path / "result.epub"
    assert out.is_file()
    with zipfile.ZipFile(out) as z:
        names = z.namelist()
    assert any(name.endswith("content.opf") for name in names)


def test_build_book_complains_when_not_overwrite(tmp_path):
    existing = tmp_path / "result.epub"
    existing.write_bytes(b"x")
    fields = _fields(tmp_path, output=str(existing.with_suffix("")), no_overwrite=True)
    with pytest.raises(ValueError, match="输出文件已存在"):
        build_book(fields)

def test_encoding_choices_come_from_core():
    """编码下拉框 = core 的候选链，不要在 GUI 里另写一份。"""
    from simple_ebook_converter.gui import app

    assert tuple(app._ENCODINGS) == ENCODING_CHOICES
    assert ENCODING_CHOICES[0] == "auto"
    assert set(ENCODING_CHOICES[1:]) == set(FALLBACK_ENCODINGS)


def test_every_advertised_encoding_is_a_known_codec():
    """下拉框/候选链里的每个名字都必须是有效 codec，否则 -e 会直接 LookupError。"""
    import codecs

    for enc in ENCODING_CHOICES[1:]:
        codecs.lookup(enc)
    # 自动探测确实按这个顺序尝试
    sample = "第一章 起\n正文".encode("gb18030")
    assert decode(sample)[1] in ENCODING_CHOICES


# ---------- 替换规则的作用范围 ----------

_SCOPE = SCOPE_LABELS[SCOPE_TITLE]


def test_replacement_scope_defaults_to_title(tmp_path):
    fields = _fields(tmp_path, replacements=[("正文第一段", "改了", _SCOPE)])
    cfg = make_config(fields)
    assert [r.scope for r in cfg.replacements] == [SCOPE_TITLE]


@pytest.mark.parametrize(
    ("label", "expected"),
    [("标题", SCOPE_TITLE), ("正文", SCOPE_BODY), ("全文", SCOPE_ALL)],
)
def test_replacement_scope_labels_map_to_core_values(tmp_path, label, expected):
    cfg = make_config(_fields(tmp_path, replacements=[("a", "b", label)]))
    assert [r.scope for r in cfg.replacements] == [expected]


def test_replacement_scope_labels_come_from_core():
    """下拉框选项直接来自 core 的 SCOPE_LABELS，不另写一份。"""
    assert set(_SCOPE_LABELS_TUPLE) == set(SCOPE_LABELS.values())


def test_replacement_rejects_unknown_scope_label(tmp_path):
    with pytest.raises(ValueError, match="作用范围只能是 标题/正文/全文"):
        make_config(_fields(tmp_path, replacements=[("a", "b", "第1章")]))


def test_blank_pattern_rows_are_skipped(tmp_path):
    cfg = make_config(_fields(tmp_path, replacements=[("", "x", _SCOPE), ("a", "b", _SCOPE)]))
    assert [r.pattern for r in cfg.replacements] == ["a"]


def test_gui_scope_column_reaches_the_parser(tmp_path):
    """表格第 3 列（中文标签）要一路传到 Rule.scope。"""
    fields = _fields(tmp_path, replacements=[("出门", "出门了", SCOPE_LABELS[SCOPE_ALL])])
    cfg = make_config(fields)
    assert cfg.replacements[0].scope == SCOPE_ALL
    assert cfg.replacements[0].scope_label == "全文"
