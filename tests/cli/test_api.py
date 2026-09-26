from importlib.metadata import version

import simple_ebook_converter.cli
from simple_ebook_converter._meta import CLI_PROG, DIST_NAME
from simple_ebook_converter.cli.cli import VERSION


def test_version_matches_packaging_metadata():
    """`--version` 与包元数据一致；全项目只有一个版本号，代码里不再写死字面量。"""
    assert VERSION == version(DIST_NAME)
    assert simple_ebook_converter.cli.__version__ == version(DIST_NAME)


def test_all_frontends_share_one_version():
    """顶层包 / core / cli / gui 报的都是同一个 pyproject.toml 里的版本号。"""
    import simple_ebook_converter.core
    import simple_ebook_converter.gui

    assert (
        simple_ebook_converter.__version__
        == simple_ebook_converter.core.__version__
        == simple_ebook_converter.cli.__version__
        == simple_ebook_converter.gui.__version__
    )


def test_prog_name_used_in_help_and_version():
    """`--help` / `--version` 里显示的命令名要跟实际装的命令一致。"""
    assert CLI_PROG == f"{DIST_NAME}-cli"
