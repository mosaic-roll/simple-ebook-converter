# sec — TXT 转 EPUB3 命令行工具

将 TXT 文本解析为章节并生成 EPUB3。核心模块（`sec.parser` / `sec.builder` / `sec.toc` 等）设计为可被 CLI 与未来的 Tkinter GUI 共用。

依赖：`click` / `ebooklib` / `chardet`。使用 [uv](https://github.com/astral-sh/uv) 管理。

## 安装

```bash
uv sync
```

## 用法

```bash
uv run sec-cli 我的小说.txt                       # 生成 我的小说.epub
uv run sec-cli 我的小说.txt --title "书名" --author "作者"
uv run sec-cli toc 我的小说.txt                   # 只输出目录
uv run sec-cli toc 我的小说.txt --toc-format json
```

完整选项见 `uv run sec-cli --help` / `uv run sec-cli toc --help`。

## 处理流程

1. 读取与编码识别（BOM → chardet → 逐个尝试，`--encoding` 可手动指定）
2. 按标题正则切分为章节（在原始行上进行，保留空行/空格信息）
3. 逐页清理（去段首/段尾空格、删空行，`--no-clean` 关闭）
4. 逐页应用替换规则（`--replace-json` / `--replace-file`）
5. 组装 EPUB3

## 测试

```bash
uv run pytest
```