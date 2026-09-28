# simple-ebook-converter — TXT 转 EPUB3 工具

将 TXT 文本解析为章节并生成 EPUB3。一个 distribution 装三个顶层子包：

| 子包                            | 说明                                                |
| ------------------------------- | --------------------------------------------------- |
| `simple_ebook_converter.core`   | 核心库，不依赖任何前端；无状态，模块各管一件事        |
| `simple_ebook_converter.cli`    | 命令行前端，入口点 `simple-ebook-converter-cli`     |
| `simple_ebook_converter.gui`    | Tkinter 图形界面前端，入口点 `simple-ebook-converter` |

版本号只有一处：根 `pyproject.toml` 的 `version`。`simple_ebook_converter.__version__`、
`simple_ebook_converter.core.__version__` 等全部由 `simple_ebook_converter._meta` 里的
`DIST_NAME` 查同一个值，代码里不写死。

依赖：`ebooklib` + `chardet` + `click`。使用 [uv](https://github.com/astral-sh/uv) 管理。

## 安装

```bash
uv sync
```

就这一条命令——只有一个包需要安装，不再有 workspace 成员，也不需要 `--all-packages`。

## 用法

命令行：

```bash
uv run simple-ebook-converter-cli 我的小说.txt                        # 生成 我的小说.epub
uv run simple-ebook-converter-cli 我的小说.txt --title "书名" --author "作者"
uv run simple-ebook-converter-cli 我的小说.txt --toc-only             # 只输出目录（stdout）
uv run simple-ebook-converter-cli 我的小说.txt --toc-only --toc-format json
uv run simple-ebook-converter-cli 我的小说.txt --toc-only -o toc.json  # 目录写入文件
uv run simple-ebook-converter-cli 我的小说.txt --dump-css out.css     # 只导出 CSS
```

单一命令，靠 `--toc-only` 切换「只输出目录」模式。完整选项见 `uv run simple-ebook-converter-cli --help`。

图形界面：

```bash
uv run simple-ebook-converter
```

作为库：

```python
from pathlib import Path

from simple_ebook_converter.core.config import Config
from simple_ebook_converter.core.encoding import read_lines
from simple_ebook_converter.core.pipeline import process, resolve

cfg = resolve(Config(input=Path("novel.txt")))  # 补全封面与书名/作者，返回新的 Config
lines, used = read_lines(cfg.input, cfg.encoding)
tree, stats = process(lines, cfg)
```

`core` 是两个前端的内部实现，不设统一门面：每个模块各管一件事，用哪一块就从哪一块导入。
`resolve()` 从文件名猜书名/作者（`《书名》作者：作者`，
见 `simple_ebook_converter.core.meta.resolve_metadata()`）并自动发现封面，
补全后返回**新**的 `Config`，不改传入的那一个。

## 替换规则的阶段

替换规则**只作用于标题**（要改正文，直接改源文件更直接）。`--replace-rules` 收一个
JSON 文件（内容是一个有序列表），每条规则可带可选的 `stage`，决定在 HTML 转义之前
还是之后匹配：

```json
[
  { "pattern": "^#+\\s*", "replace": "" },
  { "pattern": "(第.{1,10}章)\\s*", "replace": "<span class=\"chapter-number\">\\1</span>", "stage": "html" }
]
```

| `stage` | 匹配对象 | 替换结果 |
|---------|----------|----------|
| `raw`   | 原始标题（转义前） | 照常在写出时转义——**默认值** |
| `html`  | 已转义的标题（转义后） | 按 HTML 原样注入，可含标签 |

`raw` 先于 `html`：先改原文标题（写进 `node.title`，目录页/NCX/元数据都用它），
再转义，然后 `html` 规则在转义结果上再改一次，结果写进书页标题的 HTML 片段。
所以 `html` 阶段适合给标题里的片段（如整段「第…章」）套 `<span>`，再用 `--css-append`
上样式；它不会影响纯文本的目录与元数据。原始标题始终保留在 `node.raw_title`。

## 封面

封面有三种结果，优先级从高到低：

1. **显式 `--cover PATH`** —— 用这张图。
2. **自动发现** —— 不给 `--cover` 时，在**输入文件同目录**找一张名为 `cover` 的图片
   （大小写不敏感，扩展名取 `COVER_TYPES` 全集：jpg/jpeg/png/gif/svg/webp/avif）。
   **恰好命中一张**才采用；命中零张或多张都不算——多张说明作者没拿准，
   静默挑一张反而会咬人。
3. **文字封面页** —— 仍然没有图时（默认开启），在书的最前面插一个只含**书名和作者**
   的封面页。用 `--no-text-cover` 关掉，关掉后整本书就没有封面。

封面页走 EPUB 标准，不自造 CSS class：内容放在 `<section epub:type="cover">` 里，
阅读器认这个语义角色。有图时图片在 OPF manifest 里带 `properties="cover-image"`，
并额外补一条 `<meta name="cover">` 兼容 EPUB2 时代的阅读器。封面页会链到 `style.css`，
内置样式用 `body > section` 这组结构选择器排版；`--css-append` 追加在内置样式之后，
`--css-file` 则是**整份替代**内置样式（两者互斥，要用它定封面样式就照抄这组选择器，
`--dump-css` 可导出内置模板作起点）
（各家阅读器对 CSS 里带命名空间的 `epub|type` 属性选择器支持不一致，所以没拿它来选）。

```bash
simple-ebook-converter-cli novel.txt                          # 同目录没 cover.* → 生成文字封面页
simple-ebook-converter-cli novel.txt --no-text-cover          # 不要文字封面页
simple-ebook-converter-cli novel.txt --cover cover.png        # 显式给图
```

## 处理流程

`simple_ebook_converter.core.pipeline` 提供完整的「读文件 → 切分 → 写产物」，两个前端都只做
「收集参数 → 调 pipeline → 展示结果」，不各自实现其中任何一步。程序是无状态的：
`resolve(cfg)` 补全参数后返回**新**的 `Config`，`read_book(cfg)` 读文件并切分，产出方式由
`cfg` 上的开关决定：

1. `resolve()`：封面自动发现（没给 `--cover` 时找同目录的 `cover.*`）→ `Config.validate()`
   （校验取值范围、日期格式、字体/封面格式）→ 从文件名猜书名/作者
2. 读取与编码识别（BOM → chardet → 逐个尝试，`--encoding` 可手动指定）
3. 阶段一 `scan_toc()`：按标题正则切分为章节，或按 `--toc-file` 读回编辑过的目录树
4. 阶段二 `process()`：逐页清理（去段首/段尾空格、删空行，`--no-clean` 关闭）
5. 替换标题：`raw` 规则改纯文本标题（目录/元数据都用它），`html` 规则在转义后改书页标题
   （见「替换规则的阶段」）
6. 按开关产出：`cfg.toc_only` → `write_toc()` / `toc_text()`；`cfg.dump_css` →
   `write_css()`（只导出 CSS，不读输入）；否则 `write_epub()` 组装 EPUB3
   （只给 h1~h3 各建一个内容文档，h4+ 并入上级页并以片段进目录；zip 最高压缩等级
   `compresslevel=9`）

封面页是在第 6 步组装时定的，所以「文字封面」拿得到第 1、2 步猜出来的书名/作者。

## 测试

```bash
uv run pytest                    # 全部用例
uv run pytest tests/core         # 仅核心库
uv run pytest tests/cli          # 仅命令行前端
uv run pytest tests/gui          # 仅图形界面前端
```
