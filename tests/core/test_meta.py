from simple_ebook_converter.core.meta import guess_metadata, resolve_metadata


def test_guess_full():
    assert guess_metadata("《希灵帝国》（校对版全本）作者：远瞳") == ("希灵帝国", "远瞳")


def test_guess_no_extra():
    assert guess_metadata("《希灵帝国》作者：远瞳") == ("希灵帝国", "远瞳")


def test_guess_title_only():
    assert guess_metadata("《没有作者的书》全本") == ("没有作者的书", None)


def test_guess_no_match():
    assert guess_metadata("novel") == (None, None)


def test_guess_author_with_parenthesis():
    assert guess_metadata("《A》作者：B（校对版）") == ("A", "B")


def test_resolve_guesses_from_filename():
    assert resolve_metadata("《希灵帝国》作者：远瞳.txt") == ("希灵帝国", "远瞳")


def test_resolve_accepts_full_path(tmp_path):
    path = tmp_path / "《书名》作者：某人.txt"
    assert resolve_metadata(path) == ("书名", "某人")


def test_resolve_explicit_wins_over_guess():
    assert resolve_metadata("《希灵帝国》作者：远瞳.txt", "手写", "张三") == ("手写", "张三")


def test_resolve_partial_explicit_falls_back_per_field():
    assert resolve_metadata("《希灵帝国》作者：远瞳.txt", title="手写") == ("手写", "远瞳")
    assert resolve_metadata("《希灵帝国》作者：远瞳.txt", author="张三") == ("希灵帝国", "张三")


def test_resolve_blank_explicit_is_treated_as_absent():
    assert resolve_metadata("《希灵帝国》作者：远瞳.txt", "", "  ") == ("希灵帝国", "远瞳")


def test_resolve_falls_back_to_stem_never_none():
    """猜不到时退回文件名本身，前端不会再拿到 None 写进元数据。"""
    assert resolve_metadata("novel.txt") == ("novel", "")
    assert resolve_metadata("我的小说.txt") == ("我的小说", "")


def test_resolve_never_returns_none_for_plain_name():
    title, author = resolve_metadata("novel.txt")
    assert title is not None
    assert author == ""
