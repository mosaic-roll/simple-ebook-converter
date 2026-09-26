import json
import re
import zipfile
from pathlib import Path

import pytest

from simple_ebook_converter.core.config import Config
from simple_ebook_converter.core.options import OPTIONS, option_default, option_groups
from simple_ebook_converter.core.replace import STAGE_LABELS
from simple_ebook_converter.gui.app import (
    form_default,
    generate_output,
    make_config,
    option_values,
    preview_data,
    replacement_json,
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

_STAGE = STAGE_LABELS["raw"]


def _opf(epub_path: Path) -> str:
    with zipfile.ZipFile(epub_path) as z:
        name = next(n for n in z.namelist() if n.endswith("content.opf"))
        return z.read(name).decode("utf-8")


def _fields(tmp_path: Path, **overrides) -> dict:
    """和界面一样的初值：逐个选项取控件初值，替换规则表格默认空。"""
    txt = tmp_path / "书《测试集》次第.txt"
    txt.write_text(SAMPLE, encoding="utf-8")
    fields = {opt.name: form_default(opt) for opt in OPTIONS}
    fields["input"] = str(txt)
    fields["replacements"] = []
    fields.update(overrides)
    return fields


# ---------- 界面就是 CLI 的那一份选项 ----------


def test_form_shows_every_option_of_the_table():
    """选项以 CLI 为标准：core 选项表里的每一项，界面上都要有对应控件。"""
    shown = [opt.name for _title, options in option_groups() for opt in options]
    assert sorted(shown) == sorted(opt.name for opt in OPTIONS)


def test_form_default_comes_from_config():
    """控件初值就是 Config 的默认值，界面不再另写一份字面量。"""
    defaults = Config()
    for opt in OPTIONS:
        if opt.multiple:
            assert form_default(opt) == ""  # 多行文本框，空就是空
        else:
            assert form_default(opt) == ("" if option_default(opt) is None else option_default(opt))
    assert defaults.overwrite is True  # 勾上 = 覆盖，与正面字段同名同语义


def test_multi_line_option_takes_one_item_per_line(tmp_path):
    """额外层级是多行文本框：一行一条规则，和 CLI 重复写 --level 等价。"""
    fields = _fields(tmp_path, level="h1.part:^第[0-9]+部\nh5:^尾声")
    levels = {rule.level: rule for rule in make_config(fields).levels}
    assert levels[1].class_name == "part"
    assert levels[5].pattern == "^尾声"
    assert levels[3].class_name == "chapter"  # 内置预设没被额外层级动到
    assert {rule.level for rule in make_config(_fields(tmp_path)).levels} == {2, 3, 4}


def test_checkbox_defaults_match_config():
    """勾选框与正面字段同名同语义（`覆盖已有文件` 勾上就是覆盖），所以不需要取反。"""
    for opt in OPTIONS:
        if opt.kind is bool:
            assert form_default(opt) is bool(option_default(opt)), opt.name


def test_every_option_has_a_label_and_help():
    for opt in OPTIONS:
        assert opt.label and opt.help, opt.name


# ---------- 字段 → Config ----------


def test_make_config_empty_fields_fall_back_to_config(tmp_path):
    """字段留空/缺失时回落到 Config 的默认值。"""
    fields = _fields(tmp_path)
    for name in ("encoding", "language", "preface_title", "line_height", "para_spacing"):
        fields[name] = ""
    for name in ("toc_depth", "indent", "max_title_len"):
        del fields[name]
    cfg = make_config(fields)
    defaults = Config()
    for name in ("encoding", "language", "preface_title", "line_height", "para_spacing"):
        assert getattr(cfg, name) == getattr(defaults, name), name
    assert cfg.toc_depth == defaults.toc_depth
    assert cfg.indent == defaults.indent
    assert cfg.max_title_len == defaults.max_title_len


def test_make_config_defaults(tmp_path):
    cfg = make_config(_fields(tmp_path))
    assert cfg.overwrite is True
    assert cfg.title is None
    assert len(cfg.levels) >= 2


def test_make_config_rejects_bad_input(tmp_path):
    """`build_config()` 会检查要读的路径：不存在就直接报错，不必等 core 读到才失败。"""
    with pytest.raises(ValueError, match="输入文件不存在"):
        make_config(_fields(tmp_path, input=str(tmp_path / "不存在.txt")))


def test_make_config_rejects_missing_cover(tmp_path):
    with pytest.raises(ValueError, match="封面图不存在"):
        make_config(_fields(tmp_path, cover=str(tmp_path / "没有.png")))


def test_bad_date_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="日期格式错误"):
        generate_output(_fields(tmp_path, date="2024/13/05"))


def test_text_cover_checkbox_turns_it_off(tmp_path):
    """勾选框按正面说法显示：不勾 = 不要文字封面页。"""
    assert make_config(_fields(tmp_path)).text_cover is True
    assert make_config(_fields(tmp_path, text_cover=False)).text_cover is False


# ---------- 替换规则：表格只是界面写法，内部只走 JSON ----------


def test_replacement_json_is_plain_json(tmp_path):
    text = replacement_json([("甲", "乙", _STAGE)])
    assert json.loads(text) == [{"pattern": "甲", "replace": "乙", "stage": "raw"}]


def test_table_rows_reach_config_as_json(tmp_path):
    fields = _fields(tmp_path, replacements=[("第一章", "CHAPTER 1", _STAGE)])
    values = option_values(fields)
    assert values["replace_json"] == replacement_json(fields["replacements"])
    assert [r.replace for r in make_config(fields).replacements] == ["CHAPTER 1"]


def test_empty_table_keeps_typed_json(tmp_path):
    """表格空着就用输入框里的 JSON，两者不互相清空。"""
    typed = json.dumps([{"pattern": "甲", "replace": "乙"}], ensure_ascii=False)
    fields = _fields(tmp_path, replace_json=typed, replacements=[])
    assert option_values(fields)["replace_json"] == typed
    assert [r.pattern for r in make_config(fields).replacements] == ["甲"]


def test_replacement_stage_defaults_to_raw(tmp_path):
    cfg = make_config(_fields(tmp_path, replacements=[("正文第一段", "改了", _STAGE)]))
    assert [r.stage for r in cfg.replacements] == ["raw"]


@pytest.mark.parametrize(
    ("label", "expected"),
    [("原文", "raw"), ("HTML", "html")],
)
def test_replacement_stage_labels_map_to_core_values(tmp_path, label, expected):
    cfg = make_config(_fields(tmp_path, replacements=[("a", "b", label)]))
    assert [r.stage for r in cfg.replacements] == [expected]


def test_replacement_rejects_unknown_stage_label(tmp_path):
    with pytest.raises(ValueError, match="阶段只能是 原文/HTML"):
        make_config(_fields(tmp_path, replacements=[("a", "b", "第1章")]))


def test_blank_pattern_rows_are_skipped(tmp_path):
    cfg = make_config(_fields(tmp_path, replacements=[("", "x", _STAGE), ("a", "b", _STAGE)]))
    assert [r.pattern for r in cfg.replacements] == ["a"]


def test_replace_file_option_reaches_the_parser(tmp_path):
    path = tmp_path / "rules.json"
    path.write_text(json.dumps([{"pattern": "出门", "replace": "出门了"}]), encoding="utf-8")
    cfg = make_config(_fields(tmp_path, replace_file=str(path)))
    assert [r.replace for r in cfg.replacements] == ["出门了"]


# ---------- 目录预览 ----------


def test_preview_data_tree_and_replacement(tmp_path):
    tree, shown = preview_data(
        _fields(tmp_path, title="测试集", replacements=[("第一章", "CHAPTER 1", _STAGE)])
    )
    assert [n["raw_title"] for n in tree] == [
        "前言",
        "第一卷 开门见山",
        "第一章 出门",
        "第二章 遇见",
        "第二卷 渐入佳境",
        "第三章 出发",
    ]
    chapter = next(n for n in tree if n["class_name"] == "chapter")
    assert shown(chapter["raw_title"]) == "CHAPTER 1 出门"


# ---------- 生成：三种模式和 CLI 一致 ----------


def test_generate_output_creates_epub(tmp_path):
    out = generate_output(_fields(tmp_path, out=str(tmp_path / "result")))
    assert out == tmp_path / "result.epub"
    with zipfile.ZipFile(out) as z:
        assert any(name.endswith("content.opf") for name in z.namelist())


def test_generate_output_adds_epub_suffix(tmp_path):
    out = generate_output(_fields(tmp_path, out=str(tmp_path / "book.epub")))
    assert out == tmp_path / "book.epub"
    assert out.is_file()


def test_generate_output_complains_when_not_overwrite(tmp_path):
    """取消勾选「覆盖已有文件」才是不覆盖。"""
    existing = tmp_path / "result.epub"
    existing.write_bytes(b"x")
    with pytest.raises(ValueError, match="输出文件已存在"):
        generate_output(_fields(tmp_path, out=str(existing), overwrite=False))


def test_generate_output_toc_only_writes_text(tmp_path):
    fields = _fields(tmp_path, out=str(tmp_path / "目录.md"), toc_only=True)
    out = generate_output(fields)
    assert out == tmp_path / "目录.md"
    assert "第一章 出门" in out.read_text(encoding="utf-8")
    assert not list(tmp_path.glob("*.epub"))


def test_generate_output_toc_only_falls_back_next_to_input(tmp_path):
    """GUI 没有标准输出，留空输出路径就落到输入同目录的同名文件。"""
    out = generate_output(_fields(tmp_path, toc_only=True))
    assert out.parent == tmp_path
    assert out.is_file()


def test_generate_output_toc_only_json(tmp_path):
    fields = _fields(tmp_path, out=str(tmp_path / "toc.json"), toc_only=True, toc_format="json")
    out = generate_output(fields)
    tree = json.loads(out.read_text(encoding="utf-8"))
    assert [n["raw_title"] for n in tree] == [
        "前言",
        "第一卷 开门见山",
        "第一章 出门",
        "第二章 遇见",
        "第二卷 渐入佳境",
        "第三章 出发",
    ]


def test_generate_output_dump_css_writes_only_css(tmp_path):
    css = tmp_path / "book.css"
    out = generate_output(_fields(tmp_path, dump_css=str(css)))
    assert out == css
    assert "body" in css.read_text(encoding="utf-8")
    assert not list(tmp_path.glob("*.epub"))


# ---------- 元数据 ----------


def test_generate_output_guesses_metadata_from_filename(tmp_path):
    """直接填路径（不经「浏览」按钮）也要用上 core 的元数据猜测。"""
    txt = tmp_path / "《测试集》作者：张三.txt"
    txt.write_text(SAMPLE, encoding="utf-8")
    fields = _fields(tmp_path, input=str(txt), out=str(tmp_path / "guessed"))
    opf = _opf(generate_output(fields))
    assert "<dc:title>测试集</dc:title>" in opf
    assert "张三" in opf


def test_generate_output_never_writes_none_metadata(tmp_path):
    """文件名不含《》与「作者：」时，不能把 None 写进 EPUB 元数据。"""
    txt = tmp_path / "novel.txt"
    txt.write_text(SAMPLE, encoding="utf-8")
    fields = _fields(tmp_path, input=str(txt), out=str(tmp_path / "plain"))
    opf = _opf(generate_output(fields))
    assert re.findall(r"<dc:title[^>]*>([^<]*)<", opf) == ["novel"]
    assert re.findall(r"<dc:creator[^>]*>([^<]*)<", opf) == []
    assert "None" not in opf


def test_generate_output_explicit_title_overrides_filename(tmp_path):
    txt = tmp_path / "《测试集》作者：张三.txt"
    txt.write_text(SAMPLE, encoding="utf-8")
    fields = _fields(
        tmp_path, input=str(txt), out=str(tmp_path / "explicit"), title="手动标题", author="手动作者"
    )
    opf = _opf(generate_output(fields))
    assert "<dc:title>手动标题</dc:title>" in opf
    assert "手动作者" in opf
