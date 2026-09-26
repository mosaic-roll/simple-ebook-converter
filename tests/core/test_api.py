import importlib
import pkgutil
from importlib.metadata import version
from types import ModuleType

import pytest

from sec import core


def _public_names() -> set[str]:
    """各子模块里"自己定义"的公共名字（排除下划线私有、import 进来的模块与再导出）。"""
    names: set[str] = set()
    for info in pkgutil.iter_modules(core.__path__):
        mod = importlib.import_module(f"sec.core.{info.name}")
        for name, obj in vars(mod).items():
            if name.startswith("_") or isinstance(obj, ModuleType):
                continue
            # 常量（tuple/int）没有 __module__，默认算本模块定义
            if getattr(obj, "__module__", mod.__name__) == mod.__name__:
                names.add(name)
    return names


def test_version_matches_packaging_metadata():
    """版本号只以 pyproject.toml 为准，代码里不再写死一份。"""
    assert core.__version__ == version("sec")


def test_all_names_are_importable():
    """__all__ 里每一项都要真的能拿到，否则 from sec.core import X 直接失败。"""
    for name in core.__all__:
        assert hasattr(core, name), f"__all__ 里的 {name} 并不存在"


def test_no_public_name_is_missing_from_all():
    """新增了公共函数/常量就必须同时加进 __all__。"""
    missing = _public_names() - set(core.__all__)
    assert not missing, f"这些公共名字没进 __all__：{sorted(missing)}"


@pytest.mark.parametrize("name", ["ALIGN_CHOICES", "ENCODING_CHOICES", "fallback_title"])
def test_recently_added_names_are_exported(name):
    """点名单测这几个名字，避免 __all__ 漏导出时不易发现。"""
    assert name in core.__all__
