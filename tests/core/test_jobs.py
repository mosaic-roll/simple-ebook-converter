"""`core.jobs`：两个前端共用的「读文件 → 写产物」任务层。"""

import json
import zipfile

import pytest

from simple_ebook_converter.core.config import Config
from simple_ebook_converter.core.jobs import (
    STDOUT,
    epub_path,
    generate,
    guard_overwrite,
    load,
    preview,
    render_toc,
    summary,
    toc_target,
    write_text,
)

SAMPLE = "第一卷 风起\n第一章 初遇\n正文一字\n第二章 离别\n正文二字\n"


@pytest.fixture
def cfg(tmp_path):
    src = tmp_path / "《测试书》作者：某人.txt"
    src.write_text(SAMPLE, encoding="utf-8")
    return Config(input=src)


# ---------- 读入 ----------


def test_load_reads_and_parses(cfg):
    book = load(cfg)
    assert book.tree[0].title == "第一卷 风起"
    assert book.encoding == "utf-8"
    assert book.cfg is cfg


def test_load_fills_metadata_on_the_same_config(cfg):
    """书名/作者猜完就写回 cfg，GUI 的输入框要跟着变。"""
    load(cfg)
    assert (cfg.title, cfg.author) == ("测试书", "某人")


def test_load_without_input():
    with pytest.raises(ValueError, match="缺少输入文件"):
        load(Config())


def test_load_reports_unreadable_file(tmp_path):
    cfg = Config(input=tmp_path / "nope.txt")
    with pytest.raises(ValueError, match="无法读取输入文件"):
        load(cfg)


def test_load_reports_wrong_encoding(tmp_path):
    """指定了编码却解不开：这是用户能自己改的问题，要说清楚。"""
    src = tmp_path / "big.txt"
    src.write_bytes("第一章".encode("gb18030"))
    with pytest.raises(ValueError, match="无法用编码"):
        load(Config(input=src, encoding="utf-8"))


def test_load_reports_empty_file(tmp_path):
    src = tmp_path / "empty.txt"
    src.write_text("\n\n   \n", encoding="utf-8")
    with pytest.raises(ValueError, match="没有可生成的内容"):
        load(Config(input=src))


# ---------- 路径决策 ----------


def test_epub_path_defaults_to_input_name(cfg):
    assert epub_path(cfg) == cfg.input.with_suffix(".epub")


def test_epub_path_honors_output(cfg, tmp_path):
    assert epub_path(cfg, tmp_path / "out" / "b.epub") == tmp_path / "out" / "b.epub"


def test_epub_path_adds_missing_suffix(cfg, tmp_path):
    assert epub_path(cfg, tmp_path / "b") == tmp_path / "b.epub"


def test_epub_path_keeps_uppercase_suffix(cfg, tmp_path):
    assert epub_path(cfg, tmp_path / "b.EPUB") == tmp_path / "b.EPUB"


def test_epub_path_rejects_stdout(cfg):
    with pytest.raises(ValueError, match="不能输出到标准输出"):
        epub_path(cfg, STDOUT)


def test_toc_target_defaults_to_stdout():
    assert toc_target(None) is None
    assert toc_target("") is None
    assert toc_target(STDOUT) is None


def test_toc_target_honors_output(tmp_path):
    assert toc_target(tmp_path / "out.md") == tmp_path / "out.md"


# ---------- 覆盖保护 ----------


def test_guard_overwrite_lets_new_file_through(tmp_path):
    guard_overwrite(tmp_path / "a.epub", overwrite=False)


def test_guard_overwrite_blocks_existing_file(tmp_path):
    target = tmp_path / "a.epub"
    target.write_bytes(b"x")
    with pytest.raises(ValueError, match="已存在"):
        guard_overwrite(target, overwrite=False)


def test_guard_overwrite_allows_when_forced(tmp_path):
    target = tmp_path / "a.epub"
    target.write_bytes(b"x")
    guard_overwrite(target, overwrite=True)


# ---------- 写文件 ----------


def test_write_text_creates_parents(tmp_path):
    target = tmp_path / "deep" / "out.md"
    assert write_text(target, "内容") == target
    assert target.read_text(encoding="utf-8") == "内容"


def test_write_text_writes_plain_utf8(tmp_path):
    target = tmp_path / "out.md"
    write_text(target, "内容")
    assert target.read_bytes() == "内容".encode("utf-8")


def test_write_text_respects_overwrite_flag(tmp_path):
    target = tmp_path / "out.md"
    target.write_text("旧", encoding="utf-8")
    with pytest.raises(ValueError, match="已存在"):
        write_text(target, "新", overwrite=False)
    assert target.read_text(encoding="utf-8") == "旧"


# ---------- 目录 ----------


def test_render_toc_text_is_indented(cfg):
    text = render_toc(load(cfg))
    assert "第一卷 风起" in text
    assert "  第一章 初遇" in text


def test_render_toc_json_round_trips(cfg):
    data = json.loads(render_toc(load(cfg), "json"))
    assert data[0]["title"] == "第一卷 风起"
    assert data[0]["children"][0]["title"] == "第一章 初遇"


def test_render_toc_rejects_unknown_format(cfg):
    with pytest.raises(ValueError, match="目录格式"):
        render_toc(load(cfg), "xml")


def test_preview_returns_nested_dicts(cfg):
    data = preview(cfg)
    assert data[0]["children"][0]["title"] == "第一章 初遇"


# ---------- 汇总 ----------


def test_summary_reports_encoding_levels_and_preface(cfg):
    text = summary(load(cfg))
    assert "utf-8" in text
    assert "h2×1" in text and "h3×2" in text
    assert "前言" in text


# ---------- 生成 ----------


def test_generate_writes_epub(cfg, tmp_path):
    out = tmp_path / "out.epub"
    assert generate(load(cfg), out) == out
    with zipfile.ZipFile(out) as zf:
        names = zf.namelist()
        assert "mimetype" in names
        assert "EPUB/content.opf" in names
        assert any(n.startswith("EPUB/text/") for n in names)


def test_generate_defaults_to_input_name(cfg):
    out = generate(load(cfg))
    assert out == cfg.input.with_suffix(".epub")
    assert zipfile.is_zipfile(out)


def test_generate_creates_output_dir(cfg, tmp_path):
    out = tmp_path / "deep" / "a.epub"
    generate(load(cfg), out)
    assert out.is_file()


def test_generate_respects_overwrite_guard(cfg, tmp_path):
    out = tmp_path / "a.epub"
    out.write_bytes(b"x")
    cfg.overwrite = False
    with pytest.raises(ValueError, match="已存在"):
        generate(load(cfg), out)


def test_generate_can_overwrite(cfg, tmp_path):
    out = tmp_path / "a.epub"
    out.write_bytes(b"x")
    cfg.overwrite = True
    assert zipfile.is_zipfile(generate(load(cfg), out))


def test_load_reports_out_of_range_values(cfg):
    """取值范围在读入时就报，消息直接就是 Config.validate() 那句。"""
    cfg.toc_depth = 99
    with pytest.raises(ValueError, match="目录深度"):
        load(cfg)


def test_generate_reports_failure_with_context(cfg, tmp_path):
    """组装阶段出错要补上「无法生成 EPUB」这个上下文。"""
    cfg.css_file = tmp_path / "nope.css"
    with pytest.raises(ValueError, match="无法生成 EPUB"):
        generate(load(cfg), tmp_path / "a.epub")


def test_generate_leaves_no_partial_file(cfg, tmp_path):
    """失败时不该留下半个 EPUB。"""
    out = tmp_path / "a.epub"
    cfg.css_file = tmp_path / "nope.css"
    with pytest.raises(ValueError):
        generate(load(cfg), out)
    assert not out.exists()
