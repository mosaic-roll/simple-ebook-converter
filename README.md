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

## 处理流程

`sec.core.pipeline.process()` 是唯一入口，按顺序做完这五步：

1. `Config.validate()` —— 校验取值范围、日期格式、字体/封面格式
2. 读取与编码识别（BOM → chardet → 逐个尝试，`--encoding` 可手动指定）
3. 按标题正则切分为章节（在原始行上进行，保留空行/空格信息）
4. 逐页清理（去段首/段尾空格、删空行，`--no-clean` 关闭）并应用替换规则
   （`--replace-json` / `--replace-file`，同时作用于标题与正文）
5. 组装 EPUB3（zip 最高压缩等级 `compresslevel=9`）

两个前端都只做「收集参数 → 调 `process()` → 展示结果」，不再各自实现其中任何一步。

## 测试

```bash
uv run pytest                    # 全部用例
uv run pytest tests/core         # 仅核心库
uv run pytest tests/cli          # 仅命令行前端
uv run pytest tests/gui          # 仅图形界面前端
```
