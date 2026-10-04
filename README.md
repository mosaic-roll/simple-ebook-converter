# simple-ebook-converter — TXT 转 EPUB3 工具

将 TXT 文本解析为章节并生成 EPUB3。提供图形界面和命令行两种方式。

## 安装

用 [uv](https://github.com/astral-sh/uv)（推荐）：

```bash
uv sync                 # 只装核心库与 CLI
uv sync --extra gui     # 额外装 GUI 依赖
```

或用 pip：

```bash
pip install -e .
pip install -e ".[gui]"   # 需要图形界面时
```

## 运行

### 图形界面（推荐）

```bash
uv run simple-ebook-converter
```

### 命令行

```bash
# 最简：转换一本书
uv run simple-ebook-converter-cli 我的小说.txt

# 查看全部选项
uv run simple-ebook-converter-cli --help
```

详细用法见 [doc/cli.md](doc/cli.md)。

## 作为库使用

```python
from pathlib import Path
from simple_ebook_converter.core.config import Config
from simple_ebook_converter.core.pipeline import read_book

cfg = Config(input=Path("novel.txt"))
book = read_book(cfg)
```
