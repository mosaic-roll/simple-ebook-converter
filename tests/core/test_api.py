import importlib
import pkgutil
import tomllib
from importlib.metadata import version
from pathlib import Path
from types import ModuleType

import pytest

from simple_ebook_converter import core
from simple_ebook_converter._meta import CLI_PROG, DIST_NAME, IMPORT_NAME


def _modules() -> dict[str, ModuleType]:
    return {
        info.name: importlib.import_module(f"simple_ebook_converter.core.{info.name}")
        for info in pkgutil.iter_modules(core.__path__)
    }


def _public_names() -> set[str]:
    """各子模块里"自己定义"的公共名字（排除下划线私有、import 进来的模块与再导出）。"""
    names: set[str] = set()
    for mod in _modules().values():
        for attr, obj in vars(mod).items():
            if attr.startswith("_") or isinstance(obj, ModuleType):
                continue
            # 常量（tuple/int）没有 __module__，默认算本模块定义
            if getattr(obj, "__module__", mod.__name__) == mod.__name__:
                names.add(attr)
    return names


def test_version_matches_packaging_metadata():
    """版本号只以 pyproject.toml 为准，代码里不再写死一份。"""
    assert core.__version__ == version(DIST_NAME)


def test_names_match_pyproject():
    """`_meta` 里写死的包名/命令名必须和 pyproject.toml 对得上。

    改名时漏改 `_meta.DIST_NAME` 会让 `version()` 直接抛 PackageNotFoundError，
    漏改命令名则会让 `--help` 显示一个不存在的命令。
    """
    pyproject = Path(__file__).parents[2] / "pyproject.toml"
    if not pyproject.is_file():  # 从 sdist 跑测试时没有 pyproject，跳过
        pytest.skip("找不到 pyproject.toml")
    project = tomllib.loads(pyproject.read_text(encoding="utf-8"))["project"]

    assert DIST_NAME == project["name"]
    assert IMPORT_NAME == "simple_ebook_converter"
    assert set(project["scripts"]) == {DIST_NAME, CLI_PROG}
    assert project["scripts"][CLI_PROG] == f"{IMPORT_NAME}.cli.cli:main"
    assert project["scripts"][DIST_NAME] == f"{IMPORT_NAME}.gui.__main__:main"


def test_all_names_are_importable():
    """__all__ 里每一项都要真的能拿到，否则 from simple_ebook_converter.core import X 直接失败。"""
    for name in core.__all__:
        assert hasattr(core, name), f"__all__ 里的 {name} 并不存在"


def test_core_package_does_not_re_export_submodules():
    """core 是两个前端的内部实现，不是一个公共库门面。

    东西都放在各自的模块里（`core.config`、`core.pipeline`…），`core` 包本身只留版本号：
    这样谁负责什么一眼可见，前端也从用得着的那一个模块直接导入。
    """
    assert core.__all__ == ["__version__"]
    leaked = _public_names() & set(vars(core))
    assert not leaked, f"core 不该转手导出子模块的东西：{sorted(leaked)}"


def test_all_is_sorted_and_has_no_duplicates():
    assert len(set(core.__all__)) == len(core.__all__)


def test_core_does_not_import_frontends():
    """core 不得依赖任何前端：否则打包 CLI 会拖进 tkinter，打包 GUI 会拖进 click。"""
    imported: set[str] = set()
    for mod in _modules().values():
        imported |= {
            obj.__name__ for obj in vars(mod).values() if isinstance(obj, ModuleType)
        }
    assert "click" not in imported
    assert "tkinter" not in imported
