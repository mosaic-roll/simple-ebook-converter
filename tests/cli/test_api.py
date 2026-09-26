from importlib.metadata import version

import sec.cli
from sec.cli.cli import VERSION


def test_version_matches_packaging_metadata():
    """`--version` 与包元数据一致；全项目只有一个版本号，代码里不再写死字面量。"""
    assert VERSION == version("sec")
    assert sec.cli.__version__ == version("sec")


def test_all_frontends_share_one_version():
    """sec / sec.core / sec.cli / sec.gui 报的都是同一个 pyproject.toml 里的版本号。"""
    import sec.core
    import sec.gui

    assert sec.__version__ == sec.core.__version__ == sec.cli.__version__ == sec.gui.__version__
