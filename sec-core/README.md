# sec-core — TXT 转 EPUB3 核心库

`sec-cli`（命令行）与 `sec-gui`（Tkinter 图形界面）共用的核心实现，本身不提供可执行入口。

依赖：`ebooklib` / `chardet`。由工作区根目录的 [uv](https://github.com/astral-sh/uv) 管理。

## 模块

| 模块 | 职责 |
|------|------|
| `sec_core.config` | `Config` / `LevelRule` / `Node` 数据模型，内置默认标题正则 |
| `sec_core.meta` | 从 `《书名》作者：作者` 文件名猜书名与作者 |
| `sec_core.encoding` | BOM → chardet → 逐个尝试的编码识别与解码 |
| `sec_core.levels` | 解析 `--level 级别:正则[:类名]`，由 preset 生成层级规则 |
| `sec_core.parser` | 按标题规则把行切分为章节树 |
| `sec_core.cleaner` | 去段首/段尾空白（含全角空格）、删空行 |
| `sec_core.replace` | 解析并应用有序替换规则（同时作用于标题与正文） |
| `sec_core.pipeline` | 统一处理管线：切分 → 清理 → 替换 |
| `sec_core.toc` | 章节树转纯文本 / JSON 目录 |
| `sec_core.builder` | 生成 CSS、组装 EPUB3 |

## 给前端用的两个入口

```python
from sec_core import Config, config_defaults, resolve_metadata

# 1) 表单默认值：全部从 Config() 派生，前端不再重复硬编码
defaults = config_defaults()          # {"encoding": "auto", "max_title_len": 35, ...}
defaults["volume"], defaults["section"]  # 卷/章/节内置正则，节默认为空（不启用）

# 2) 元数据：显式指定优先，否则从文件名猜
title, author = resolve_metadata("《希灵帝国》作者：远瞳.txt")
```

`config_defaults()` 覆盖 `Config` 的全部字段，含 `volume`/`chapter`/`section`
三个由 `levels` 拆出的正则字符串，`toc_depth`、`chapter_align` 等排版项与
`preface_title` 一并给出，前端照单填表即可。

## 测试

```bash
uv run pytest sec-core
```
