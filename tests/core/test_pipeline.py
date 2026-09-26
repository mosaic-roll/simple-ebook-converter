from pathlib import Path

import pytest

from simple_ebook_converter.core.config import Config, LevelRule, default_levels
from simple_ebook_converter.core.parser import NoEnabledRulesError
from simple_ebook_converter.core.pipeline import process
from simple_ebook_converter.core.replace import SCOPE_ALL, SCOPE_BODY, SCOPE_TITLE, Rule

SAMPLE = [
    "封面文案",
    "第一卷 风起",
    "第一章 初遇",
    "正文一字",
    "第二章 离别",
    "正文二字",
]


def _cfg(tmp_path: Path, **kwargs) -> Config:
    return Config(input=tmp_path / "《测试书》作者：某人.txt", **kwargs)


def test_process_guesses_metadata_into_cfg(tmp_path):
    """书名/作者由 process 按文件名猜好并写回 cfg，两个前端不必各自实现。"""
    cfg = _cfg(tmp_path)
    assert cfg.title is None and cfg.author == ""
    process(SAMPLE, cfg)
    assert (cfg.title, cfg.author) == ("测试书", "某人")


def test_process_keeps_explicit_metadata(tmp_path):
    cfg = _cfg(tmp_path, title="手写书名", author="手写作")
    process(SAMPLE, cfg)
    assert (cfg.title, cfg.author) == ("手写书名", "手写作")


def test_process_metadata_is_idempotent(tmp_path):
    """重复调用不会把已猜出的值再猜一遍。"""
    cfg = _cfg(tmp_path)
    process(SAMPLE, cfg)
    process(SAMPLE, cfg)
    assert (cfg.title, cfg.author) == ("测试书", "某人")


def test_process_without_input_leaves_metadata_alone():
    cfg = Config()
    process(SAMPLE, cfg)
    assert cfg.title is None and cfg.author == ""


def test_process_validates_config(tmp_path):
    """取值范围由 process 兜住，不必指望每个前端记得调 validate()。"""
    with pytest.raises(ValueError, match="目录深度"):
        process(SAMPLE, _cfg(tmp_path, toc_depth=99))


def test_process_reports_disabled_levels(tmp_path):
    cfg = _cfg(tmp_path, levels=[LevelRule(2, "", "volume")])
    with pytest.raises(NoEnabledRulesError):
        process(SAMPLE, cfg)


def test_process_falls_back_to_book_title(tmp_path):
    """没有标题命中时，整篇归到一章，标题取书名。"""
    src = tmp_path / "我的小说.txt"
    tree, stats = process(["没有标题的一行", "另一行"], Config(input=src))
    assert stats.has_preface is False
    assert len(tree) == 1
    assert tree[0].title == "我的小说"
    assert tree[0].paragraphs == ["没有标题的一行", "另一行"]


def test_process_uses_resolved_title_as_fallback(tmp_path):
    """书名是猜出来的也能当兜底章节名。"""
    src = tmp_path / "《测试书》作者：某人.txt"
    tree, _ = process(["没有标题"], Config(input=src))
    assert tree[0].title == "测试书"


def test_process_cleans_by_default(tmp_path):
    tree, _ = process(["　　正文一　", "", "  ", "正文二"], _cfg(tmp_path))
    assert tree[0].paragraphs == ["正文一", "正文二"]


def test_process_keeps_blank_lines_when_not_cleaning(tmp_path):
    tree, _ = process(["正文一", "", "正文二"], _cfg(tmp_path, clean=False))
    assert tree[0].paragraphs == ["正文一", "", "正文二"]


def test_process_replaces_titles_and_bodies_keeping_raw(tmp_path):
    cfg = _cfg(tmp_path, replacements=[Rule(r"^第", "第X", SCOPE_ALL)])
    tree, _ = process(SAMPLE, cfg)
    volume = tree[1]
    assert volume.title == "第X一卷 风起"
    assert volume.raw_title == "第一卷 风起"
    assert volume.children[0].title == "第X一章 初遇"
    assert volume.children[0].raw_title == "第一章 初遇"


# ---------- 替换的作用范围 ----------


def test_default_scope_touches_titles_only(tmp_path):
    """默认只改标题：GUI 里只能看到目录，默认动正文反而不符合直觉。"""
    cfg = _cfg(tmp_path, replacements=[Rule("正文一", "改了")])
    tree, _ = process(SAMPLE, cfg)
    assert tree[1].children[0].paragraphs == ["正文一字"]
    assert tree[1].title == "第一卷 风起"


def test_body_scope_touches_paragraphs_only(tmp_path):
    cfg = _cfg(tmp_path, replacements=[Rule("正文一", "改了", SCOPE_BODY)])
    tree, _ = process(SAMPLE, cfg)
    assert tree[1].children[0].paragraphs == ["改了字"]
    assert tree[1].title == "第一卷 风起"


def test_all_scope_touches_both(tmp_path):
    cfg = _cfg(tmp_path, replacements=[Rule("一", "壹", SCOPE_ALL)])
    tree, _ = process(SAMPLE, cfg)
    assert tree[1].title == "第壹卷 风起"
    assert tree[1].children[0].paragraphs == ["正文壹字"]


def test_scopes_apply_independently_in_one_pass(tmp_path):
    """标题规则与正文规则混在一份列表里，各走各的，互不干扰。"""
    cfg = _cfg(
        tmp_path,
        replacements=[
            Rule("风起", "起风", SCOPE_TITLE),
            Rule("正文一", "P1", SCOPE_BODY),
            Rule("离别", "别离", SCOPE_ALL),
        ],
    )
    tree, _ = process(SAMPLE, cfg)
    volume = tree[1]
    assert volume.title == "第一卷 起风"
    assert volume.children[0].paragraphs == ["P1字"]
    # scope=all 的规则两边都进
    assert volume.children[1].title == "第二章 别离"
    assert volume.children[1].paragraphs == ["正文二字"]


def test_body_only_rules_leave_titles_untouched(tmp_path):
    cfg = _cfg(tmp_path, replacements=[Rule("第", "X", SCOPE_BODY)])
    tree, _ = process(SAMPLE, cfg)
    assert tree[1].title == "第一卷 风起"
    assert tree[1].raw_title == "第一卷 风起"


# ---------- 封面自动发现 ----------


def test_process_discovers_cover_next_to_input(tmp_path):
    cover = tmp_path / "cover.png"
    cover.write_bytes(b"\x89PNG")
    cfg = _cfg(tmp_path)
    assert cfg.cover is None
    process(SAMPLE, cfg)
    assert cfg.cover == cover


def test_process_keeps_explicit_cover(tmp_path):
    (tmp_path / "cover.png").write_bytes(b"\x89PNG")
    explicit = tmp_path / "mine.jpg"
    explicit.write_bytes(b"\xff\xd8")
    cfg = _cfg(tmp_path, cover=explicit)
    process(SAMPLE, cfg)
    assert cfg.cover == explicit


def test_process_leaves_cover_none_when_absent(tmp_path):
    cfg = _cfg(tmp_path)
    process(SAMPLE, cfg)
    assert cfg.cover is None


def test_discovered_cover_passes_validation(tmp_path):
    """自动发现的封面也必须过得了 Config.validate()。"""
    (tmp_path / "cover.webp").write_bytes(b"RIFF")
    cfg = _cfg(tmp_path)
    process(SAMPLE, cfg)
    cfg.validate()


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
