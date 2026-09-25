from sec_cli.meta import guess_metadata


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