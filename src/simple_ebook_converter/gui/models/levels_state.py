"""内置层级的三态：`None`（没动过）/ `""`（显式关闭）/ 非空正则。

三态不能只看控件：文本框里**总**有内容（core 缺省正则），所以「没动过」和「动过但
值恰好等于缺省」区分不开 —— 必须另记一个「用户动过没有」的标记。规则就这两条，
抽出来脱离 Tk 单测。

`default_pattern`（core 缺省正则）由调用方解析后传入，本模块不 import core。
"""

from __future__ import annotations


def from_saved(given: str | None, default_pattern: str) -> tuple[bool, str, bool]:
    """已保存的三态值 → `(enabled, pattern, touched)`。

    * `None`（没存过）→ 勾上、填 core 缺省、**未动过**（以后 core 改缺省能跟上）
    * `""`（显式关闭）→ 不勾
    * 非空 → 勾上、用该正则、**动过**
    """
    if given is None:
        return True, str(default_pattern), False
    return bool(given), given, True


def to_saved(enabled: bool, touched: bool, text: str) -> str | None:
    """`(enabled, touched, text)` → 三态值。

    * 没勾 → `""`（显式关闭）
    * 没动过 → `None`（不发这个键，core 用 `option_default`）
    * 动过 → 文本（只判空；首尾空格有意义，原样保留）
    """
    if not enabled:
        return ""
    if not touched:
        return None
    return text if text.strip() else ""
