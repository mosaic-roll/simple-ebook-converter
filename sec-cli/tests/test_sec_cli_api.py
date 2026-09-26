from importlib.metadata import version

import sec_cli
from sec_cli.cli import VERSION


def test_version_matches_packaging_metadata():
    """--version 与包元数据一致，代码里不再写死一份字面量。"""
    assert VERSION == version("sec-cli")
    assert sec_cli.__version__ == version("sec-cli")
