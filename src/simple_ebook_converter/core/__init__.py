"""core 是两个前端的内部实现：纯转换，不依赖 click 与 tkinter。

模块各自负责一件事，前端按需要直接从对应模块导入，不在这里转手：`config`（参数与
默认值）、`options`（选项表）、`pipeline`（读文件、切分、产出文件）、`builder`
（组装 EPUB）、`parser` / `text` / `replace` / `toc` / `levels` / `meta` /
`encoding` / `mediatypes` / `sources`（资源内容预加载）/ `validation`（值域校验）。
"""

from .._meta import __version__

__all__ = ["__version__"]
