# sec — TXT 转 EPUB3 工具

将 TXT 文本解析为章节并生成 EPUB3。一个 distribution 装三个顶层子包：

| 子包      | 说明                                                          |
| --------- | ------------------------------------------------------------- |
| `sec.core` | 核心库，不依赖任何前端；唯一总入口 `process()`                 |
| `sec.cli`  | 命令行前端，入口点 `sec-cli`                                   |
| `sec.gui`  | Tkinter 图形界面前端，入口点 `sec-gui`                         |

版本号只有一处：根 `pyproject.toml` 的 `version`。`sec.__version__`、`sec.core.__version__`
等全部由 `importlib.metadata` 读同一个值，代码里不写死。

依赖：`ebooklib` + `chardet` + `click`。使用 [uv](https://github.com/astral-sh/uv) 管理。

## 安装

```bash
uv sync
```

就这一条命令——只有一个包需要安装，不再有 workspace 成员，也不需要 `--all-packages`。

## 用法

命令行：

```bash
uv run sec-cli 我的小说.txt                        # 生成 我的小说.epub
uv run sec-cli 我的小说.txt --title "书名" --author "作者"
uv run sec-cli 我的小说.txt --toc-only             # 只输出目录（stdout）
uv run sec-cli 我的小说.txt --toc-only --toc-format json
uv run sec-cli 我的小说.txt --toc-only -o toc.json  # 目录写入文件
uv run sec-cli 我的小说.txt --dump-css out.css     # 只导出 CSS
```

单一命令，靠 `--toc-only` 切换「只输出目录」模式。完整选项见 `uv run sec-cli --help`。

图形界面：

```bash
uv run sec-gui
```

作为库：

```python
from sec.core import Config, process, read_lines

lines, used = read_lines(src, "auto")
tree, stats = process(lines, Config(input=src, title="书名"))
```

书名与作者未显式指定时，`process()` 会先从文件名猜（`《书名》作者：作者`，
见 `sec.core.meta.resolve_metadata`），并写回 `cfg`。

## 替换规则的作用范围

`--replace-json` / `--replace-file` 收一个 JSON 列表，每条规则可带可选的 `scope`：

```json
[
  { "pattern": "^#+\\s*", "replace": "" },
  { "pattern": "正文里的\\s+", "replace": " ", "scope": "body" },
  { "pattern": "括号",     "replace": "【】", "scope": "all" }
]
```

| `scope` | 作用位置 |
|---------|----------|
| `title` | 只改标题（含目录页与书页标题）——**默认值** |
| `body`  | 只改正文段落 |
| `all`   | 标题与正文都改 |

默认只改标题，是因为 GUI 里只能看到目录预览，「默认也动正文」反而不符合直觉。
原始标题始终保留在 `node.raw_title`。

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
内置样式用 `body > section` 这组结构选择器排版，`--css-file` 追加在最后因而可以覆盖
（各家阅读器对 CSS 里带命名空间的 `epub|type` 属性选择器支持不一致，所以没拿它来选）。

```bash
sec-cli novel.txt                          # 同目录没 cover.* → 生成文字封面页
sec-cli novel.txt --no-text-cover          # 不要文字封面页
sec-cli novel.txt --cover cover.png        # 显式给图
```

## 处理流程

`sec.core.pipeline.process()` 是唯一入口，按顺序做完这六步：

1. 封面自动发现（没给 `--cover` 时找同目录的 `cover.*`），结果写回 `cfg`
2. `Config.validate()` —— 校验取值范围、日期格式、字体/封面格式
3. 读取与编码识别（BOM → chardet → 逐个尝试，`--encoding` 可手动指定）
4. 按标题正则切分为章节（在原始行上进行，保留空行/空格信息）
5. 逐页清理（去段首/段尾空格、删空行，`--no-clean` 关闭）
6. 按 `scope` 分流应用替换规则（标题规则只进 `node.title`，正文规则只进
   `node.paragraphs`），然后组装 EPUB3（zip 最高压缩等级 `compresslevel=9`）

封面页是在第 6 步组装时定的，所以「文字封面」拿得到第 1、3 步猜出来的书名/作者。
两个前端都只做「收集参数 → 调 `process()` → 展示结果」，不再各自实现其中任何一步。

## 测试

```bash
uv run pytest                    # 全部用例
uv run pytest tests/core         # 仅核心库
uv run pytest tests/cli          # 仅命令行前端
uv run pytest tests/gui          # 仅图形界面前端
```
