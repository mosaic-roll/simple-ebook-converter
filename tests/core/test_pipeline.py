"""`core.pipeline`：两个前端共用的「读文件 → 切分 → 写产物」那一层。"""

import json
import zipfile
from dataclasses import replace
from pathlib import Path

import pytest

from simple_ebook_converter.core.config import Config, LevelRule, default_levels
from simple_ebook_converter.core.parser import NoEnabledRulesError, walk
from simple_ebook_converter.core.pipeline import (
    preview_titles,
    process,
    read_book,
    resolve,
    scan_toc,
    toc_text,
    write_css,
    write_epub,
    write_text,
    write_toc,
)
from simple_ebook_converter.core.replace import Rule
from simple_ebook_converter.core.toc import to_json, tree_from_json

SAMPLE = [
    "封面文案",
    "第一卷 风起",
    "第一章 初遇",
    "正文一字",
    "第二章 离别",
    "正文二字",
]

LINES = "第一卷 风起\n第一章 初遇\n正文一字\n第二章 离别\n正文二字\n"


@pytest.fixture
def cfg(tmp_path):
    src = tmp_path / "《测试书》作者：某人.txt"
    src.write_text(LINES, encoding="utf-8")
    return Config(input=src)


def _cfg(tmp_path: Path, **kwargs) -> Config:
    return Config(input=tmp_path / "《测试书》作者：某人.txt", **kwargs)


# ---------- resolve：解析前把参数补全 ----------


def test_resolve_guesses_metadata():
    """书名/作者按文件名猜好，两个前端不必各自实现。"""
    cfg = Config(input=Path("《测试书》作者：某人.txt"))
    assert (cfg.title, cfg.author) == (None, "")
    assert (resolve(cfg).title, resolve(cfg).author) == ("测试书", "某人")


def test_resolve_keeps_explicit_metadata(tmp_path):
    cfg = _cfg(tmp_path, title="手写书名", author="手写作")
    assert (resolve(cfg).title, resolve(cfg).author) == ("手写书名", "手写作")


def test_resolve_does_not_touch_the_given_config(tmp_path):
    """core 无状态：补全结果写进新的一份，传进来的那个原样不动。"""
    cfg = _cfg(tmp_path)
    resolved = resolve(cfg)
    assert (cfg.title, cfg.author) == (None, "")
    assert resolved is not cfg
    assert resolved.input is cfg.input  # 共享的是只读输入，不是配置本身


def test_resolve_without_input_leaves_metadata_alone():
    assert (resolve(Config()).title, resolve(Config()).author) == (None, "")


def test_resolve_validates_config(tmp_path):
    """取值范围在这一步兜住，不必指望每个前端记得调 validate()。"""
    with pytest.raises(ValueError, match="目录深度"):
        resolve(_cfg(tmp_path, toc_depth=99))


# ---------- 封面自动发现 ----------


def test_resolve_discovers_cover_next_to_input(tmp_path):
    cover = tmp_path / "cover.png"
    cover.write_bytes(b"\x89PNG")
    cfg = _cfg(tmp_path)
    assert cfg.cover is None
    assert resolve(cfg).cover == cover


def test_resolve_keeps_explicit_cover(tmp_path):
    (tmp_path / "cover.png").write_bytes(b"\x89PNG")
    explicit = tmp_path / "mine.jpg"
    explicit.write_bytes(b"\xff\xd8")
    assert resolve(_cfg(tmp_path, cover=explicit)).cover == explicit


def test_resolve_leaves_cover_none_when_absent(tmp_path):
    assert resolve(_cfg(tmp_path)).cover is None


def test_discovered_cover_passes_validation(tmp_path):
    """自动发现的封面也必须过得了 Config.validate()。"""
    (tmp_path / "cover.webp").write_bytes(b"RIFF")
    resolve(_cfg(tmp_path)).validate()


# ---------- read_book：读入 ----------


def test_read_book_reads_and_parses(cfg):
    book = read_book(cfg)
    assert book.tree[0].title == "第一卷 风起"
    assert book.encoding == "utf-8"
    assert book.cfg is not cfg  # 补全过的那一份


def test_read_book_fills_metadata_on_its_own_config(cfg):
    assert (cfg.title, cfg.author) == (None, "")
    assert (read_book(cfg).cfg.title, read_book(cfg).cfg.author) == ("测试书", "某人")


def test_read_book_without_input():
    with pytest.raises(ValueError, match="缺少输入文件"):
        read_book(Config())


def test_read_book_reports_unreadable_file(tmp_path):
    with pytest.raises(ValueError, match="无法读取输入文件"):
        read_book(Config(input=tmp_path / "nope.txt"))


def test_read_book_reports_wrong_encoding(tmp_path):
    """指定了编码却解不开：这是用户能自己改的问题，要说清楚。"""
    src = tmp_path / "big.txt"
    src.write_bytes("第一章".encode("gb18030"))
    with pytest.raises(ValueError, match="无法用编码"):
        read_book(Config(input=src, encoding="utf-8"))


def test_read_book_reports_empty_file(tmp_path):
    src = tmp_path / "empty.txt"
    src.write_text("\n\n   \n", encoding="utf-8")
    with pytest.raises(ValueError, match="没有可生成的内容"):
        read_book(Config(input=src))


def test_read_book_reports_out_of_range_values(tmp_path):
    """取值范围在读入时就报，消息直接就是 Config.validate() 那句。"""
    with pytest.raises(ValueError, match="目录深度"):
        read_book(_cfg(tmp_path, toc_depth=99))


# ---------- process：切分 → 清理 → 替换 ----------


def test_process_reports_disabled_levels(tmp_path):
    with pytest.raises(NoEnabledRulesError):
        process(SAMPLE, _cfg(tmp_path, levels=[LevelRule(2, "", "volume")]))


def test_process_falls_back_to_book_title(tmp_path):
    """没有标题命中时，整篇归到一章，标题取书名。"""
    tree, stats = process(
        ["没有标题的一行", "另一行"], Config(input=tmp_path / "我的小说.txt")
    )
    assert stats.has_preface is False
    assert len(tree) == 1
    assert tree[0].title == "我的小说"
    assert tree[0].paragraphs == ["没有标题的一行", "另一行"]


def test_process_uses_resolved_title_as_fallback(tmp_path):
    """书名是猜出来的也能当兜底章节名。"""
    tree, _ = process(["没有标题"], resolve(_cfg(tmp_path)))
    assert tree[0].title == "测试书"


def test_process_cleans_by_default(tmp_path):
    tree, _ = process(["　　正文一　", "", "  ", "正文二"], _cfg(tmp_path))
    assert tree[0].paragraphs == ["正文一", "正文二"]


def test_process_keeps_blank_lines_when_not_cleaning(tmp_path):
    tree, _ = process(["正文一", "", "正文二"], _cfg(tmp_path, clean=False))
    assert tree[0].paragraphs == ["正文一", "", "正文二"]


def test_process_replaces_titles_keeping_raw(tmp_path):
    cfg = _cfg(tmp_path, replacements=[Rule(r"^第", "第X")])
    tree, _ = process(SAMPLE, cfg)
    volume = tree[1]
    assert volume.title == "第X一卷 风起"
    assert volume.raw_title == "第一卷 风起"
    assert volume.children[0].title == "第X一章 初遇"
    assert volume.children[0].raw_title == "第一章 初遇"


def test_process_returns_stats(tmp_path):
    _, stats = process(SAMPLE, _cfg(tmp_path))
    assert stats.level_counts == {2: 1, 3: 2}
    assert stats.max_level == 3
    assert stats.has_preface is True
    assert stats.total_lines == len(SAMPLE)


def test_levels_are_not_shared_between_configs(tmp_path):
    """两次调用不能互相污染 default_levels()。"""
    a = _cfg(tmp_path)
    b = _cfg(tmp_path, levels=[*default_levels()])
    process(SAMPLE, a)
    process(SAMPLE, b)
    assert [r.level for r in b.levels] == [r.level for r in default_levels()]


# ---------- 替换：只作用于标题，raw / html 两个阶段 ----------


def test_replacement_never_touches_paragraphs(tmp_path):
    """替换只作用于标题；改正文请直接改源文件。"""
    cfg = _cfg(tmp_path, replacements=[Rule("正文一", "改了")])
    tree, _ = process(SAMPLE, cfg)
    assert tree[1].children[0].paragraphs == ["正文一字"]
    assert tree[1].title == "第一卷 风起"


def test_raw_stage_replaces_the_plain_title(tmp_path):
    cfg = _cfg(tmp_path, replacements=[Rule("风起", "起风")])
    tree, _ = process(SAMPLE, cfg)
    assert tree[1].title == "第一卷 起风"
    assert tree[1].raw_title == "第一卷 风起"


def test_raw_stage_result_is_escaped_for_the_page(tmp_path):
    """raw 阶段塞进来的 `<` 当文本转义，不会变成标签。"""
    node = process(SAMPLE, _cfg(tmp_path, replacements=[Rule("第一卷", "<b>")]))[0][1]
    assert node.title == "<b> 风起"
    assert node.title_html == "&lt;b&gt; 风起"


def test_html_stage_injects_markup_into_the_heading(tmp_path):
    """html 阶段在转义之后匹配，替换结果原样进书页标题（纯文本标题不受影响）。"""
    cfg = _cfg(
        tmp_path,
        replacements=[Rule(r"第(.+)章", r'第<span class="num">\1</span>章', "html")],
    )
    node = process(SAMPLE, cfg)[0][1].children[0]
    assert node.title == "第一章 初遇"
    assert node.title_html == '第<span class="num">一</span>章 初遇'


def test_raw_runs_before_html(tmp_path):
    """两个阶段一前一后：raw 改完再转义，html 在转义结果上接着改。"""
    cfg = _cfg(
        tmp_path,
        replacements=[Rule("初遇", "重逢"), Rule("重逢", "<i>重逢</i>", "html")],
    )
    node = process(SAMPLE, cfg)[0][1].children[0]
    assert node.title == "第一章 重逢"
    assert node.title_html == "第一章 <i>重逢</i>"


def test_stages_apply_independently_in_one_pass(tmp_path):
    cfg = _cfg(
        tmp_path,
        replacements=[Rule("风起", "起风", "raw"), Rule("离别", "别离", "html")],
    )
    volume = process(SAMPLE, cfg)[0][1]
    assert volume.title == "第一卷 起风"
    assert volume.title_html == "第一卷 起风"
    # html 阶段不改纯文本标题，只改书页标题
    assert volume.children[1].title == "第二章 离别"
    assert volume.children[1].title_html == "第二章 别离"


# ---------- 预览：界面单独跑一遍标题替换 ----------


def _preview(replacements=()):
    tree, _ = scan_toc(SAMPLE, Config())
    return preview_titles(tree, list(replacements))


def test_preview_lists_every_title_in_document_order():
    results = _preview()
    assert [(r.level, r.raw_title) for r in results] == [
        (0, "前言"),
        (2, "第一卷 风起"),
        (3, "第一章 初遇"),
        (3, "第二章 离别"),
    ]


def test_preview_leaves_the_scanned_tree_untouched():
    """预览是纯函数：生成阶段还要拿这棵树自己再算一遍。"""
    tree, _ = scan_toc(SAMPLE, Config())
    preview_titles(tree, [Rule("风起", "起风")])
    assert tree[1].title == "第一卷 风起"
    assert tree[1].title_html == ""


def test_preview_applies_the_raw_stage():
    volume = _preview([Rule("风起", "起风")])[1]
    assert volume.title == "第一卷 起风"
    assert volume.raw_title == "第一卷 风起"


def test_preview_without_html_rules_shows_unescaped_text():
    """没有 html 规则时 `title_html` 只是转义结果，界面该显示未转义的 `title`。"""
    volume = _preview([Rule("第一卷", "<b>")])[1]
    assert (volume.title, volume.title_html) == ("<b> 风起", "&lt;b&gt; 风起")
    assert volume.html_hit is False


def test_preview_flags_an_html_rule_that_fired():
    chapter = _preview([Rule(r"第(.+)章", r'第<span class="num">\1</span>章', "html")])[2]
    assert chapter.title == "第一章 初遇"
    assert chapter.title_html == '第<span class="num">一</span>章 初遇'
    assert chapter.html_hit is True


def test_preview_flags_an_html_rule_that_changed_nothing():
    """替换文本与原文相同也算命中：这条规则确实作用过，界面照样标蓝。"""
    chapter = _preview([Rule("初遇", "初遇", "html")])[2]
    assert chapter.html_hit is True


def test_preview_flags_only_the_titles_a_rule_reached():
    results = _preview([Rule("离别", "别离", "html")])
    assert [r.html_hit for r in results] == [False, False, False, True]


def test_preview_agrees_with_what_process_writes(tmp_path):
    """预览与生成走同一条链，同一份规则下结果必须一致。"""
    replacements = [Rule("风起", "起风"), Rule("离别", "<i>别离</i>", "html")]
    tree, _ = process(SAMPLE, _cfg(tmp_path, replacements=replacements))
    results = preview_titles(scan_toc(SAMPLE, Config())[0], replacements)
    for node, result in zip(walk(tree), results):
        assert (result.title, result.title_html) == (node.title, node.title_html)


# ---------- 目录 ----------


def test_toc_text_is_indented(cfg):
    text = toc_text(read_book(cfg))
    assert "第一卷 风起" in text
    assert "  第一章 初遇" in text


def test_toc_json_round_trips(cfg):
    """目录树 JSON 回喂 `tree_from_json`，原始标题与正文逐节点一致。"""
    lines = LINES.splitlines()
    tree, _ = scan_toc(lines, resolve(cfg))
    data = to_json(tree)
    assert data[0]["raw_title"] == "第一卷 风起"
    # Full-span semantics: a parent covers all its children's lines.
    assert data[0]["lines"] == [1, 5]
    assert data[1]["lines"] == [2, 3]
    restored = tree_from_json(data, lines)
    assert [n.raw_title for n in walk(restored)] == [n.raw_title for n in walk(tree)]
    assert [n.paragraphs for n in walk(restored)] == [n.paragraphs for n in walk(tree)]


def test_scan_toc_from_toc_file(cfg, tmp_path):
    """--toc-file：跳过正则解析按行号取正文；标题用文件现值，替换照常跑。"""
    lines = LINES.splitlines()
    data = to_json(scan_toc(lines, resolve(cfg))[0])
    data[0]["raw_title"] = "第一卷 改名"
    toc_path = tmp_path / "toc.json"
    toc_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    tree, stats = process(
        lines,
        replace(resolve(cfg), toc_file=toc_path, replacements=[Rule("初遇", "重逢")]),
    )
    assert tree[0].title == "第一卷 改名"
    assert tree[0].children[0].title == "第一章 重逢"
    assert tree[0].children[0].paragraphs == ["正文一字"]
    assert tree[0].children[1].paragraphs == ["正文二字"]
    assert stats.level_counts == {2: 1, 3: 2}
    assert stats.has_preface is False


def test_toc_rejects_unknown_format(cfg):
    with pytest.raises(ValueError, match="目录格式"):
        toc_text(read_book(replace(cfg, toc_format="xml")))


def test_write_toc_writes_file(cfg, tmp_path):
    out = tmp_path / "目录.md"
    book = read_book(replace(cfg, out=out))
    assert write_toc(book) == out
    assert "第一章 初遇" in out.read_text(encoding="utf-8")


def test_write_toc_json(cfg, tmp_path):
    out = tmp_path / "toc.json"
    write_toc(read_book(replace(cfg, out=out, toc_format="json")))
    assert json.loads(out.read_text(encoding="utf-8"))[0]["raw_title"] == "第一卷 风起"


# ---------- EPUB ----------


def test_write_epub_writes_zip(cfg, tmp_path):
    out = write_epub(read_book(replace(cfg, out=tmp_path / "out.epub")))
    assert zipfile.is_zipfile(out)
    with zipfile.ZipFile(out) as zf:
        names = zf.namelist()
        assert "mimetype" in names
        assert "EPUB/content.opf" in names
        assert any(n.startswith("EPUB/text/") for n in names)


def test_write_epub_falls_back_to_input_name(cfg):
    assert write_epub(read_book(cfg)) == cfg.input.with_suffix(".epub")


def test_write_epub_adds_missing_suffix(cfg, tmp_path):
    assert (
        write_epub(read_book(replace(cfg, out=tmp_path / "b"))) == tmp_path / "b.epub"
    )


def test_write_epub_keeps_uppercase_suffix(cfg, tmp_path):
    out = write_epub(read_book(replace(cfg, out=tmp_path / "b.EPUB")))
    assert out == tmp_path / "b.EPUB"


def test_write_epub_creates_output_dir(cfg, tmp_path):
    assert write_epub(
        read_book(replace(cfg, out=tmp_path / "deep" / "a.epub"))
    ).is_file()


def test_write_epub_respects_overwrite_flag(cfg, tmp_path):
    out = tmp_path / "out.epub"
    out.write_bytes(b"x")
    with pytest.raises(ValueError, match="已存在"):
        write_epub(read_book(replace(cfg, out=out, overwrite=False)))


def test_write_epub_can_overwrite(cfg, tmp_path):
    out = tmp_path / "a.epub"
    out.write_bytes(b"x")
    book = read_book(replace(cfg, out=out, overwrite=True))
    assert zipfile.is_zipfile(write_epub(book))


def test_write_epub_reports_failure_with_context(cfg, tmp_path):
    """组装阶段出错要补上「无法生成 EPUB」这个上下文。"""
    book = read_book(
        replace(cfg, out=tmp_path / "a.epub", css_file=tmp_path / "nope.css")
    )
    with pytest.raises(ValueError, match="无法生成 EPUB"):
        write_epub(book)


def test_write_epub_leaves_no_partial_file(cfg, tmp_path):
    """失败时不该留下半个 EPUB。"""
    out = tmp_path / "a.epub"
    book = read_book(replace(cfg, out=out, css_file=tmp_path / "nope.css"))
    with pytest.raises(ValueError):
        write_epub(book)
    assert not out.exists()


# ---------- CSS ----------


def test_write_css_writes_only_css(cfg, tmp_path):
    out = tmp_path / "book.css"
    assert write_css(replace(cfg, dump_css=out)) == out
    assert "body" in out.read_text(encoding="utf-8")
    assert not list(tmp_path.glob("*.epub"))


def test_write_css_needs_no_input(tmp_path):
    """只排版不读内容：没有输入文件也能导出 CSS。"""
    assert "body" in write_css(Config(dump_css=tmp_path / "b.css")).read_text(
        encoding="utf-8"
    )


def test_write_css_needs_a_path():
    with pytest.raises(ValueError, match="缺少 CSS 输出路径"):
        write_css(Config())


# ---------- write_text ----------


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
