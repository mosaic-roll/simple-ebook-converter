from pathlib import Path

import pytest

from sec_core.config import Config, LevelRule, default_levels
from sec_core.parser import NoEnabledRulesError
from sec_core.pipeline import fallback_title, process
from sec_core.replace import Rule

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


def test_process_falls_back_to_filename_stem(tmp_path):
    """没有标题命中时，整篇归到一章，标题取文件名。"""
    src = tmp_path / "我的小说.txt"
    tree, stats = process(["没有标题的一行", "另一行"], Config(input=src))
    assert stats.has_preface is False
    assert len(tree) == 1
    assert tree[0].title == "我的小说"
    assert tree[0].paragraphs == ["没有标题的一行", "另一行"]


def test_fallback_title_prefers_explicit_title(tmp_path):
    assert fallback_title(Config(title="书名", input=tmp_path / "x.txt")) == "书名"


def test_fallback_title_without_input_or_title():
    assert fallback_title(Config()) == "未命名"


def test_process_cleans_by_default(tmp_path):
    tree, _ = process(["\u3000\u3000正文一　", "", "  ", "正文二"], _cfg(tmp_path))
    node = tree[0]
    assert node.paragraphs == ["正文一", "正文二"]


def test_process_no_clean_keeps_blank_lines(tmp_path):
    tree, _ = process(["正文一", "", "正文二"], _cfg(tmp_path, no_clean=True))
    assert tree[0].paragraphs == ["正文一", "", "正文二"]


def test_process_replaces_titles_and_bodies_keeping_raw(tmp_path):
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
    """两次调用不能互相污染 default_levels()（process 不应改传入的 list 元素）。"""
    a = _cfg(tmp_path)
    b = _cfg(tmp_path, levels=[*default_levels()])
    process(SAMPLE, a)
    process(SAMPLE, b)
    assert [r.level for r in b.levels] == [r.level for r in default_levels()]
